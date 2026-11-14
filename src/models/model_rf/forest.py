"""Le modèle : forêt aléatoire avec incertitude.

INTERFACE COMMUNE (tout autre modèle de l'équipe doit la respecter pour être comparé) :
    model = ForestModel(kind, entrees).fit(X, y)
    model.predict_with_uncertainty(X)

    - regression     -> (moyenne, ecart_type)           deux tableaux de taille n
    - classification -> (probas, ecart_type)             deux tableaux n x nb_classes,
                        colonnes dans l'ordre de model.classes_

Comment l'incertitude est calculée : on demande à CHAQUE arbre sa réponse.
Si les arbres sont d'accord, l'écart-type est petit ; s'ils se contredisent, il est grand.

Deux améliorations (activées par défaut) :
1. balanced=True : les issues rares (ex. extinction) comptent autant que les fréquentes.
2. calibrate=True (régression) : les fourchettes sont élargies pour être honnêtes.
   On utilise les arbres qui n'ont PAS vu un essai (« out-of-bag ») pour mesurer de combien
   ils se trompent vraiment, puis on agrandit l'écart-type d'autant.
   Tout se fait à l'intérieur de fit() : l'évaluation reste honnête.
"""
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder

TARGET_COVERAGE = 0.95


class ForestModel:
    name = "Forêt aléatoire"

    def __init__(self, kind: str, entrees: dict, n_trees: int = 300,
                 balanced: bool = True, calibrate: bool = True):
        self.kind = kind
        self.calibrate = calibrate
        self.scale_ = 1.0  # facteur d'élargissement des fourchettes (1 = pas de correction)
        num = [c for c, t in entrees.items() if t == "nombre"]
        txt = [c for c, t in entrees.items() if t == "texte"]
        # Les arbres ne comprennent que des nombres :
        # - colonnes numériques : valeur manquante -> médiane (pour le calcul seulement)
        # - colonnes texte : une colonne 0/1 par valeur (« one-hot »)
        self.prep = ColumnTransformer([
            ("num", SimpleImputer(strategy="median"), num),
            ("txt", OneHotEncoder(handle_unknown="ignore"), txt),
        ])
        # min_samples_leaf=2 : chaque feuille contient au moins 2 essais (moins d'apprentissage par cœur)
        if kind == "regression":
            self.forest = RandomForestRegressor(n_estimators=n_trees, min_samples_leaf=2, random_state=0)
        else:
            self.forest = RandomForestClassifier(
                n_estimators=n_trees, min_samples_leaf=2, random_state=0,
                class_weight="balanced_subsample" if balanced else None)

    def fit(self, X, y):
        Xt = self.prep.fit_transform(X)
        self.forest.fit(Xt, y)
        if self.kind == "classification":
            self.classes_ = list(self.forest.classes_)
        elif self.calibrate:
            self.scale_ = self._calibration_scale(Xt, np.asarray(y, dtype=float))
        return self

    def _calibration_scale(self, Xt, y):
        """De combien faut-il élargir les fourchettes pour couvrir 95 % des cas ?"""
        trees = self.forest.estimators_
        n = len(y)
        preds = np.stack([t.predict(Xt) for t in trees])            # arbres x n
        oob = np.ones_like(preds, dtype=bool)                        # True = l'arbre n'a pas vu l'essai
        for i, sample in enumerate(self.forest.estimators_samples_):
            oob[i, sample] = False
        counts = oob.sum(axis=0)
        ok = counts >= 5                                             # assez d'arbres « aveugles »
        if ok.sum() < 5:
            return 1.0
        p = np.where(oob, preds, np.nan)[:, ok]
        mean, std = np.nanmean(p, axis=0), np.nanstd(p, axis=0)
        eps = 1e-6 + 0.01 * np.std(y)
        ratio = np.abs(y[ok] - mean) / (std + eps)                   # erreur réelle / erreur annoncée
        level = min(1.0, np.ceil((ok.sum() + 1) * TARGET_COVERAGE) / ok.sum())
        needed = np.quantile(ratio, level)                           # 95 % des erreurs passent sous ce seuil
        return max(1.0, needed / 1.96)                               # on ne rétrécit jamais

    def predict_with_uncertainty(self, X):
        Xt = self.prep.transform(X)
        trees = self.forest.estimators_
        if self.kind == "regression":
            per_tree = np.stack([t.predict(Xt) for t in trees])           # arbres x n
            return per_tree.mean(axis=0), per_tree.std(axis=0) * self.scale_
        per_tree = np.stack([t.predict_proba(Xt) for t in trees])         # arbres x n x classes
        return per_tree.mean(axis=0), per_tree.std(axis=0)


class ForestModelBasic(ForestModel):
    """Ancienne version (sans les améliorations), gardée pour comparer avant/après."""
    name = "Forêt (version de base)"

    def __init__(self, kind, entrees, **kw):
        super().__init__(kind, entrees, balanced=False, calibrate=False, **kw)


