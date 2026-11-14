"""Interface d'inférence officielle et modulaire pour le Dashboard de Luca.
Architecture : 100% Physics-Informed ML (Propriétés thermodynamiques de la matière).
"""

import os
import joblib
import numpy as np
import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "pim_flammability_gbt_v1.joblib")

# Chargement paresseux au premier appel
_BUNDLE = None

def _get_bundle():
    global _BUNDLE
    if _BUNDLE is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Modèle officiel introuvable à : {MODEL_PATH}")
        _BUNDLE = joblib.load(MODEL_PATH)
    return _BUNDLE

def predict_fire_safety(
    o2_percent: float,
    pressure_kpa: float,
    flow_cm_s: float = 0.0,
    material: str = "pmma",
    custom_delta_hc: float = None,
    custom_t_auto_ign: float = None,
    custom_l_gas: float = None,
    is_solid: int = None
):
    """Prédit le risque d'allumage et le taux de combustion pour n'importe quelle condition spatiale.
    
    Supporte les matériaux connus de la NASA et les matériaux totalement inédits (Zero-Shot).
    """
    bundle = _get_bundle()
    clf = bundle["classifier_pipeline"]
    reg = bundle["regressor_pipeline"]
    thresh = bundle["optimal_threshold"]
    thermo_table = bundle["thermo_properties_table"]
    default_thermo = bundle["default_thermo"]

    # 1. Extraction ou injection des propriétés physico-chimiques
    mat_lower = str(material).lower().strip()
    base_props = thermo_table.get(mat_lower, default_thermo).copy()

    delta_hc = custom_delta_hc if custom_delta_hc is not None else base_props["delta_hc"]
    t_auto_ign = custom_t_auto_ign if custom_t_auto_ign is not None else base_props["t_auto_ign_c"]
    l_gas = custom_l_gas if custom_l_gas is not None else base_props["l_gas_kj_g"]
    solid_flag = is_solid if is_solid is not None else base_props["is_solid"]

    # 2. Vecteur d'entrée pour le classificateur
    X_clf = pd.DataFrame([{
        "o2_percent": float(o2_percent),
        "pressure_kpa": float(pressure_kpa),
        "flow_cm_s": float(flow_cm_s),
        "delta_hc": float(delta_hc),
        "t_auto_ign_c": float(t_auto_ign),
        "l_gas_kj_g": float(l_gas),
        "is_solid": int(solid_flag)
    }])

    prob_fire = float(clf.predict_proba(X_clf)[0, 1])
    is_fire = bool(prob_fire >= thresh)

    # 3. Prédiction continue en cascade (taux de combustion)
    if is_fire:
        X_reg = pd.DataFrame([{
            "o2_percent": float(o2_percent),
            "pressure_kpa": float(pressure_kpa),
            "delta_hc": float(delta_hc),
            "t_auto_ign_c": float(t_auto_ign),
            "l_gas_kj_g": float(l_gas)
        }])
        pred_rate = float(reg.predict(X_reg)[0])
        pred_rate = max(0.0, round(pred_rate, 4))
    else:
        pred_rate = 0.0

    # 4. Calcul de l'indice de risque global pour Luca (0 à 100)
    risk_score = round(prob_fire * 100, 1)
    if risk_score < 35:
        risk_level = "GREEN (Atmosphère auto-extinguible)"
    elif risk_score < 65:
        risk_level = "ORANGE (Risque d'inflammation modéré sous flux)"
    else:
        risk_level = "RED (Propagation active très dangereuse)"

    return {
        "is_fire_active": is_fire,
        "fire_probability": round(prob_fire, 4),
        "decision_threshold": thresh,
        "predicted_burning_rate_mm2_s": pred_rate,
        "spacecraft_risk_score": risk_score,
        "risk_level": risk_level,
        "material_identified": mat_lower in thermo_table,
        "physical_properties_used": {
            "delta_hc_kj_g": delta_hc,
            "t_auto_ign_c": t_auto_ign,
            "l_gas_kj_g": l_gas,
            "is_solid": solid_flag
        }
    }

if __name__ == "__main__":
    print("--- TEST 1 : Cabine standard ISS (Air 21% O2, 101.3 kPa, PMMA solide) ---")
    res1 = predict_fire_safety(21.0, 101.3, 0.0, "pmma")
    print(res1)

    print("\n--- TEST 2 : Sas lunaire Artemis enrichi (34% O2, 70 kPa, Méthanol) ---")
    res2 = predict_fire_safety(34.0, 70.0, 5.0, "methanol")
    print(res2)

    print("\n--- TEST 3 : Nouveau matériau INÉDIT (Kevlar synthétique non testé par NASA) ---")
    res3 = predict_fire_safety(30.0, 80.0, 10.0, "kevlar")
    print(res3)
