"""Modèle CatBoost à 3 classes (extinction / combustion / intermédiaire), toutes familles réunies.

La logique du modèle est celle du script d'origine (test_modele_catboost_3c/catboost_modele_hephaistos_3c_test.py) :
mêmes classes, mêmes variables exclues, même préparation des colonnes, mêmes hyperparamètres, même découpage.
Ce qui change :
- les données sont lues dans data/processed/families (load_family) au lieu de copies dans le dossier du modèle ;
- trois colonnes ajoutées depuis à la table des solides (extinction_flow_cm_s, extinction_mode, extinction_pot)
  sont exclues, comme les autres mesures faites après l'essai ;
- predict() suit l'interface commune des modèles (src/models/README.md).

Entraînement : python -m src.models.model_catboost.train ; validation : python -m src.models.model_catboost.evaluate.
"""

from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.model_selection import GroupShuffleSplit

from src.data.build_unified import load_family

FOLDER = Path(__file__).resolve().parent
MODEL_PATH = FOLDER / "catboost_fire_3classes.cbm"

# Familles de données : valeur de material_type -> table de data/processed/families
FILES = {'solid': 'solids', 'gas': 'gas', 'droplet': 'droplets', 'aerosol': 'aerosols'}
CLASS_MAPPING = {
    'extinguished': 'extinction',
    'burned': 'combustion',
    'completion': 'combustion',
    'disruption': 'intermediate',
}
CLASSES = ['extinction', 'combustion', 'intermediate']

# Identifiants, commentaires et mesures après l'essai.
EXCLUDED_COLUMNS = [
    'outcome', 'target_3classes',
    'psi_id', 'test_id', 'session', 'test_date', 'pi', 'sample_no',
    'source_file', 'source_line', 'experiment', 'gmt_day',
    'cir_identifier', 'test_time_gmt', 'parent_test', 'date_raw',
    'material_raw', 'flow_raw', 'fan_raw', 'fuel_label_raw',
    'observations', 'qc_flags', 'comments', 'description',
    'x_o2_final', 'co2_final_pct', 'co_final_ppm', 'x_fuel_final',
    'pressure_final_kpa', 'burn_time_s', 'burn_length_cm',
    'burn_complete', 'spread_rate_mm_s', 'spread_mode',
    'burning_rate_mm2_s', 'weight_loss_mg_min', 'peak_burner_T_K',
    'flame_color', 'end_mode_raw', 'test_end_raw', 'hot_ignition_raw',
    'cool_flame', 'tfp', 'sides_burning', 'flow_min_cm_s',
    'flow_max_cm_s', 'ignition_time_s',
    # Colonnes ajoutées à la table des solides après l'écriture du modèle (conditions d'extinction) :
    # mesures après l'essai, exclues par la même règle.
    'extinction_flow_cm_s', 'extinction_mode', 'extinction_pot',
]

CATBOOST_PARAMS = dict(
    iterations=2000,
    depth=5,
    learning_rate=0.03,
    l2_leaf_reg=5,
    loss_function='MultiClass',
    eval_metric='MultiClass',
    auto_class_weights='SqrtBalanced',
    random_seed=42,
    allow_writing_files=False,
)
EARLY_STOPPING_ROUNDS = 80

# Fiabilité mesurée en validation par jour d'essai (voir validation.md), affichée avec chaque prédiction.
RELIABILITY = ("moyenne : en validation par jour d'essai, exactitude 0,77 (référence naïve 0,70), F1 macro 0,65, MCC 0,45 ; "
               "la classe « combustion » est mal reconnue (rappel 0,27) ; gouttelettes : une entrée (d_ext_mm) est mesurée "
               "après l'essai et reste vide avant ; voir src/models/model_catboost/validation.md")


# ---------- Données ----------

def load_data():
    """Expériences des quatre familles réunies, avec la cible à 3 classes (lignes sans classe définie retirées)."""
    frames = []
    for material_type, family in FILES.items():
        df = load_family(family)
        df['material_type'] = material_type
        frames.append(df)
    data = pd.concat(frames, ignore_index=True)
    if 'outcome' not in data:
        raise ValueError('La colonne outcome est absente.')
    # Mapper uniquement les résultats dont le sens a été défini.
    data['target_3classes'] = data['outcome'].astype('string').map(CLASS_MAPPING)
    data = data.dropna(subset=['target_3classes']).copy()
    data['target_3classes'] = data['target_3classes'].astype(str)
    return data


