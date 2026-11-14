"""Interface d'inférence Physics-Informed ML (Propriétés thermodynamiques NIST/NASA)."""

import os
import joblib
import numpy as np
import pandas as pd

MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "pim_flammability_gbt_v1.joblib")

_BUNDLE = None

def _get_bundle():
    global _BUNDLE
    if _BUNDLE is None:
        if not os.path.exists(MODEL_PATH):
            raise FileNotFoundError(f"Fichier modèle introuvable : {MODEL_PATH}")
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
    bundle = _get_bundle()
    clf = bundle["classifier_pipeline"]
    reg = bundle["regressor_pipeline"]
    thresh = bundle["optimal_threshold"]
    thermo_table = bundle["thermo_properties_table"]
    default_thermo = bundle["default_thermo"]

    mat_lower = str(material).lower().strip()
    base_props = thermo_table.get(mat_lower, default_thermo).copy()

    delta_hc = custom_delta_hc if custom_delta_hc is not None else base_props["delta_hc"]
    t_auto_ign = custom_t_auto_ign if custom_t_auto_ign is not None else base_props["t_auto_ign_c"]
    l_gas = custom_l_gas if custom_l_gas is not None else base_props["l_gas_kj_g"]
    solid_flag = is_solid if is_solid is not None else base_props["is_solid"]

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

    risk_score = round(prob_fire * 100, 1)
    if risk_score < 35:
        risk_level = "GREEN (Auto-extinguible)"
    elif risk_score < 65:
        risk_level = "ORANGE (Risque d'inflammation modéré sous flux)"
    else:
        risk_level = "RED (Propagation active dangereuse)"

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