class TunedForestModel(ForestModel):
    """Forêt qui choisit elle-même ses réglages, SANS jamais regarder les données de test.

    Dans fit(), on refait un mini-examen interne sur les seules données d'entraînement
    (sessions entières mises de côté), on essaie quelques réglages fixés à l'avance,
    et on garde le meilleur. Le vrai examen (evaluate.py) reste donc honnête :
    c'est ce qu'on appelle une validation « imbriquée ».

    Réglages testés (liste fixée a priori, volontairement petite) :
    - min_samples_leaf : taille minimale d'une feuille. Grand = réponses plus prudentes,
      proches de la moyenne ; petit = plus de détails, plus de risque d'apprendre par cœur.
    - max_features : part des paramètres que chaque arbre regarde à chaque question.
      Petit = arbres plus différents entre eux (meilleure incertitude).
    """
    name = "Forêt aléatoire réglée"
    uses_groups = True
    GRID = [{"min_samples_leaf": leaf, "max_features": feat}
            for leaf in (1, 3, 8, 15) for feat in ("sqrt", 0.6, 1.0)]

    def fit(self, X, y, groups=None):
        from sklearn.base import clone
        from sklearn.metrics import balanced_accuracy_score, mean_absolute_error
        from sklearn.model_selection import GroupKFold, KFold

        if groups is not None and pd.Series(groups).nunique() >= 3:
            splits = list(GroupKFold(n_splits=3).split(X, groups=groups))
        else:
            splits = list(KFold(n_splits=3, shuffle=True, random_state=0).split(X))

        Xt = self.prep.fit_transform(X)
        y_arr = np.asarray(y)
        best, best_score = None, -np.inf
        for params in self.GRID:
            scores = []
            for tr, te in splits:
                f = clone(self.forest).set_params(n_estimators=100, n_jobs=-1, **params)
                f.fit(Xt[tr], y_arr[tr])
                pred = f.predict(Xt[te])
                if self.kind == "regression":
                    scores.append(-mean_absolute_error(y_arr[te], pred))
                else:
                    scores.append(balanced_accuracy_score(y_arr[te], pred))
            if np.mean(scores) > best_score:
                best, best_score = params, np.mean(scores)

        self.best_params_ = best
        self.forest.set_params(**best)
        return super().fit(X, y)


class OversampledForest(ForestModel):
    """Forêt + OVERSAMPLING ALÉATOIRE (classification) : on recopie au hasard les essais
    des issues rares jusqu'à ce que chaque issue ait autant d'essais que la plus fréquente.

    La copie se fait DANS fit(), donc seulement sur les données d'entraînement :
    aucune copie d'un essai de test ne peut se retrouver à l'entraînement.
    Pas de pondération en plus (sinon les issues rares compteraient deux fois).
    """
    name = "Forêt + oversampling aléatoire"

    def __init__(self, kind, entrees, **kw):
        super().__init__(kind, entrees, balanced=False, **kw)

    def _resample(self, X, y, rng):
        y = pd.Series(np.asarray(y), index=X.index)
        target = y.value_counts().max()
        idx = []
        for c, n in y.value_counts().items():
            members = np.flatnonzero(y.to_numpy() == c)
            idx.extend(members)
            idx.extend(rng.choice(members, size=target - n, replace=True))
        idx = np.asarray(idx)
        return X.iloc[idx].reset_index(drop=True), y.iloc[idx].reset_index(drop=True)

    def fit(self, X, y):
        if self.kind == "classification":
            X, y = self._resample(X, y, np.random.default_rng(0))
        return super().fit(X, y)


class SmoteForest(OversampledForest):
    """Forêt + SMOTE (classification) : au lieu de recopier, on CRÉE des essais rares
    artificiels « entre » deux essais rares voisins (nombres interpolés au hasard ;
    texte copié du premier essai). Les essais artificiels ne servent qu'à l'entraînement,
    jamais à l'évaluation ni à l'affichage.
    """
    name = "Forêt + SMOTE"
    K = 5

    def _resample(self, X, y, rng):
        y = np.asarray(y)
        num = [c for c in X.columns if X[c].dtype.kind == "f"]
        filled = X[num].fillna(X[num].median())
        scale = filled.std().replace(0, 1)
        target = pd.Series(y).value_counts().max()
        new_X, new_y = [X], [y]
        for c, n in pd.Series(y).value_counts().items():
            members = np.flatnonzero(y == c)
            if n == target or len(members) < 2:
                continue
            Z = (filled.iloc[members] / scale).to_numpy()
            d = np.linalg.norm(Z[:, None, :] - Z[None, :, :], axis=2)
            np.fill_diagonal(d, np.inf)
            neigh = np.argsort(d, axis=1)[:, :min(self.K, len(members) - 1)]
            a = rng.integers(0, len(members), size=target - n)
            b = neigh[a, rng.integers(0, neigh.shape[1], size=len(a))]
            u = rng.random((len(a), 1))
            base = X.iloc[members[a]].reset_index(drop=True).copy()
            fa = filled.iloc[members[a]].to_numpy()
            fb = filled.iloc[members[b]].to_numpy()
            base[num] = fa + u * (fb - fa)
            new_X.append(base)
            new_y.append(np.full(len(a), c))
        return pd.concat(new_X, ignore_index=True), pd.Series(np.concatenate(new_y))


def model_for(family: str, output: str, default=ForestModel):
    """Classe de modèle à utiliser pour (famille, sortie) : voir MODEL_OVERRIDES dans families.py."""
    from .families import MODEL_OVERRIDES
    name = MODEL_OVERRIDES.get((family, output))
    return globals()[name] if name else default