def clean_columns(X, cat_features):
    """Types compatibles CatBoost et valeurs manquantes (catégories vides -> 'Missing', nombres -> NaN)."""
    X = X.copy()
    for col in cat_features:
        X[col] = X[col].astype('string').str.strip().replace('', pd.NA).fillna('Missing').astype(str)
    for col in X.columns.difference(cat_features):
        X[col] = pd.to_numeric(X[col], errors='coerce').astype('float64')
        X[col] = X[col].replace([np.inf, -np.inf], np.nan)
    return X


def prepare_features(data, extra_excluded=()):
    """X, y, variables catégorielles et colonnes vides retirées. extra_excluded : diagnostic seulement."""
    excluded = EXCLUDED_COLUMNS + list(extra_excluded)
    X = data.drop(columns=[c for c in excluded if c in data.columns]).copy()
    y = data['target_3classes']
    cat_features = X.select_dtypes(include=['object', 'category', 'string']).columns.tolist()
    X = clean_columns(X, cat_features)
    empty_cols = [c for c in X.columns if (X[c].eq('Missing').all() if c in cat_features else X[c].isna().all())]
    X = X.drop(columns=empty_cols)
    cat_features = [c for c in cat_features if c in X.columns]
    if X.empty or X.shape[1] == 0:
        raise ValueError('Aucune variable exploitable.')
    return X, y, cat_features, empty_cols


def groups_by_test(data):
    """Groupes du découpage d'origine : un essai (famille + test_id) n'est jamais coupé en deux."""
    if 'test_id' not in data or data['test_id'].isna().any():
        raise ValueError('test_id absent ou incomplet : définir des groupes fiables avant entraînement.')
    return data['material_type'].astype(str) + '_' + data['test_id'].astype(str)


# ---------- Entraînement ----------

def check_classes(name, labels):
    absent = set(CLASSES) - set(labels)
    if absent:
        raise ValueError(f'Classe(s) absente(s) dans {name}: {absent}. Revoir le découpage.')


def fit_with_early_stopping(X_dev, y_dev, groups_dev, cat_features, verbose=0):
    """Découpe dev en entraînement / validation (25 %, par groupe) et entraîne avec arrêt anticipé."""
    inner = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
    idx_train, idx_val = next(inner.split(X_dev, y_dev, groups_dev))
    X_train, y_train = X_dev.iloc[idx_train], y_dev.iloc[idx_train]
    X_val, y_val = X_dev.iloc[idx_val], y_dev.iloc[idx_val]
    check_classes('train', y_train)
    check_classes('validation', y_val)
    model = CatBoostClassifier(**CATBOOST_PARAMS, verbose=verbose)
    model.fit(X_train, y_train, cat_features=cat_features, eval_set=(X_val, y_val),
              early_stopping_rounds=EARLY_STOPPING_ROUNDS)
    return model, (y_train, y_val)


def holdout_split(X, y, groups):
    """Découpage d'origine : 20 % des essais en test (par groupe)."""
    outer = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
    return next(outer.split(X, y, groups))


# ---------- Prédiction ----------

FAMILY_TYPES = {'droplets': 'droplet', 'solids': 'solid', 'gas': 'gas'}


@lru_cache(maxsize=1)
def trained_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"{MODEL_PATH} absent : lancer python -m src.models.model_catboost.train")
    model = CatBoostClassifier()
    model.load_model(str(MODEL_PATH))
    return model


@lru_cache(maxsize=1)
def training_data():
    return load_data()


def _same_composition(gas, fuel, flame_type, x_fuel, x_o2):
    g = gas[(gas['fuel'].astype(str) == fuel) & (gas['flame_type'].astype(str) == flame_type)]
    return g[np.isclose(g['x_fuel'].astype(float), x_fuel, atol=5e-4) & np.isclose(g['x_o2'].astype(float), x_o2, atol=5e-4)]


