# Module Machine Learning : Nicolas

Architecture officielle Physics-Informed ML (Propriétés thermodynamiques NIST/NASA) pour la sécurité incendie spatiale.

## Modèle & Nomenclature :
- **Artéfact** : `models/pim_flammability_gbt_v1.joblib` (*Physics-Informed Model / Gradient Boosted Trees v1*)
- **Inférence** : `predict.py` -> `predict_fire_safety(o2_percent, pressure_kpa, flow_cm_s, material)`
- **Entraînement & CV** : `train.py` (Validation croisée 5-Fold, seuil calibré Maximin)
- **Démo autonome** : `test_run.py`

## Lancer un test :
```bash
cd machine-learning/nicolas
python test_run.py
```

## Intégration pour Luca (Streamlit Dashboard) :
```python
from machine_learning.nicolas.predict import predict_fire_safety

resultat = predict_fire_safety(o2_percent=34.0, pressure_kpa=70.0, flow_cm_s=5.0, material="pmma")
# Renvoie : is_fire_active, fire_probability, predicted_burning_rate_mm2_s, spacecraft_risk_score, risk_level
```
