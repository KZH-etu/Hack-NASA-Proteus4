"""Les fonctions appelées par le dashboard.

    from src.models.model_rf.service import MLService
    ml = MLService()                          # charge data/processed/*.parquet et entraîne
    ml.list_families()                        # familles avec au moins un modèle
    ml.get_parameters(famille)                # paramètres + plages réelles -> curseurs
    ml.predict(famille, {...})                # prédictions + incertitude + essais proches
    ml.recommend_next_experiment(famille, {...})

Entraînement (lent, à faire une fois) : python -m src.models.model_rf.train  -> src/models/model_rf/artifacts/ml_service.joblib
Dans le dashboard : ml = MLService.load()  (une seconde), dans une fonction @st.cache_resource.
"""
import itertools

import numpy as np
import pandas as pd
from pathlib import Path

import joblib

from .data_only import DATA_FAMILIES, DataExplorer
from .data_prep import family_rows, load_tables, model_features, prepare_xy, to_features
from .metrics import evaluate, fit_model
from .families import FAMILIES
from .forest import ForestModel, model_for

# Au-delà de cette distance (en écarts-types), aucun essai NASA n'est considéré comme proche.
NEAR_DATA_THRESHOLD = 1.0
MIN_ROWS = 15  # en dessous, on n'entraîne pas : trop peu d'essais pour être honnête
SAVED_PATH = Path(__file__).resolve().parent / "artifacts" / "ml_service.joblib"
SOURCE_COLS = ["test_id", "experiment", "session", "psi_id", "source_file", "source_line"]


