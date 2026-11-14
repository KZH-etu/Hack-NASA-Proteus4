from pathlib import Path
import numpy as np
import pandas as pd
from catboost import CatBoostClassifier
from sklearn.model_selection import GroupShuffleSplit
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

# MODELE : CatBoost Classifier

FOLDER = Path(__file__).resolve().parent
FILES = {'solid': 'solids.parquet', 'gas': 'gas.parquet', 'droplet': 'droplets.parquet', 'aerosol': 'aerosols.parquet'}
CLASS_MAPPING = {
    'extinguished': 'extinction',
    'burned': 'combustion',
    'completion': 'combustion',
    'disruption': 'intermediate',
}
CLASSES = ['extinction', 'combustion', 'intermediate']

# 1. Charger et réunir les expériences.
frames = []
for material_type, filename in FILES.items():
    path = FOLDER / filename
    if not path.is_file():
        raise FileNotFoundError(f'Fichier manquant : {path}')
    df = pd.read_parquet(path)
    df['material_type'] = material_type
    frames.append(df)
data = pd.concat(frames, ignore_index=True)
if 'outcome' not in data:
    raise ValueError('La colonne outcome est absente.')
print('Dimensions initiales :', data.shape)
print('Répartition originale :\n', data['outcome'].value_counts(dropna=False))

# 2. Mapper uniquement les résultats dont le sens a été défini.
data['target_3classes'] = data['outcome'].astype('string').map(CLASS_MAPPING)
data = data.dropna(subset=['target_3classes']).copy()
data['target_3classes'] = data['target_3classes'].astype(str)
print('\nClasses retenues :\n', data['target_3classes'].value_counts())
print('\nPar matériau :\n', pd.crosstab(data['material_type'], data['target_3classes']))

# 3. Exclure les identifiants, les commentaires et les mesures après l'essai.
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
]
X = data.drop(columns=[c for c in EXCLUDED_COLUMNS if c in data.columns]).copy()
y = data['target_3classes']

# 4. Types compatibles CatBoost et gestion des valeurs manquantes.
cat_features = X.select_dtypes(include=['object', 'category', 'string']).columns.tolist()
for col in cat_features:
    X[col] = X[col].astype('string').str.strip().replace('', pd.NA).fillna('Missing').astype(str)
for col in X.columns.difference(cat_features):
    X[col] = pd.to_numeric(X[col], errors='coerce').astype('float64')
    X[col] = X[col].replace([np.inf, -np.inf], np.nan)
empty_cols = [c for c in X.columns if (X[c].eq('Missing').all() if c in cat_features else X[c].isna().all())]
X = X.drop(columns=empty_cols)
cat_features = [c for c in cat_features if c in X.columns]
if X.empty or X.shape[1] == 0:
    raise ValueError('Aucune variable exploitable.')
print('\nVariables retenues :', X.columns.tolist())
print('Colonnes vides retirées :', empty_cols)

# 5. Séparation par groupe : ne pas mélanger les mêmes essais.
if 'test_id' not in data or data['test_id'].isna().any():
    raise ValueError('test_id absent ou incomplet : définir des groupes fiables avant entraînement.')
groups = data['material_type'].astype(str) + '_' + data['test_id'].astype(str)
outer = GroupShuffleSplit(n_splits=1, test_size=0.20, random_state=42)
idx_dev, idx_test = next(outer.split(X, y, groups))
X_dev, y_dev, groups_dev = X.iloc[idx_dev], y.iloc[idx_dev], groups.iloc[idx_dev]
X_test, y_test = X.iloc[idx_test], y.iloc[idx_test]
inner = GroupShuffleSplit(n_splits=1, test_size=0.25, random_state=42)
idx_train, idx_val = next(inner.split(X_dev, y_dev, groups_dev))
X_train, y_train = X_dev.iloc[idx_train], y_dev.iloc[idx_train]
X_val, y_val = X_dev.iloc[idx_val], y_dev.iloc[idx_val]
for name, labels in [('train', y_train), ('validation', y_val), ('test', y_test)]:
    print(f'\n{name} ({len(labels)} lignes) :\n{labels.value_counts()}')
    absent = set(CLASSES) - set(labels)
    if absent:
        raise ValueError(f'Classe(s) absente(s) dans {name}: {absent}. Revoir le découpage.')

# 6. Un seul modèle, trois classes.
model = CatBoostClassifier(
    iterations=2000,
    depth=5,
    learning_rate=0.03,
    l2_leaf_reg=5,
    loss_function='MultiClass',
    eval_metric='MultiClass',
    auto_class_weights='SqrtBalanced',
    random_seed=42,
    verbose=50,
    allow_writing_files=False,
)
model.fit(X_train, y_train, cat_features=cat_features,
          eval_set=(X_val, y_val), early_stopping_rounds=80)

# 7. Trois probabilités par observation : somme = 1.
predictions = model.predict(X_test).ravel()
proba_raw = model.predict_proba(X_test)
probabilities = pd.DataFrame(proba_raw, columns=model.classes_, index=X_test.index)
probabilities = probabilities[CLASSES]
print('\n===== RESULTATS TEST =====')
print('Accuracy :', round(accuracy_score(y_test, predictions), 4))
print('F1 macro :', round(f1_score(y_test, predictions, labels=CLASSES, average='macro', zero_division=0), 4))
print(classification_report(y_test, predictions, labels=CLASSES, zero_division=0))
print('Matrice de confusion (ordre :', CLASSES, ') :\n', confusion_matrix(y_test, predictions, labels=CLASSES))
print('Meilleure itération :', model.best_iteration_)

results = probabilities.rename(columns={
    'extinction': 'P_extinction',
    'combustion': 'P_combustion',
    'intermediate': 'P_intermediaire',
})
results['Actual'] = y_test
results['Predicted'] = predictions
print('\nProbabilités :\n', results.head(10).to_string())

# 8. Sauvegardes.

# Sauvegarder le modèle entraîné
model_path = FOLDER / "catboost_fire_3classes.cbm"
model.save_model(str(model_path))

# Sauvegarder les probabilités et les prédictions
predictions_path = FOLDER / "catboost_test_predictions_3classes.csv"
results.to_csv(predictions_path, index=False)

# Sauvegarder l'importance des variables
importance = pd.DataFrame({
    "Feature": X.columns,
    "Importance": model.feature_importances_
})

importance = importance.sort_values(
    by="Importance",
    ascending=False
)

importance_path = FOLDER / "catboost_feature_importance_3classes.csv"
importance.to_csv(importance_path, index=False)

print("\n===== SAUVEGARDE TERMINÉE =====")
print("Modèle :", model_path)
print("Prédictions :", predictions_path)
print("Importance des variables :", importance_path)

print("\n===== VARIABLES LES PLUS IMPORTANTES =====")
print(importance.head(15).to_string(index=False))