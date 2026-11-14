# Modèle PIM GBT v1 (Physics-Informed Flame Modeling)

Sous-module d'inférence thermodynamique pour la prédiction d'inflammabilité et de taux de combustion en microgravité (NASA PSI).

## Approche Technique
Le modèle intègre les constantes physico-chimiques tabulées de la matière (NIST / SFPE) :
- Chaleur de combustion $\Delta H_c$ (kJ/g)
- Température d'auto-inflammation $T_{ign}$ (°C)
- Chaleur latente de gazéification / pyrolyse $L_v$ (kJ/g)
- État physique initial (solide vs fluide)

Cette formulation permet l'extrapolation à des matériaux inédits non testés sur l'ISS (*zero-shot generalization*).

## Architecture
- **Classification d'inflammabilité** : `GradientBoostingClassifier` (`max_depth=3`, $\eta=0.08$, seuil calibré $\theta=0.35$).
- **Régression continue** : `GradientBoostingRegressor` (`max_depth=3`, perte $L_2$).
- **Validation** : Stratified 5-Fold Cross-Validation sur 722 essais étiquetés de la base NASA PSI.

## Performances Validées (5-Fold CV)
- **Accuracy** : 79.1%
- **ROC-AUC** : 0.834
- **Recall** : 64.4%
- **Précision** : 61.5% (plancher garanti $\ge 61.5%$)
- **MAE régression** : 0.030 mm²/s (erreur médiane typique)

## Utilisation
```python
from src.models.model_thermo import predict_fire_safety

result = predict_fire_safety(o2_percent=34.0, pressure_kpa=70.0, flow_cm_s=5.0, material="pmma")
# result = {
#     "is_fire_active": bool,
#     "fire_probability": float,
#     "predicted_burning_rate_mm2_s": float,
#     "spacecraft_risk_score": float (0-100),
#     "risk_level": str
# }
```
Lancer les tests de scénarios :
```bash
python -m src.models.model_thermo.test_run
```
