"""Point d'entrée de la recommandation de la prochaine expérience ISS : aiguille vers le bon modèle.

    from src.models.recommend import recommend_next_experiment
    recommend_next_experiment({"fuel": "heptane", "o2_percent": 34, "pressure_kpa": 55, "d0_mm": 3.0})   # gouttelettes (flex)
    recommend_next_experiment({"material": "pmma_flat", "o2_percent": 34, "flow_cm_s": 10})              # solides (solids)

Méthode et détails : src/models/flex/recommend.py et src/models/solids/model.py.
"""


def recommend_next_experiment(scenario, n=5):
    """Recommandations d'essais autour d'un scénario de mission (gouttelettes si `fuel`, solides si `material`)."""
    if "material" in scenario:
        from src.models.solids import recommend_next_experiment as recommend_solids
        return recommend_solids(scenario, n=n)
    from src.models.flex.recommend import recommend_next_experiment as recommend_flex
    return recommend_flex(scenario, n=n)
