"""Familles SANS modèle (solides, aérosols) : recherche des essais NASA réels les plus proches.

Même parcours que pour les familles avec modèle — l'utilisateur choisit la famille et règle
les paramètres — mais la réponse est une liste d'essais RÉELS (avec leur source), jamais une
prédiction. Pourquoi pas de modèle : voir DATA_ONLY dans families.py.

    from src.models.model_rf.data_only import DataExplorer
    ex = DataExplorer()                        # ou ml.explorer depuis MLService
    ex.list_families()
    ex.get_parameters("Solides (BASS-II, Saffire)")
    ex.find_tests("Solides (BASS-II, Saffire)", {"material": "sibal", "x_o2": 0.21, ...})
    ex.summary("Solides (BASS-II, Saffire)")
"""
import numpy as np
import pandas as pd

from .data_prep import load_tables, to_features

MODES_FR = {
    "low_flow": "manque d'air (débit trop faible)",
    "blowoff": "soufflage (débit trop fort)",
    "brief_flame": "flamme brève, ne s'installe pas",
    "flow_off": "ventilation coupée",
    "steady_flow": "à débit constant",
}

DATA_FAMILIES = {
    "Solides (BASS-II, Saffire)": {
        "description": "Matériaux solides (PMMA, tissus SIBAL et Nomex, cires) qui brûlent dans un "
                       "courant d'air. Pas de prédiction : l'issue dépend surtout du protocole "
                       "(air réduit jusqu'à l'extinction). On montre les essais réels comparables.",
        "fichier": "solids",
        # BASS (v1) exclu : issue presque jamais renseignée
        "filtre": {"experiment": ["BASS-II", "Saffire-I", "Saffire-II", "Saffire-III"]},
        "parametres": {
            "material": "texte",
            "geometry": "texte",
            "x_o2": "nombre",              # fraction d'O2
            "flow_max_cm_s": "nombre",     # vitesse d'air la plus forte pendant l'essai
        },
        "afficher": ["outcome", "extinction_mode", "extinction_flow_cm_s",
                     "flow_min_cm_s", "flow_max_cm_s", "observations"],
    },
    "Aérosols / fumées (SAME, SAME-R)": {
        "description": "Matériaux de cabine chauffés (sans flamme) pour produire de la fumée, afin de "
                       "concevoir des détecteurs. Pas de prédiction : la table ne contient pas de mesure "
                       "de fumée. On montre les essais réels comparables.",
        "fichier": "aerosols",
        "filtre": {"experiment": ["SAME", "SAME-R"]},
        "parametres": {
            "material": "texte",
            "flow_cm_s": "nombre",         # vitesse de l'air
            "rt_r0": "nombre",             # Rt/R0 = réglage de la température du fil chauffant
        },
        "afficher": ["description", "duration_s", "net_aging_s", "weight_loss_mg_min"],
    },
}
SOURCE_COLS = ["test_id", "experiment", "session", "psi_id", "source_file", "source_line"]


