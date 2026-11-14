"""Entraînement du modèle CatBoost à 3 classes (script d'origine : catboost_modele_hephaistos_3c_test.py).

Usage :
    python -m src.models.model_catboost.train

Écrit dans ce dossier : catboost_fire_3classes.cbm (modèle utilisé par predict), les prédictions du jeu de test
et l'importance des variables.
"""

import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix, f1_score

from src.models.model_catboost.model import (CLASSES, FOLDER, MODEL_PATH, check_classes, fit_with_early_stopping,
                                             groups_by_test, holdout_split, load_data, prepare_features)

# MODELE : CatBoost Classifier


def main():
    # 1-2. Charger et réunir les expériences ; cible à 3 classes.
    data = load_data()
    print('Dimensions :', data.shape)
    print('\nClasses retenues :\n', data['target_3classes'].value_counts())
    print('\nPar matériau :\n', pd.crosstab(data['material_type'], data['target_3classes']))

    # 3-4. Exclure identifiants, commentaires et mesures après l'essai ; types CatBoost.
    X, y, cat_features, empty_cols = prepare_features(data)
    print('\nVariables retenues :', X.columns.tolist())
    print('Colonnes vides retirées :', empty_cols)

    # 5. Séparation par groupe : ne pas mélanger les mêmes essais.
    groups = groups_by_test(data)
    idx_dev, idx_test = holdout_split(X, y, groups)
    X_dev, y_dev, groups_dev = X.iloc[idx_dev], y.iloc[idx_dev], groups.iloc[idx_dev]
    X_test, y_test = X.iloc[idx_test], y.iloc[idx_test]
    check_classes('test', y_test)

    # 6. Un seul modèle, trois classes.
    model, (y_train, y_val) = fit_with_early_stopping(X_dev, y_dev, groups_dev, cat_features, verbose=50)
    for name, labels in [('train', y_train), ('validation', y_val), ('test', y_test)]:
        print(f'\n{name} ({len(labels)} lignes) :\n{labels.value_counts()}')

    # 7. Trois probabilités par observation : somme = 1.
    predictions = model.predict(X_test).ravel()
    probabilities = pd.DataFrame(model.predict_proba(X_test), columns=model.classes_, index=X_test.index)[CLASSES]
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

    # 8. Sauvegardes : modèle, probabilités et prédictions, importance des variables.
    model.save_model(str(MODEL_PATH))
    predictions_path = FOLDER / "catboost_test_predictions_3classes.csv"
    results.to_csv(predictions_path, index=False)
    importance = pd.DataFrame({"Feature": X.columns, "Importance": model.feature_importances_})
    importance = importance.sort_values(by="Importance", ascending=False)
    importance_path = FOLDER / "catboost_feature_importance_3classes.csv"
    importance.to_csv(importance_path, index=False)

    print("\n===== SAUVEGARDE TERMINÉE =====")
    print("Modèle :", MODEL_PATH)
    print("Prédictions :", predictions_path)
    print("Importance des variables :", importance_path)
    print("\n===== VARIABLES LES PLUS IMPORTANTES =====")
    print(importance.head(15).to_string(index=False))


if __name__ == "__main__":
    main()
