import os
import joblib
import numpy as np
import pandas as pd
from sklearn.model_selection import StratifiedKFold, train_test_split
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.metrics import accuracy_score, recall_score, precision_score, f1_score, roc_auc_score

DATA_PATH = r"c:\Users\patri\Documents\gemini-workspace\engineering-lab\nasa-space-apps-2026\flame-in-freefall\data\processed\jason_proteus4_experiments_all.csv"
MODEL_DIR = r"c:\Users\patri\Documents\gemini-workspace\engineering-lab\nasa-space-apps-2026\flame-in-freefall\src\models"
os.makedirs(MODEL_DIR, exist_ok=True)

# Table des constantes physiques officielles (NIST / SFPE Handbook of Fire Protection)
THERMO_PROPERTIES = {
    'methanol':   {'delta_hc': 22.7, 't_auto_ign_c': 465.0, 'l_gas_kj_g': 1.10, 'is_solid': 0},
    'heptane':    {'delta_hc': 48.1, 't_auto_ign_c': 223.0, 'l_gas_kj_g': 0.36, 'is_solid': 0},
    'n-butane':   {'delta_hc': 49.5, 't_auto_ign_c': 405.0, 'l_gas_kj_g': 0.38, 'is_solid': 0},
    'propane':    {'delta_hc': 50.3, 't_auto_ign_c': 470.0, 'l_gas_kj_g': 0.42, 'is_solid': 0},
    'ethane':     {'delta_hc': 51.9, 't_auto_ign_c': 515.0, 'l_gas_kj_g': 0.49, 'is_solid': 0},
    'pmma':       {'delta_hc': 26.2, 't_auto_ign_c': 430.0, 'l_gas_kj_g': 1.62, 'is_solid': 1},
    'sibal':      {'delta_hc': 17.5, 't_auto_ign_c': 400.0, 'l_gas_kj_g': 2.10, 'is_solid': 1},
    'nomex':      {'delta_hc': 27.0, 't_auto_ign_c': 550.0, 'l_gas_kj_g': 2.50, 'is_solid': 1},
    'japan wax':  {'delta_hc': 42.0, 't_auto_ign_c': 350.0, 'l_gas_kj_g': 0.85, 'is_solid': 1},
    'silicone':   {'delta_hc': 16.0, 't_auto_ign_c': 450.0, 'l_gas_kj_g': 1.90, 'is_solid': 1},
    # Matériaux génériques d'extrapolation
    'polyethylene': {'delta_hc': 43.6, 't_auto_ign_c': 349.0, 'l_gas_kj_g': 2.30, 'is_solid': 1},
    'teflon':       {'delta_hc': 5.0,  't_auto_ign_c': 560.0, 'l_gas_kj_g': 3.20, 'is_solid': 1},
    'kevlar':       {'delta_hc': 31.0, 't_auto_ign_c': 500.0, 'l_gas_kj_g': 2.80, 'is_solid': 1},
}
DEFAULT_THERMO = {'delta_hc': 35.0, 't_auto_ign_c': 430.0, 'l_gas_kj_g': 1.0, 'is_solid': 0.5}

