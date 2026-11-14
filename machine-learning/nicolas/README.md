# Module Machine Learning : Nicolas

Architecture officielle Physics-Informed ML (Proprietes thermodynamiques de la matiere NIST/NASA) pour la securite incendie spatiale.

## Fichiers inclus :
- `predict.py` : Fonction universelle `predict_fire_safety(o2_percent, pressure_kpa, flow_cm_s, material)`.
- `train.py` : Pipeline complet re-entrainable avec validation croisee 5-Fold.
- `models/official_thermodynamic_models.joblib` : Modeles serialises pre-entraines.
- `test_run.py` : Script d execution autonome en une ligne pour tester les scenarios.

## Comment faire tourner ce modele ?
```bash
cd machine-learning/nicolas
python test_run.py
```

## Integration pour Luca (Streamlit Dashboard) :
```python
from machine_learning.nicolas.predict import predict_fire_safety

resultat = predict_fire_safety(o2_percent=34.0, pressure_kpa=70.0, flow_cm_s=5.0, material="pmma")
# resultat contient : is_fire_active, fire_probability, predicted_burning_rate_mm2_s, spacecraft_risk_score, risk_level
```
