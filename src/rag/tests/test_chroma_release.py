import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path

from src.rag.chroma_release import (
    ARCHIVE_FILENAME,
    CHROMA_SQLITE_FILENAME,
    LOCAL_MANIFEST_FILENAME,
    MANIFEST_FILENAME,
    ChromaManifest,
    ensure_chroma_db_up_to_date,
    install_chroma_archive,
    package_chroma_dir,
    publish_chroma_release,
    read_local_manifest,
    safe_extract_tar_gz,
)
from src.rag.config import RagConfig


def _create_fake_chroma_dir(chroma_dir: Path, payload: bytes = b"sqlite-data") -> None:
    """Create a minimal valid ChromaDB directory layout for tests."""
    chroma_dir.mkdir(parents=True, exist_ok=True)
    (chroma_dir / CHROMA_SQLITE_FILENAME).write_bytes(payload)
    segment_dir = chroma_dir / "11111111-1111-1111-1111-111111111111"
    segment_dir.mkdir(parents=True, exist_ok=True)
    (segment_dir / "data_level0.bin").write_bytes(b"hnsw-index")


class TestChromaRelease(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.root = Path(self.tmp_dir.name)
        self.config = RagConfig(
            chroma_dir=self.root / "chroma_db",
            chroma_collection="nasa_scientific_reports",
            github_repo="KZH-etu/Hack-NASA-Proteus4",
            chroma_release_prefix="chroma-db-",
        )

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_package_excludes_local_manifest_and_computes_sha256(self) -> None:
        _create_fake_chroma_dir(self.config.chroma_dir)
        (self.config.chroma_dir / LOCAL_MANIFEST_FILENAME).write_text("{}", encoding="utf-8")
        out_dir = self.root / "out"

        archive_path, manifest_path, manifest = package_chroma_dir(
            self.config.chroma_dir,
            out_dir,
            tag_name="chroma-db-v20261114-120000",
            collection_name=self.config.chroma_collection,
            skip_verify=True,
        )

        self.assertTrue(archive_path.is_file())
        self.assertTrue(manifest_path.is_file())
        self.assertEqual(manifest.tag_name, "chroma-db-v20261114-120000")
        self.assertGreater(manifest.size_bytes, 0)
        self.assertEqual(len(manifest.sha256), 64)

        with tarfile.open(archive_path, "r:gz") as tar:
            names = tar.getnames()
        self.assertIn(CHROMA_SQLITE_FILENAME, names)
        self.assertIn("11111111-1111-1111-1111-111111111111/data_level0.bin", names)
        self.assertNotIn(LOCAL_MANIFEST_FILENAME, names)

    def test_safe_extract_blocks_path_traversal(self) -> None:
        evil_tar = self.root / "evil.tar.gz"
        evil_src = self.root / "evil_src.txt"
        evil_src.write_text("pwned", encoding="utf-8")

        with tarfile.open(evil_tar, "w:gz") as tar:
            tar.add(evil_src, arcname="../escape.txt")

        with self.assertRaises(ValueError):
            safe_extract_tar_gz(evil_tar, self.root / "extract_target")

    def test_install_chroma_archive_rolls_back_on_bad_sha256(self) -> None:
        _create_fake_chroma_dir(self.config.chroma_dir, payload=b"original-db")
        archive_path, _, manifest = package_chroma_dir(
            self.config.chroma_dir,
            self.root / "pkg",
            tag_name="chroma-db-v2",
            collection_name=self.config.chroma_collection,
            skip_verify=True,
        )
        bad_manifest = ChromaManifest(
            tag_name="chroma-db-v2",
            asset_name=ARCHIVE_FILENAME,
            sha256="0" * 64,
            size_bytes=manifest.size_bytes,
            collection_name=self.config.chroma_collection,
            chunk_count=None,
            created_at=manifest.created_at,
        )

        with self.assertRaises(ValueError):
            install_chroma_archive(archive_path, self.config.chroma_dir, bad_manifest)

        self.assertEqual(
            (self.config.chroma_dir / CHROMA_SQLITE_FILENAME).read_bytes(),
            b"original-db",
        )

    def test_publish_and_ensure_up_to_date_flow(self) -> None:
        source_dir = self.root / "source_chroma"
        _create_fake_chroma_dir(source_dir, payload=b"fresh-release-db")
        pkg_dir = self.root / "remote_release"
        archive_path, manifest_path, expected_manifest = package_chroma_dir(
            source_dir,
            pkg_dir,
            tag_name="chroma-db-v20261114-213500",
            collection_name=self.config.chroma_collection,
            skip_verify=True,
        )

        def fake_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            if cmd[:3] == ["gh", "release", "list"]:
                payload = [
                    {
                        "tagName": "v0.1.0",
                        "name": "App release",
                        "isDraft": False,
                        "publishedAt": "2026-11-14T22:00:00Z",
                    },
                    {
                        "tagName": expected_manifest.tag_name,
                        "name": f"ChromaDB {expected_manifest.tag_name}",
                        "isDraft": False,
                        "publishedAt": "2026-11-14T21:35:00Z",
                    },
                ]
                return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
            if cmd[:3] == ["gh", "release", "view"]:
                payload = {
                    "tagName": expected_manifest.tag_name,
                    "name": f"ChromaDB {expected_manifest.tag_name}",
                    "publishedAt": "2026-11-14T21:35:00Z",
                    "assets": [
                        {"name": ARCHIVE_FILENAME},
                        {"name": MANIFEST_FILENAME},
                    ],
                }
                return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(payload), stderr="")
            if cmd[:3] == ["gh", "release", "download"]:
                dir_idx = cmd.index("--dir") + 1
                pat_idx = cmd.index("--pattern") + 1
                target_dir = Path(cmd[dir_idx])
                pattern = cmd[pat_idx]
                target_dir.mkdir(parents=True, exist_ok=True)
                if pattern == MANIFEST_FILENAME:
                    shutil.copy2(manifest_path, target_dir / MANIFEST_FILENAME)
                elif pattern == ARCHIVE_FILENAME:
                    shutil.copy2(archive_path, target_dir / ARCHIVE_FILENAME)
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            raise AssertionError(f"Unexpected command: {cmd}")

        # 1. Local missing -> downloads and installs
        res_download = ensure_chroma_db_up_to_date(self.config, runner=fake_runner)
        self.assertEqual(res_download.status, "downloaded")
        self.assertEqual(res_download.tag_name, expected_manifest.tag_name)
        self.assertEqual(
            (self.config.chroma_dir / CHROMA_SQLITE_FILENAME).read_bytes(),
            b"fresh-release-db",
        )
        local_manifest = read_local_manifest(self.config.chroma_dir)
        self.assertIsNotNone(local_manifest)
        self.assertEqual(local_manifest.sha256, expected_manifest.sha256)

        # 2. Local already synced -> skips download
        res_cached = ensure_chroma_db_up_to_date(self.config, runner=fake_runner)
        self.assertEqual(res_cached.status, "up_to_date")

    def test_ensure_falls_back_to_local_when_gh_fails_and_not_strict(self) -> None:
        _create_fake_chroma_dir(self.config.chroma_dir, payload=b"offline-db")

        def failing_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="network down")

        result = ensure_chroma_db_up_to_date(self.config, runner=failing_runner)
        self.assertEqual(result.status, "local_fallback")

        strict_config = RagConfig(
            chroma_dir=self.config.chroma_dir,
            chroma_collection=self.config.chroma_collection,
            github_repo=self.config.github_repo,
            chroma_sync_strict=True,
        )
        with self.assertRaises(RuntimeError):
            ensure_chroma_db_up_to_date(strict_config, runner=failing_runner)

    def test_publish_dry_run_skips_gh_release_create(self) -> None:
        _create_fake_chroma_dir(self.config.chroma_dir)
        called: list[list[str]] = []

        def recorder(cmd: list[str]) -> subprocess.CompletedProcess[str]:
            called.append(cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

        manifest = publish_chroma_release(
            self.config,
            tag_name="chroma-db-vtest",
            dry_run=True,
            skip_verify=True,
            runner=recorder,
        )
        self.assertEqual(manifest.tag_name, "chroma-db-vtest")
        self.assertEqual(called, [])
