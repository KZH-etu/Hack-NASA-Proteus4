import os
import sys

sys.path.append(os.path.dirname(__file__))
from predict import predict_fire_safety

def run_demo():
    print("=" * 75)
    print("DEMONSTRATION DU MODELE DE NICOLAS (PHYSICS-INFORMED ML)")
    print("=" * 75 + "\n")

    scenarios = [
        ("Cabine Standard ISS (Terre / 0g)", 21.0, 101.3, 0.0, "pmma"),
        ("Sas Lunaire Artemis (Atmosphere enrichie O2)", 34.0, 70.0, 5.0, "methanol"),
        ("Rover Pressurise Martien (Hypoxique basse pression)", 16.0, 50.0, 10.0, "sibal"),
        ("Materiau Inedit (Composite Kevlar haute resistance)", 30.0, 80.0, 10.0, "kevlar")
    ]

    for title, o2, p, flow, mat in scenarios:
        print(f"Scénario : {title}")
        print(f"   Conditions : O2={o2}%, Pression={p} kPa, Flux={flow} cm/s, Materiau={mat}")
        res = predict_fire_safety(o2_percent=o2, pressure_kpa=p, flow_cm_s=flow, material=mat)
        print(f"   Verdict : {'FEU ACTIF' if res['is_fire_active'] else 'AUTO-EXTINCTION'}")
        print(f"   Probabilite : {res['fire_probability']*100:.1f}%")
        print(f"   Taux de combustion estime : {res['predicted_burning_rate_mm2_s']} mm2/s")
        print(f"   Niveau de risque : {res['risk_level']}\n")

if __name__ == "__main__":
    run_demo()