class DataExplorer:
    def __init__(self, tables: dict | None = None):
        tables = tables if tables is not None else load_tables()
        self.rows = {}
        for family, fiche in DATA_FAMILIES.items():
            if fiche["fichier"] not in tables:
                continue
            df = tables[fiche["fichier"]]
            mask = df["gravity"] == "micro"              # microgravité seulement
            for col, values in fiche["filtre"].items():
                mask &= df[col].isin(values)
            self.rows[family] = df[mask].copy()

    def list_families(self) -> list:
        return list(self.rows)

    def get_parameters(self, family: str) -> dict:
        X = to_features(self.rows[family], DATA_FAMILIES[family]["parametres"])
        params = {}
        for col, kind in DATA_FAMILIES[family]["parametres"].items():
            if kind == "nombre":
                v = X[col].dropna()
                params[col] = {"type": "nombre", "min": float(v.min()), "max": float(v.max()),
                               "defaut": float(v.median())}
            else:
                counts = X[col][X[col] != "inconnu"].value_counts()
                params[col] = {"type": "texte", "choix": list(counts.index), "defaut": counts.index[0]}
        return params

    def default_scenario(self, family: str) -> dict:
        return {k: p["defaut"] for k, p in self.get_parameters(family).items()}

    def find_tests(self, family: str, params: dict, k: int = 5) -> dict:
        """Les k essais réels les plus proches de la demande, avec leur source."""
        fiche = DATA_FAMILIES[family]
        rows = self.rows[family]
        types = fiche["parametres"]
        R = to_features(rows, types)
        Q = to_features(pd.DataFrame([params]), types)
        num = [c for c, t in types.items() if t == "nombre"]
        txt = [c for c, t in types.items() if t == "texte"]

        sd = R[num].std().replace(0, 1).fillna(1).to_numpy()
        diff = (R[num].to_numpy() - Q[num].to_numpy()) / sd
        with np.errstate(invalid="ignore"):
            # valeur manquante dans l'essai : ni pour ni contre
            d = np.sqrt(np.nanmean(np.where(np.isnan(diff), np.nan, diff ** 2), axis=1) * len(num))
        d = np.nan_to_num(d, nan=5.0)
        for c in txt:                                    # autre matériau / forme : très éloigné
            d = d + 10 * (R[c].to_numpy() != Q[c].iloc[0])

        order = np.argsort(d)[:k]
        cols = [c for c in SOURCE_COLS + list(types) + fiche["afficher"] if c in rows.columns]
        found = rows.iloc[order][list(dict.fromkeys(cols))].reset_index(drop=True)
        if "extinction_mode" in found:
            found["extinction_mode"] = found["extinction_mode"].map(MODES_FR).fillna(found["extinction_mode"])
        found["distance"] = d[order]

        out = {"famille": family, "parametres": params, "mode": "données réelles (pas de prédiction)",
               "essais_proches": found, "donnee_proche": bool(len(found)) and found["distance"].iloc[0] <= 1.0}
        same = [c for c in txt if (R[c] == Q[c].iloc[0]).sum() == 0]
        if same:
            out["avertissement"] = ("Aucun essai NASA avec ce choix : " + ", ".join(
                f"{c} = {params.get(c)}" for c in same) + ". Les essais montrés sont d'une autre catégorie.")
        elif not out["donnee_proche"]:
            out["avertissement"] = "Aucun essai NASA vraiment proche : les essais montrés sont les moins éloignés."
        return out

    def summary(self, family: str) -> pd.DataFrame:
        """Vue d'ensemble de la famille (pour l'onglet Explorer)."""
        rows = self.rows[family]
        if family.startswith("Solides"):
            s = rows.copy()
            s["mode"] = s["extinction_mode"].map(MODES_FR).fillna("non renseigné")
            table = pd.crosstab([s["experiment"], s["material"], s["geometry"]], s["mode"])
            table.insert(0, "essais", table.sum(axis=1))
            table.insert(1, "O2 testé (%)", s.groupby(["experiment", "material", "geometry"])["x_o2"]
                         .agg(lambda x: f"{100 * x.min():.1f} à {100 * x.max():.1f}" if x.notna().any() else "—"))
            return table.sort_values("essais", ascending=False)
        g = rows.groupby(["experiment", "material"])
        return pd.DataFrame({
            "essais": g.size(),
            "vitesses d'air testées (cm/s)": g["flow_cm_s"].agg(lambda x: ", ".join(f"{v:g}" for v in sorted(x.dropna().unique()))),
            "Rt/R0 (chauffe)": g["rt_r0"].agg(lambda x: f"{x.min():.2f} à {x.max():.2f}" if x.notna().any() else "—"),
        })


# Compatibilité avec la v7
def solids_summary(tables=None):
    return DataExplorer(tables).summary("Solides (BASS-II, Saffire)")


def solids_extinctions(tables=None):
    rows = DataExplorer(tables).rows["Solides (BASS-II, Saffire)"]
    rows = rows[rows["extinction_flow_cm_s"].notna()]
    out = rows[["test_id", "session", "material", "geometry", "x_o2", "extinction_flow_cm_s",
                "extinction_mode", "psi_id", "source_file", "source_line"]].copy()
    out["extinction_mode"] = out["extinction_mode"].map(MODES_FR).fillna("non renseigné")
    return out.sort_values(["material", "x_o2"]).reset_index(drop=True)
