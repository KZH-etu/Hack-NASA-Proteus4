"""Package, publish, check, and download ChromaDB snapshots via GitHub Releases (gh CLI)."""

from __future__ import annotations

import dataclasses
import gc
import hashlib
import json
import logging
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import chromadb

from src.rag.config import RagConfig

logger = logging.getLogger(__name__)

ARCHIVE_FILENAME = "chroma_db.tar.gz"
MANIFEST_FILENAME = "chroma_db_manifest.json"
LOCAL_MANIFEST_FILENAME = ".release_manifest.json"
CHROMA_SQLITE_FILENAME = "chroma.sqlite3"

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]


@dataclass(slots=True)
class ChromaManifest:
    """Metadata describing a packaged ChromaDB release archive."""

    tag_name: str
    asset_name: str
    sha256: str
    size_bytes: int
    collection_name: str
    chunk_count: int | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        """Serialize the manifest to a JSON-compatible dictionary."""
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChromaManifest":
        """Build a ChromaManifest from parsed JSON."""
        return cls(
            tag_name=str(data["tag_name"]),
            asset_name=str(data.get("asset_name") or ARCHIVE_FILENAME),
            sha256=str(data.get("sha256") or ""),
            size_bytes=int(data.get("size_bytes") or 0),
            collection_name=str(data.get("collection_name") or ""),
            chunk_count=(
                int(data["chunk_count"]) if data.get("chunk_count") is not None else None
            ),
            created_at=str(data.get("created_at") or ""),
        )


@dataclass(slots=True)
class ReleaseSummary:
    """Summary of a remote GitHub Release for ChromaDB."""

    tag_name: str
    name: str
    published_at: str
    assets: list[dict[str, Any]]
    manifest: ChromaManifest | None = None


@dataclass(slots=True)
class SyncResult:
    """Result returned by ensure_chroma_db_up_to_date."""

    status: str  # "up_to_date" | "downloaded" | "outdated" | "local_fallback"
    tag_name: str | None
    chunk_count: int | None
    chroma_dir: Path
    message: str