class MLService:
    def __init__(self, tables: dict | None = None, model_class=ForestModel, check_quality: bool = True):
        self.tables = tables if tables is not None else load_tables()
        self.models, self.skipped, self.rows, self.quality = {}, {}, {}, {}
        for family, fiche in FAMILIES.items():
            if fiche["fichier"] not in self.tables:
                self.skipped[(family, "*")] = f"table {fiche['fichier']} absente"
                continue
            self.rows[family] = family_rows(self.tables, family)
            for output, spec in fiche["sorties"].items():
                X, y, groups, _ = prepare_xy(self.tables, family, output)
                if len(y) < MIN_ROWS:
                    self.skipped[(family, output)] = f"seulement {len(y)} essais"
                    continue
                cls = model_for(family, output, model_class)
                self.models[(family, output)] = fit_model(cls, spec["type"], family, X, y, groups)
                if check_quality:
                    # Évaluation par session : le modèle bat-il une réponse fixe ?
                    self.quality[(family, output)] = evaluate(self.tables, family, output, cls)
        # Familles sans modèle (solides, aérosols) : recherche d'essais réels
        self.explorer = DataExplorer(self.tables)

    # ---------- 0. Point d'entrée unique pour le dashboard (les 4 familles) ----------
    def catalogue(self) -> list:
        """Toutes les familles proposées à l'utilisateur, avec leur mode de réponse."""
        out = [{"famille": f, "mode": "prediction", "description": FAMILIES[f]["description"]}
               for f in self.list_families()]
        out += [{"famille": f, "mode": "donnees", "description": DATA_FAMILIES[f]["description"]}
                for f in self.explorer.list_families()]
        return out

    def parameters(self, family: str) -> dict:
        """Paramètres de n'importe quelle famille (avec ou sans modèle)."""
        if family in FAMILIES:
            return self.get_parameters(family)
        return self.explorer.get_parameters(family)

    def ask(self, family: str, params: dict) -> dict:
        """Réponse pour n'importe quelle famille : prédiction si un modèle existe, sinon essais réels."""
        if family in FAMILIES:
            out = self.predict(family, params)
            out["mode"] = "prédiction"
            return out
        return self.explorer.find_tests(family, params)

    # ---------- Sauvegarde / chargement ----------
    def save(self, path: Path | str = SAVED_PATH):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: Path | str = SAVED_PATH) -> "MLService":
        return joblib.load(path)

    @staticmethod
    def load_or_train(path: Path | str = SAVED_PATH) -> "MLService":
        """Charge le service entraîné ; s'il n'existe pas encore (ex. après un git clone), l'entraîne (~15 s)."""
        if Path(path).exists():
            return MLService.load(path)
        service = MLService()
        service.save(path)
        return service

    # ---------- 1. Familles disponibles ----------
    def list_families(self) -> list:
        return [f for f in FAMILIES if any(k[0] == f for k in self.models)]

    # ---------- 2. Paramètres et plages, pour les curseurs ----------
    def get_parameters(self, family: str) -> dict:
        X = to_features(self.rows[family], FAMILIES[family]["entrees"])
        params = {}
        for col, kind in FAMILIES[family]["entrees"].items():
            if kind == "nombre":
                v = X[col].dropna()
                params[col] = {"type": "nombre", "min": float(v.min()), "max": float(v.max()),
                               "defaut": float(v.median())}
            else:
                counts = X[col][X[col] != "inconnu"].value_counts()
                params[col] = {"type": "texte", "choix": list(counts.index),  # le plus fréquent d'abord
                               "defaut": counts.index[0]}
        return params

    def default_scenario(self, family: str) -> dict:
        return {k: p["defaut"] for k, p in self.get_parameters(family).items()}

    # ---------- 3. Prédiction ----------
    def predict(self, family: str, params: dict) -> dict:
        fiche = FAMILIES[family]
        X = model_features(pd.DataFrame([params]), family)
        results = {}
        for output, spec in fiche["sorties"].items():
            model = self.models.get((family, output))
            if model is None:
                results[output] = {"indisponible": self.skipped.get((family, output), "pas de modèle")}
                continue
            mean, std = model.predict_with_uncertainty(X)
            if spec["type"] == "regression":
                m, s = float(mean[0]), float(std[0])
                results[output] = {"valeur": m, "incertitude": s,
                                   "intervalle_95": (max(m - 1.96 * s, 0.0), m + 1.96 * s)}
            else:
                probas = {c: round(float(p), 3) for c, p in zip(model.classes_, mean[0])}
                best = max(probas, key=probas.get)
                results[output] = {"issue_probable": best, "probabilite": probas[best],
                                   "incertitude": float(std[0][model.classes_.index(best)]),
                                   "toutes_les_issues": probas}
            q = self.quality.get((family, output))
            if q is not None and not q.get("bat_la_reference", False):
                results[output]["modele_non_fiable"] = (
                    "Testé sur des sessions mises de côté, ce modèle ne fait pas mieux qu'une réponse "
                    "fixe : se fier plutôt aux essais réels les plus proches.")

        nearest = self.nearest_tests(family, params)
        close = bool(len(nearest)) and nearest["distance"].iloc[0] <= NEAR_DATA_THRESHOLD
        out = {"famille": family, "parametres": params, "resultats": results,
               "essais_proches": nearest, "donnee_proche": close}
        if not close:
            out["avertissement"] = ("Aucun essai NASA proche de ces conditions : "
                                    "la prédiction est une extrapolation, à prendre avec prudence.")
        # Un paramètre hors de la plage jamais testée : la forêt ne sait pas extrapoler.
        outside = [f"{c} = {params[c]:g} (testé de {p['min']:g} à {p['max']:g})"
                   for c, p in self.get_parameters(family).items()
                   if p["type"] == "nombre" and params.get(c) is not None
                   and not p["min"] <= params[c] <= p["max"]]
        if outside:
            out["donnee_proche"] = False
            out["hors_plage"] = outside
            out["avertissement"] = ("Hors des conditions testées par la NASA : " + "; ".join(outside)
                                    + ". Le modèle répond comme au bord de la plage : c'est une "
                                      "zone à tester, pas une prédiction fiable.")
        return out

    # ---------- Essais réels les plus proches ----------
    def _distances(self, family: str, queries: pd.DataFrame):
        """Distance de chaque condition demandée à chaque essai réel (matrice requêtes x essais).

        Calculée sur les paramètres numériques normalisés ; un essai avec une valeur texte
        différente (autre carburant, autre matériau…) est considéré comme lointain.
        """
        entrees = FAMILIES[family]["entrees"]
        rows = self.rows[family]
        R = to_features(rows, entrees)
        Q = to_features(queries, entrees)
        num = [c for c, t in entrees.items() if t == "nombre"]
        txt = [c for c, t in entrees.items() if t == "texte"]
        sd = R[num].std().replace(0, 1).fillna(1)
        diff = (Q[num].to_numpy()[:, None, :] - R[num].to_numpy()[None, :, :]) / sd.to_numpy()
        sq = np.where(np.isnan(diff), np.nan, diff ** 2)
        with np.errstate(invalid="ignore"):
            d = np.sqrt(np.nanmean(sq, axis=2) * len(num))     # valeur manquante : ni pour ni contre
        d = np.nan_to_num(d, nan=np.inf)
        for c in txt:                                           # texte différent : distance +10
            d += 10 * (Q[c].to_numpy()[:, None] != R[c].to_numpy()[None, :])
        return d, rows

    def nearest_tests(self, family: str, params: dict, k: int = 3) -> pd.DataFrame:
        """Les k essais NASA réels les plus proches, avec leur source."""
        d, rows = self._distances(family, pd.DataFrame([params]))
        order = np.argsort(d[0])[:k]
        fiche = FAMILIES[family]
        cols = [c for c in SOURCE_COLS + list(fiche["entrees"])
                + [s["colonne"] for s in fiche["sorties"].values()] if c in rows.columns]
        out = rows.iloc[order][list(dict.fromkeys(cols))].reset_index(drop=True)
        out["distance"] = d[0][order]
        return out

    # ---------- 4. Prochaine expérience ----------
    def recommend_next_experiment(self, family: str, scenario: dict, output: str | None = None,
                                  n_points: int = 4, top_k: int = 5) -> pd.DataFrame:
        """Autour du scénario, trouve les conditions où le modèle doute ET où aucun essai n'existe.

        Les paramètres texte restent ceux du scénario ; les numériques varient de ±25 %
        de leur plage réelle, sans en sortir.
        """
        output = output or next(o for o in FAMILIES[family]["sorties"] if (family, o) in self.models)
        model = self.models[(family, output)]
        params = self.get_parameters(family)

        axes = {}
        for col, p in params.items():
            if p["type"] == "nombre":
                center = scenario.get(col, p["defaut"])
                half = 0.25 * (p["max"] - p["min"])
                lo, hi = max(center - half, p["min"]), min(center + half, p["max"])
                axes[col] = np.unique(np.linspace(lo, hi, n_points))
        grid = pd.DataFrame(list(itertools.product(*axes.values())), columns=list(axes))
        for col, p in params.items():
            if p["type"] == "texte":
                grid[col] = scenario.get(col, p["defaut"])

        X = model_features(grid, family)
        mean, std = model.predict_with_uncertainty(X)
        if model.kind == "regression":
            grid["prediction"], grid["incertitude"] = mean, std
        else:
            grid["prediction"] = [model.classes_[i] for i in mean.argmax(axis=1)]
            grid["incertitude"] = 1 - mean.max(axis=1)        # 0 = sûr, proche de 1 = hésite

        d, _ = self._distances(family, grid)
        grid["distance_donnees"] = d.min(axis=1)

        # Score = moitié « le modèle doute », moitié « zone inexplorée »,
        # en préférant les conditions proches du scénario de mission.
        span = {c: (params[c]["max"] - params[c]["min"]) or 1 for c in axes}
        gap = sum(((grid[c] - scenario.get(c, params[c]["defaut"])) / span[c]) ** 2 for c in axes)
        doubt = grid["incertitude"] / (grid["incertitude"].max() or 1)
        novelty = np.minimum(grid["distance_donnees"], 2 * NEAR_DATA_THRESHOLD) / (2 * NEAR_DATA_THRESHOLD)
        grid["score"] = (0.5 * doubt + 0.5 * novelty) / (1 + np.sqrt(gap))
        return grid.sort_values("score", ascending=False).head(top_k).reset_index(drop=True)
