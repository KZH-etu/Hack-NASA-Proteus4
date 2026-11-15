"""Cache des modèles entraînés (src/models/model_gp/cache.py) : rechargement, réentraînement et replis."""

from src.models.model_gp import cache


class Trainer:
    """Faux entraînement : compte les appels et renvoie un objet sérialisable."""

    def __init__(self):
        self.calls = 0

    def __call__(self):
        self.calls += 1
        return {"poids": [1.0, 2.0], "entrainement": self.calls}


def test_entraine_puis_recharge(tmp_path):
    train = Trainer()
    first = cache.load_or_train("flex", train, cache_dir=tmp_path, key="v1")
    assert train.calls == 1
    assert (tmp_path / "flex.joblib").exists() and (tmp_path / "flex.key").read_text() == "v1"
    again = cache.load_or_train("flex", train, cache_dir=tmp_path, key="v1")
    assert train.calls == 1  # rechargé, pas réentraîné
    assert again == first


def test_reentraine_si_donnees_ou_code_changent(tmp_path):
    train = Trainer()
    cache.load_or_train("gas", train, cache_dir=tmp_path, key="v1")
    model = cache.load_or_train("gas", train, cache_dir=tmp_path, key="v2")
    assert train.calls == 2 and model["entrainement"] == 2
    assert (tmp_path / "gas.key").read_text() == "v2"


def test_fichier_abime_reentraine(tmp_path):
    train = Trainer()
    cache.load_or_train("solids", train, cache_dir=tmp_path, key="v1")
    (tmp_path / "solids.joblib").write_bytes(b"pas un modele")
    model = cache.load_or_train("solids", train, cache_dir=tmp_path, key="v1")
    assert train.calls == 2 and model["entrainement"] == 2


def test_sauvegarde_impossible_renvoie_quand_meme_le_modele(tmp_path):
    blocked = tmp_path / "fichier"
    blocked.write_text("")  # un fichier à la place du dossier : la sauvegarde échoue
    model = cache.load_or_train("flex", Trainer(), cache_dir=blocked / "models", key="v1")
    assert model["entrainement"] == 1


def test_empreinte_suit_les_sources_et_ignore_les_fins_de_ligne(tmp_path):
    sources = ("src/*.py", "data/*.parquet")
    (tmp_path / "src").mkdir()
    (tmp_path / "data").mkdir()
    code, table = tmp_path / "src" / "model.py", tmp_path / "data" / "t.parquet"
    code.write_bytes(b"a = 1\nb = 2\n")
    table.write_bytes(b"\x00\x01")
    key = cache.fingerprint(tmp_path, sources)
    code.write_bytes(b"a = 1\r\nb = 2\r\n")  # même fichier extrait sous Windows
    assert cache.fingerprint(tmp_path, sources) == key
    table.write_bytes(b"\x00\x02")  # données modifiées
    assert cache.fingerprint(tmp_path, sources) != key


def test_empreinte_du_projet_stable():
    assert cache.fingerprint() == cache.fingerprint()
