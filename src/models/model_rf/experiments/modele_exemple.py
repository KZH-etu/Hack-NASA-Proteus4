"""MODÈLE EXEMPLE — à copier pour brancher un autre modèle dans la comparaison.

Exemple choisi : les k plus proches voisins (kNN). Pour prédire, on regarde les k essais
les plus ressemblants et on fait la moyenne (ou le vote). L'incertitude = la dispersion
de ces voisins. Il sert surtout de modèle de comparaison simple.

Pour brancher ton propre modèle :
1. copier ce fichier, renommer la classe et `name` ;
2. garder EXACTEMENT les mêmes signatures :
     __init__(self, kind, entrees)        kind = "regression" ou "classification"
     fit(self, X, y) -> self              X = DataFrame (colonnes de la fiche), y = Series
     predict_with_uncertainty(self, X)    voir forêt.py pour le format exact
     self.classes_                        (classification) liste des issues, même ordre que les probas
3. l'ajouter dans tests/compare_models.py.
"""
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.neighbors import NearestNeighbors
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler


class KNNModel:
    name = "k plus proches voisins"

    def __init__(self, kind: str, entrees: dict, k: int = 10):
        self.kind, self.k = kind, k
        num = [c for c, t in entrees.items() if t == "nombre"]
        txt = [c for c, t in entrees.items() if t == "texte"]
        self.prep = ColumnTransformer([
            ("num", make_pipeline(SimpleImputer(strategy="median"), StandardScaler()), num),
            ("txt", OneHotEncoder(handle_unknown="ignore", sparse_output=False), txt),
        ])

    def fit(self, X, y):
        Xt = self.prep.fit_transform(X)
        self.nn = NearestNeighbors(n_neighbors=min(self.k, len(Xt))).fit(Xt)
        self.y_ = np.asarray(y)
        if self.kind == "classification":
            self.classes_ = sorted(set(self.y_))
        return self

    def predict_with_uncertainty(self, X):
        _, idx = self.nn.kneighbors(self.prep.transform(X))
        neigh = self.y_[idx]                                        # n x k
        if self.kind == "regression":
            neigh = neigh.astype(float)
            # incertitude = dispersion des valeurs des voisins
            return neigh.mean(axis=1), neigh.std(axis=1)
        onehot = np.stack([(neigh == c).astype(float) for c in self.classes_], axis=2)  # n x k x classes
        return onehot.mean(axis=1), onehot.std(axis=1) / np.sqrt(neigh.shape[1])