def conditions_to_row(family, conditions):
    """Traduit des conditions (clés communes aux modèles, voir README) en une ligne de variables du modèle.

    Retourne (ligne, notes). Toute clé qui porte exactement le nom d'une variable du modèle est prise telle quelle.
    Rien n'est inventé : une variable inconnue reste vide (catégorie 'Missing' ou NaN, comme à l'entraînement).
    """
    if family not in FAMILY_TYPES:
        raise ValueError(f"famille « {family} » non couverte ; choisir parmi {list(FAMILY_TYPES)}")
    c = dict(conditions)
    notes = []
    row = {'material_type': FAMILY_TYPES[family], 'gravity': c.get('gravity', 'micro')}
    if 'o2_percent' in c:
        row['x_o2'] = c['o2_percent'] / 100
    if 'pressure_kpa' in c:
        row['pressure_kpa'] = c['pressure_kpa']

    if family == 'droplets':
        o2, co2, he = c['o2_percent'] / 100, c.get('co2_percent', 0.0) / 100, c.get('he_percent', 0.0) / 100
        row.update(fuel=c.get('fuel', 'heptane').lower(), x_co2=co2, x_he=he, d0_mm=c.get('d0_mm', 3.0))
        row['x_n2'] = 1 - o2 - co2 - he
        row['diluent'] = 'N2+CO2' if co2 > 0 else ('N2+He' if he > 0 else 'N2')
        row['fuel_main_fraction'] = 1.0
        notes.append("x_n2 déduit (1 − O2 − CO2 − He) et diluant déduit du CO2 / He, comme dans les données")
        notes.append("d_ext_mm (diamètre à l'extinction, mesuré après l'essai) est une entrée du modèle : "
                     "inconnu avant l'essai, il reste vide")
    elif family == 'solids':
        material = str(c.get('material', 'pmma')).lower()
        if material.startswith('pmma'):
            material = 'pmma'  # noms de classes de model_gp (pmma_flat, pmma_thin...) -> matériau de la table
        row['material'] = material
        if 'flow_cm_s' in c:
            row['flow_cm_s'] = c['flow_cm_s']
    elif family == 'gas':
        fuel, flame_type = c.get('fuel', 'propane').lower(), c.get('flame_type', 'normal')
        row.update(fuel=fuel, flame_type=flame_type, x_fuel=c.get('x_fuel'), hc_rate_mg_s=c.get('hc_rate_mg_s'))
        # z_st et t_ad_K ont été calculés par l'équipe ACME ; on les reprend d'essais réels de même composition
        # (z_st ne dépend que de la composition, t_ad_K aussi de la pression) ; sinon ils restent vides.
        if row['x_fuel'] is not None and 'x_o2' in row and 'z_st' not in c:
            gas = training_data()
            same = _same_composition(gas[gas['material_type'] == 'gas'], fuel, flame_type, row['x_fuel'], row['x_o2'])
            if len(same):
                row['z_st'] = float(same['z_st'].astype(float).median())
                near_p = same[(same['pressure_kpa'].astype(float) - row.get('pressure_kpa', np.nan)).abs() <= 10]
                if len(near_p):
                    row['t_ad_K'] = float(near_p['t_ad_K'].astype(float).median())
                notes.append(f"z_st{' et t_ad_K' if len(near_p) else ''} repris de {len(same)} essai(s) réel(s) "
                             "de même composition")
            else:
                notes.append("z_st et t_ad_K (calculés par l'équipe ACME) : aucun essai de même composition, laissés vides")

    model_columns = trained_model().feature_names_
    for key, value in c.items():
        if key in model_columns:
            row[key] = value
    return row, notes


def predict(family, conditions):
    """Probabilités des 3 classes pour une famille ('droplets', 'solids', 'gas') et des conditions d'essai."""
    model = trained_model()
    columns = model.feature_names_
    cat_features = [columns[i] for i in model.get_cat_feature_indices()]
    row, notes = conditions_to_row(family, conditions)
    X = clean_columns(pd.DataFrame([{col: row.get(col) for col in columns}]), cat_features)
    proba = dict(zip(model.classes_, model.predict_proba(X)[0]))
    probabilities = {k: round(float(proba[k]), 3) for k in CLASSES}

    warnings = ["pas d'intervalle d'incertitude : CatBoost donne une probabilité ponctuelle"] + notes
    data = training_data()
    fam = data[data['material_type'] == FAMILY_TYPES[family]]
    for col in columns:
        if col in cat_features or col not in fam:
            continue
        value, known = X.at[0, col], fam[col].astype(float).dropna()
        if np.isnan(value):
            if len(known) == len(fam) and col != 'd_ext_mm':
                warnings.append(f"{col} inconnu alors qu'il est toujours renseigné à l'entraînement pour cette famille")
        elif len(known) and not known.min() <= value <= known.max():
            warnings.append(f"{col} = {value:g} hors des essais de cette famille ({known.min():g}–{known.max():g}) : extrapolation")
    return {
        "model": "model_catboost",
        "family": family,
        "probabilities": probabilities,
        "p_extinction": probabilities['extinction'],
        "predicted_class": max(probabilities, key=probabilities.get),
        "inputs_used": {k: v for k, v in X.iloc[0].items() if not (isinstance(v, float) and np.isnan(v)) and v != 'Missing'},
        "reliability": RELIABILITY,
        "warnings": warnings,
    }