def _default_runner(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    """Run an external CLI command and capture UTF-8 output."""
    return subprocess.run(
        cmd,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _run_gh(args: list[str], runner: CommandRunner = _default_runner) -> str:
    """Execute a gh CLI command and raise a clear RuntimeError on failure."""
    cmd = ["gh", *args]
    try:
        proc = runner(cmd)
    except FileNotFoundError as exc:
        raise RuntimeError(
            "Le CLI GitHub 'gh' est introuvable. Installez-le (https://cli.github.com/) "
            "et authentifiez-vous avec 'gh auth login'."
        ) from exc

    if proc.returncode != 0:
        details = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"Échec de la commande '{' '.join(cmd)}': {details}")
    return proc.stdout


def resolve_github_repo(
    configured_repo: str | None = None,
    runner: CommandRunner = _default_runner,
) -> str:
    """Resolve owner/repo from config or fallback to the git origin remote."""
    if configured_repo and configured_repo.strip():
        return configured_repo.strip()

    proc = runner(["git", "remote", "get-url", "origin"])
    if proc.returncode == 0:
        url = proc.stdout.strip()
        match = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", url)
        if match:
            return match.group(1)

    raise RuntimeError(
        "Impossible de déterminer le dépôt GitHub (configurez RAG_GITHUB_REPO)."
    )


def compute_sha256(file_path: Path) -> str:
    """Compute the hex SHA-256 digest of a file in streaming chunks."""
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def has_valid_local_chroma(chroma_dir: Path) -> bool:
    """Return True when chroma_dir contains a non-empty chroma.sqlite3 database."""
    sqlite_file = chroma_dir / CHROMA_SQLITE_FILENAME
    return sqlite_file.is_file() and sqlite_file.stat().st_size > 0


def read_local_manifest(chroma_dir: Path) -> ChromaManifest | None:
    """Read the local .release_manifest.json if present and valid."""
    manifest_path = chroma_dir / LOCAL_MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        return ChromaManifest.from_dict(payload)
    except (OSError, ValueError, KeyError) as exc:
        logger.warning("Manifeste local invalide (%s): %s", manifest_path, exc)
        return None


def write_local_manifest(chroma_dir: Path, manifest: ChromaManifest) -> Path:
    """Persist .release_manifest.json inside chroma_dir."""
    chroma_dir.mkdir(parents=True, exist_ok=True)
    target = chroma_dir / LOCAL_MANIFEST_FILENAME
    target.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return target


def read_chroma_chunk_count(chroma_dir: Path, collection_name: str) -> int | None:
    """Inspect the number of chunks in the target ChromaDB collection."""
    if not has_valid_local_chroma(chroma_dir):
        return None
    client: Any | None = None
    try:
        client = chromadb.PersistentClient(path=str(chroma_dir))
        collection = client.get_collection(name=collection_name)
        return int(collection.count())
    except Exception as exc:
        logger.warning("Impossible de compter les chunks dans %s: %s", chroma_dir, exc)
        return None
    finally:
        if client is not None:
            system = getattr(client, "_system", None)
            if system is not None and hasattr(system, "stop"):
                try:
                    system.stop()
                except Exception:
                    pass
            del client
            gc.collect()


def generate_release_tag(prefix: str = "chroma-db-") -> str:
    """Build a chronological UTC release tag name."""
    stamp = datetime.now(timezone.utc).strftime("v%Y%m%d-%H%M%S")
    return f"{prefix}{stamp}"


def package_chroma_dir(
    chroma_dir: Path,
    output_dir: Path,
    *,
    tag_name: str,
    collection_name: str,
    skip_verify: bool = False,
) -> tuple[Path, Path, ChromaManifest]:
    """Compress chroma_dir into chroma_db.tar.gz and write chroma_db_manifest.json."""
    if not has_valid_local_chroma(chroma_dir):
        raise FileNotFoundError(
            f"Base ChromaDB introuvable ou vide dans {chroma_dir} "
            f"({CHROMA_SQLITE_FILENAME} manquant)."
        )

    chunk_count = (
        None if skip_verify else read_chroma_chunk_count(chroma_dir, collection_name)
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    archive_path = output_dir / ARCHIVE_FILENAME
    manifest_path = output_dir / MANIFEST_FILENAME

    files_to_pack = sorted(
        p
        for p in chroma_dir.rglob("*")
        if p.is_file() and p.name != LOCAL_MANIFEST_FILENAME
    )
    if not files_to_pack:
        raise RuntimeError(f"Aucun fichier à compresser dans {chroma_dir}.")

    with tarfile.open(archive_path, "w:gz") as tar:
        for file_path in files_to_pack:
            rel_path = file_path.relative_to(chroma_dir).as_posix()
            tar.add(file_path, arcname=rel_path, recursive=False)

    manifest = ChromaManifest(
        tag_name=tag_name,
        asset_name=ARCHIVE_FILENAME,
        sha256=compute_sha256(archive_path),
        size_bytes=archive_path.stat().st_size,
        collection_name=collection_name,
        chunk_count=chunk_count,
        created_at=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    )
    manifest_path.write_text(
        json.dumps(manifest.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return archive_path, manifest_path, manifest


def publish_chroma_release(
    config: RagConfig,
    *,
    tag_name: str | None = None,
    notes: str | None = None,
    dry_run: bool = False,
    skip_verify: bool = False,
    runner: CommandRunner = _default_runner,
) -> ChromaManifest:
    """Compress local ChromaDB and publish it as a GitHub Release via gh CLI."""
    resolved_tag = tag_name or generate_release_tag(config.chroma_release_prefix)
    repo = resolve_github_repo(config.github_repo, runner=runner)

    with tempfile.TemporaryDirectory(prefix="chroma_pack_") as tmp:
        tmp_dir = Path(tmp)
        archive_path, manifest_path, manifest = package_chroma_dir(
            config.chroma_dir,
            tmp_dir,
            tag_name=resolved_tag,
            collection_name=config.chroma_collection,
            skip_verify=skip_verify,
        )

        size_mb = manifest.size_bytes / (1024 * 1024)
        if dry_run:
            logger.info(
                "[dry-run] Archive prête : %s (%.2f Mo, sha256=%s, chunks=%s)",
                archive_path.name,
                size_mb,
                manifest.sha256,
                manifest.chunk_count,
            )
            return manifest

        release_notes = notes or (
            f"Snapshot ChromaDB (`{manifest.collection_name}`)\n\n"
            f"- **Tag** : `{manifest.tag_name}`\n"
            f"- **Chunks** : `{manifest.chunk_count if manifest.chunk_count is not None else 'non vérifié'}`\n"
            f"- **Taille archive** : `{size_mb:.2f} Mo` ({manifest.size_bytes} octets)\n"
            f"- **SHA-256** : `{manifest.sha256}`\n"
            f"- **Créé le (UTC)** : `{manifest.created_at}`"
        )

        _run_gh(
            [
                "release",
                "create",
                manifest.tag_name,
                str(archive_path),
                str(manifest_path),
                "--repo",
                repo,
                "--title",
                f"ChromaDB {manifest.tag_name}",
                "--notes",
                release_notes,
            ],
            runner=runner,
        )
        write_local_manifest(config.chroma_dir, manifest)
        return manifest


def _parse_iso_timestamp(value: str) -> datetime:
    """Parse an ISO-8601 timestamp string safely."""
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def get_latest_chroma_release(
    config: RagConfig,
    *,
    runner: CommandRunner = _default_runner,
) -> ReleaseSummary | None:
    """Fetch the latest non-draft GitHub Release matching chroma_release_prefix."""
    repo = resolve_github_repo(config.github_repo, runner=runner)
    raw_list = _run_gh(
        [
            "release",
            "list",
            "--repo",
            repo,
            "--limit",
            "30",
            "--json",
            "tagName,name,isDraft,publishedAt",
        ],
        runner=runner,
    )
    releases = json.loads(raw_list or "[]")
    matching = [
        item
        for item in releases
        if not item.get("isDraft")
        and str(item.get("tagName", "")).startswith(config.chroma_release_prefix)
    ]
    if not matching:
        return None

    matching.sort(
        key=lambda item: _parse_iso_timestamp(str(item.get("publishedAt") or "")),
        reverse=True,
    )
    latest_tag = str(matching[0]["tagName"])

    raw_view = _run_gh(
        [
            "release",
            "view",
            latest_tag,
            "--repo",
            repo,
            "--json",
            "tagName,name,publishedAt,assets",
        ],
        runner=runner,
    )
    details = json.loads(raw_view)
    assets = list(details.get("assets") or [])
    manifest = _download_remote_manifest(repo, latest_tag, assets, runner=runner)

    return ReleaseSummary(
        tag_name=str(details["tagName"]),
        name=str(details.get("name") or details["tagName"]),
        published_at=str(details.get("publishedAt") or ""),
        assets=assets,
        manifest=manifest,
    )


def _download_remote_manifest(
    repo: str,
    tag_name: str,
    assets: list[dict[str, Any]],
    *,
    runner: CommandRunner = _default_runner,
) -> ChromaManifest | None:
    """Download and parse chroma_db_manifest.json if attached to the release."""
    has_manifest = any(a.get("name") == MANIFEST_FILENAME for a in assets)
    if not has_manifest:
        return None

    with tempfile.TemporaryDirectory(prefix="chroma_manifest_") as tmp:
        tmp_dir = Path(tmp)
        _run_gh(
            [
                "release",
                "download",
                tag_name,
                "--repo",
                repo,
                "--dir",
                str(tmp_dir),
                "--pattern",
                MANIFEST_FILENAME,
                "--clobber",
            ],
            runner=runner,
        )
        manifest_file = tmp_dir / MANIFEST_FILENAME
        if not manifest_file.is_file():
            return None
        payload = json.loads(manifest_file.read_text(encoding="utf-8"))
        return ChromaManifest.from_dict(payload)


def is_local_chroma_up_to_date(
    chroma_dir: Path,
    remote: ReleaseSummary,
) -> bool:
    """Return True when the local ChromaDB matches the remote release."""
    if not has_valid_local_chroma(chroma_dir):
        return False

    local_manifest = read_local_manifest(chroma_dir)
    if local_manifest is None:
        return False
    if local_manifest.tag_name != remote.tag_name:
        return False

    if remote.manifest and remote.manifest.sha256:
        return local_manifest.sha256 == remote.manifest.sha256
    return True


def safe_extract_tar_gz(archive_path: Path, dest_dir: Path) -> None:
    """Extract a .tar.gz archive safely, blocking path traversal and links."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_root = dest_dir.resolve()

    with tarfile.open(archive_path, "r:gz") as tar:
        members = tar.getmembers()
        for member in members:
            if member.issym() or member.islnk():
                raise ValueError(f"Lien symbolique/dur interdit dans l'archive: {member.name}")

            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                raise ValueError(f"Chemin interdit dans l'archive: {member.name}")

            resolved_target = (dest_root / member_path).resolve()
            if resolved_target != dest_root and dest_root not in resolved_target.parents:
                raise ValueError(f"Évasion de répertoire détectée: {member.name}")

        for member in members:
            if member.isdir():
                (dest_root / member.name).mkdir(parents=True, exist_ok=True)
            elif member.isfile():
                target_file = dest_root / member.name
                target_file.parent.mkdir(parents=True, exist_ok=True)
                source = tar.extractfile(member)
                if source is None:
                    continue
                with source, target_file.open("wb") as out:
                    shutil.copyfileobj(source, out)


def install_chroma_archive(
    archive_path: Path,
    chroma_dir: Path,
    manifest: ChromaManifest,
) -> None:
    """Verify SHA-256, extract archive to .tmp, and swap atomically into chroma_dir."""
    if manifest.sha256:
        actual_sha = compute_sha256(archive_path)
        if actual_sha != manifest.sha256:
            raise ValueError(
                f"Somme SHA-256 invalide pour {archive_path.name}: "
                f"attendu {manifest.sha256}, obtenu {actual_sha}"
            )

    parent_dir = chroma_dir.parent
    parent_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = parent_dir / f"{chroma_dir.name}.tmp"
    bak_dir = parent_dir / f"{chroma_dir.name}.bak"

    if tmp_dir.exists():
        shutil.rmtree(tmp_dir)
    if bak_dir.exists():
        shutil.rmtree(bak_dir)

    try:
        safe_extract_tar_gz(archive_path, tmp_dir)
        if not has_valid_local_chroma(tmp_dir):
            raise RuntimeError(
                f"Archive invalide : {CHROMA_SQLITE_FILENAME} absent après décompression."
            )
        write_local_manifest(tmp_dir, manifest)

        had_existing = chroma_dir.exists()
        if had_existing:
            os.replace(chroma_dir, bak_dir)

        try:
            os.replace(tmp_dir, chroma_dir)
        except Exception:
            if had_existing and bak_dir.exists() and not chroma_dir.exists():
                os.replace(bak_dir, chroma_dir)
            raise

        if bak_dir.exists():
            shutil.rmtree(bak_dir, ignore_errors=True)
    finally:
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)


def download_chroma_release(
    config: RagConfig,
    remote: ReleaseSummary,
    *,
    runner: CommandRunner = _default_runner,
) -> ChromaManifest:
    """Download the archive from a GitHub Release and install it into config.chroma_dir."""
    repo = resolve_github_repo(config.github_repo, runner=runner)
    has_archive = any(a.get("name") == ARCHIVE_FILENAME for a in remote.assets)
    if not has_archive:
        raise RuntimeError(
            f"La release '{remote.tag_name}' ne contient pas l'asset '{ARCHIVE_FILENAME}'."
        )

    with tempfile.TemporaryDirectory(prefix="chroma_dl_") as tmp:
        tmp_dir = Path(tmp)
        _run_gh(
            [
                "release",
                "download",
                remote.tag_name,
                "--repo",
                repo,
                "--dir",
                str(tmp_dir),
                "--pattern",
                ARCHIVE_FILENAME,
                "--clobber",
            ],
            runner=runner,
        )
        archive_path = tmp_dir / ARCHIVE_FILENAME
        if not archive_path.is_file():
            raise RuntimeError(
                f"Échec du téléchargement de '{ARCHIVE_FILENAME}' depuis '{remote.tag_name}'."
            )

        manifest = remote.manifest or ChromaManifest(
            tag_name=remote.tag_name,
            asset_name=ARCHIVE_FILENAME,
            sha256=compute_sha256(archive_path),
            size_bytes=archive_path.stat().st_size,
            collection_name=config.chroma_collection,
            chunk_count=None,
            created_at=remote.published_at,
        )
        install_chroma_archive(archive_path, config.chroma_dir, manifest)
        return manifest


def ensure_chroma_db_up_to_date(
    config: RagConfig,
    *,
    force: bool = False,
    check_only: bool = False,
    runner: CommandRunner = _default_runner,
) -> SyncResult:
    """Ensure local ChromaDB exists and matches the latest GitHub Release."""
    local_valid = has_valid_local_chroma(config.chroma_dir)
    local_manifest = read_local_manifest(config.chroma_dir)

    try:
        remote = get_latest_chroma_release(config, runner=runner)
    except Exception as exc:
        if local_valid and not config.chroma_sync_strict and not force:
            logger.warning(
                "Impossible de vérifier la dernière release ChromaDB (%s). "
                "Utilisation de la base locale existante.",
                exc,
            )
            return SyncResult(
                status="local_fallback",
                tag_name=local_manifest.tag_name if local_manifest else None,
                chunk_count=local_manifest.chunk_count if local_manifest else None,
                chroma_dir=config.chroma_dir,
                message=f"Vérification GitHub impossible ({exc}) ; base locale conservée.",
            )
        raise

    if remote is None:
        if local_valid and not config.chroma_sync_strict and not force:
            return SyncResult(
                status="local_fallback",
                tag_name=local_manifest.tag_name if local_manifest else None,
                chunk_count=local_manifest.chunk_count if local_manifest else None,
                chroma_dir=config.chroma_dir,
                message="Aucune release ChromaDB publiée sur GitHub ; base locale conservée.",
            )
        raise RuntimeError(
            f"Aucune release '{config.chroma_release_prefix}*' trouvée sur {config.github_repo}."
        )

    if not force and is_local_chroma_up_to_date(config.chroma_dir, remote):
        return SyncResult(
            status="up_to_date",
            tag_name=remote.tag_name,
            chunk_count=remote.manifest.chunk_count if remote.manifest else None,
            chroma_dir=config.chroma_dir,
            message=f"Base ChromaDB déjà à jour ({remote.tag_name}).",
        )

    if check_only:
        return SyncResult(
            status="outdated",
            tag_name=remote.tag_name,
            chunk_count=remote.manifest.chunk_count if remote.manifest else None,
            chroma_dir=config.chroma_dir,
            message=f"Mise à jour disponible : {remote.tag_name}.",
        )

    installed = download_chroma_release(config, remote, runner=runner)
    return SyncResult(
        status="downloaded",
        tag_name=installed.tag_name,
        chunk_count=installed.chunk_count,
        chroma_dir=config.chroma_dir,
        message=f"Base ChromaDB téléchargée et installée ({installed.tag_name}).",
    )
