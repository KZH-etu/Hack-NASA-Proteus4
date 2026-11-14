import os
import sys

sys.path.append(os.path.dirname(__file__))
from predict import predict_fire_safety

def run_demo():
    print("=" * 70)
    print("PIM GBT v1 - DEMO RUN (4 SCENARIOS DE MISSION)")
    print("=" * 70 + "\n")

    scenarios = [
        ("ISS Standard (0g)", 21.0, 101.3, 0.0, "pmma"),
        ("Sas Lunaire Artemis (O2 enrichi)", 34.0, 70.0, 5.0, "methanol"),
        ("Rover Martien (Basse pression)", 16.0, 50.0, 10.0, "sibal"),
        ("Composite Inedit (Zero-shot)", 30.0, 80.0, 10.0, "kevlar")
    ]

    for title, o2, p, flow, mat in scenarios:
        res = predict_fire_safety(o2_percent=o2, pressure_kpa=p, flow_cm_s=flow, material=mat)
        status = "FEU" if res["is_fire_active"] else "EXTINCTION"
        print(f"[{status}] {title} ({mat}) -> P(feu)={res['fire_probability']*100:.1f}%, Rate={res['predicted_burning_rate_mm2_s']} mm2/s")

if __name__ == "__main__":
    run_demo()
