# Module Machine Learning : Nicolas

Architecture Physics-Informed ML (Proprietes thermodynamiques de la matiere NIST/NASA) pour la securite incendie spatiale.

## Fichiers inclus :
- `predict.py` : Fonction universelle `predict_fire_safety(o2_percent, pressure_kpa, flow_cm_s, material)`.
- `train.py` : Pipeline complet d entrainement avec validation croisee 5-Fold.
- `models/pim_flammability_gbt_v1.joblib` : Modele serialise pre-entraine.
- `test_run.py` : Script d execution autonome pour tester les scenarios.

## Lancer un test :
```bash
cd machine-learning/nicolas
python test_run.py
```