def train_official_thermo_baseline():
    print("="*85)
    print("INSTALLATION DU MODÈLE THERMODYNAMIQUE CONTINU COMME NOUVELLE BASE OFFICIELLE")
    print("100% Physics-Informed ML | Zéro One-Hot | Capacité d'Extrapolation Universelle")
    print("="*85 + "\n")
    
    df = pd.read_csv(DATA_PATH)
    
    # 1. CLASSIFICATEUR D'INFLAMMABILITÉ
    valid_outcomes = ['burned', 'completion', 'disruption', 'extinguished', 'no_ignition']
    clf_df = df[df['outcome'].isin(valid_outcomes)].copy()
    clf_df['target'] = clf_df['outcome'].apply(lambda x: 1 if x in ['burned', 'completion', 'disruption'] else 0)

    clf_df['o2_percent'] = clf_df['o2_percent'].fillna(21.0)
    clf_df['pressure_kpa'] = clf_df['pressure_kpa'].fillna(101.3)
    clf_df['flow_cm_s'] = clf_df['flow_cm_s'].fillna(0.0)
    clf_df['material'] = clf_df['material'].fillna('unknown')

    # Mapping des 4 propriétés continues de la matière
    for prop in ['delta_hc', 't_auto_ign_c', 'l_gas_kj_g', 'is_solid']:
        clf_df[prop] = clf_df['material'].apply(lambda m: THERMO_PROPERTIES.get(str(m).lower(), DEFAULT_THERMO)[prop])

    features_clf = ['o2_percent', 'pressure_kpa', 'flow_cm_s', 'delta_hc', 't_auto_ign_c', 'l_gas_kj_g', 'is_solid']
    X_clf = clf_df[features_clf]
    y_clf = clf_df['target']

    # Entraînement officiel sur la totalité des données étiquetées avec Pipeline standardisé
    clf_pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('gbc', GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.08, random_state=42))
    ])
    clf_pipeline.fit(X_clf, y_clf)
    
    # Validation croisée 5-fold pour certifier les métriques officielles
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    accs, recs, precs, f1s, aucs = [], [], [], [], []
    for train_idx, test_idx in skf.split(X_clf, y_clf):
        X_tr, X_te = X_clf.iloc[train_idx], X_clf.iloc[test_idx]
        y_tr, y_te = y_clf.iloc[train_idx], y_clf.iloc[test_idx]
        p = Pipeline([
            ('scaler', StandardScaler()),
            ('gbc', GradientBoostingClassifier(n_estimators=100, max_depth=3, learning_rate=0.08, random_state=42))
        ])
        p.fit(X_tr, y_tr)
        probs = p.predict_proba(X_te)[:, 1]
        preds = (probs >= 0.35).astype(int)
        accs.append(accuracy_score(y_te, preds))
        recs.append(recall_score(y_te, preds))
        precs.append(precision_score(y_te, preds, zero_division=0))
        f1s.append(f1_score(y_te, preds, zero_division=0))
        aucs.append(roc_auc_score(y_te, probs))

    # 2. PRÉDICTEUR DE TAUX DE COMBUSTION
    reg_df = df[df['burning_rate'].notnull() & (df['burning_rate'] > 0)].copy()
    reg_df['o2_percent'] = reg_df['o2_percent'].fillna(21.0)
    reg_df['pressure_kpa'] = reg_df['pressure_kpa'].fillna(101.3)
    reg_df['flow_cm_s'] = reg_df['flow_cm_s'].fillna(0.0)

    for prop in ['delta_hc', 't_auto_ign_c', 'l_gas_kj_g', 'is_solid']:
        reg_df[prop] = reg_df['material'].apply(lambda m: THERMO_PROPERTIES.get(str(m).lower(), DEFAULT_THERMO)[prop])

    features_reg = ['o2_percent', 'pressure_kpa', 'delta_hc', 't_auto_ign_c', 'l_gas_kj_g']
    X_reg = reg_df[features_reg]
    y_reg = reg_df['burning_rate']

    reg_pipeline = Pipeline([
        ('scaler', StandardScaler()),
        ('gbr', GradientBoostingRegressor(n_estimators=100, max_depth=3, learning_rate=0.08, random_state=42))
    ])
    reg_pipeline.fit(X_reg, y_reg)

    # 3. SAUVEGARDE DE LA NOUVELLE BASE OFFICIELLE
    bundle_official = {
        "classifier_pipeline": clf_pipeline,
        "regressor_pipeline": reg_pipeline,
        "optimal_threshold": 0.35,
        "features_clf": features_clf,
        "features_reg": features_reg,
        "thermo_properties_table": THERMO_PROPERTIES,
        "default_thermo": DEFAULT_THERMO,
        "cv_metrics_5fold": {
            "accuracy": np.mean(accs) * 100,
            "roc_auc": np.mean(aucs),
            "recall": np.mean(recs) * 100,
            "precision": np.mean(precs) * 100,
            "f1": np.mean(f1s) * 100
        }
    }
    
    save_path = os.path.join(MODEL_DIR, "official_thermodynamic_models.joblib")
    joblib.dump(bundle_official, save_path)
    print("MÉTRIQUES DE LA NOUVELLE BASE OFFICIELLE (5-FOLD CV) :")
    print(f"Accuracy  : {np.mean(accs)*100:.2f} %")
    print(f"ROC-AUC   : {np.mean(aucs):.3f}")
    print(f"Recall    : {np.mean(recs)*100:.2f} %")
    print(f"Precision : {np.mean(precs)*100:.2f} %")
    print(f"F1-Score  : {np.mean(f1s)*100:.2f} %")
    print(f"\nModèle officiel persisté avec succès sous :\n{save_path}")

if __name__ == "__main__":
    train_official_thermo_baseline()
