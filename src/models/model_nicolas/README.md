# Model Nicolas : Physics-Informed ML

Architecture officielle Physics-Informed ML (Proprietes thermodynamiques de la matiere NIST/NASA) pour la securite incendie spatiale.

## Fichiers inclus :
- `predict.py` : Fonction universelle `predict_fire_safety(o2_percent, pressure_kpa, flow_cm_s, material)`.
- `train.py` : Pipeline complet d entrainement avec validation croisee 5-Fold.
- `models/pim_flammability_gbt_v1.joblib` : Modele serialise pre-entraine.
- `test_run.py` : Script d execution autonome pour tester les scenarios.

## Lancer un test :
```bash
cd src/models/model_nicolas
python test_run.py
```

## Integration pour Luca (Streamlit Dashboard) :
```python
from src.models.model_nicolas.predict import predict_fire_safety

resultat = predict_fire_safety(o2_percent=34.0, pressure_kpa=70.0, flow_cm_s=5.0, material="pmma")
```
