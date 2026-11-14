"""FICHES PAR FAMILLE — calées sur les vraies tables (data/processed/*.parquet).

Pour chaque famille :
- fichier      : table d'origine
- filtre       : quelles lignes appartiennent à la famille
- filtre_extra : (optionnel) fonction qui retire des lignes, avec la raison en commentaire
- entrees      : paramètres réglés par l'utilisateur, connus AVANT l'essai (jamais un résultat)
- sorties      : ce qu'on prédit (classification = issue, regression = nombre)
- groupe       : colonne de validation (une session entière est mise de côté)

Familles « données seulement » : pas de résultat à prédire, affichées sans modèle.
"""

FAMILIES = {
    "Gouttelettes (FLEX)": {
        "description": "Une goutte de carburant isolée brûle en apesanteur : "
                       "s'éteint-elle, éclate-t-elle ou brûle-t-elle jusqu'au bout ?",
        "fichier": "droplets",
        "filtre": {"experiment": ["FLEX"]},
        "entrees": {
            "fuel": "texte",            # heptane / méthanol
            "x_o2": "nombre",           # fraction d'O2 (0.21 = air)
            "x_co2": "nombre",          # fraction de CO2 (gaz extincteur)
            "x_he": "nombre",           # fraction d'hélium
            "pressure_kpa": "nombre",
            "d0_mm": "nombre",          # diamètre initial de la goutte
        },
        # Variables calculées (physique de la combustion, choisies AVANT de voir les résultats) :
        # c'est la pression partielle d'O2 (quantité réelle d'O2 disponible), pas la fraction,
        # qui gouverne la flamme ; idem pour le CO2 extincteur.
        # TESTÉES le 14/11 (tests/ameliorations.py) : pas de gain démontré -> NON RETENUES.
        # Pour les réactiver, renommer la clé en « derivees ».
        "derivees_non_retenues": {
            "p_o2_kpa": lambda X: X["x_o2"] * X["pressure_kpa"],
            "p_co2_kpa": lambda X: X["x_co2"] * X["pressure_kpa"],
            "x_inerte": lambda X: 1 - X["x_o2"],
        },
        "sorties": {
            "issue": {"colonne": "outcome", "type": "classification"},
            "vitesse_combustion_mm2_s": {"colonne": "burning_rate_mm2_s", "type": "regression"},
        },
        "groupe": "session",
    },
    "Gaz (ACME CFI-G)": {
        "description": "Petite flamme de gaz sur un brûleur : brûle-t-elle durablement, "
                       "s'éteint-elle seule, ou ne s'allume-t-elle pas ?",
        "fichier": "gas",
        "filtre": {"experiment": ["ACME CFI-G"]},
        # « other » : 2 essais seulement, inclassables -> retirés
        "filtre_extra": lambda rows: rows[rows["outcome"] != "other"],
        "entrees": {
            "fuel": "texte",            # éthane, propane, n-butane
            "flame_type": "texte",      # normal (carburant dans l'air) / inverse (O2 dans le carburant)
            "x_fuel": "nombre",
            "x_o2": "nombre",
            "pressure_kpa": "nombre",
            "hc_rate_mg_s": "nombre",   # débit de carburant au brûleur
        },
        # Testées, pas de gain démontré -> non retenues (voir plus haut).
        "derivees_non_retenues": {
            "p_o2_kpa": lambda X: X["x_o2"] * X["pressure_kpa"],
            "p_fuel_kpa": lambda X: X["x_fuel"] * X["pressure_kpa"],
        },
        "sorties": {
            "issue": {"colonne": "outcome", "type": "classification"},
        },
        "groupe": "session",
    },
}

# Familles sans résultat exploitable pour le ML : à afficher dans l'onglet « Explorer » seulement.
DATA_ONLY = {
    "Saffire": "solids — grands feux, 22 essais, pas de vitesse de propagation dans la table",
    "SPICE / ACME Flame Design": "gas — pas de colonne de résultat",
    # rt_r0 = Rt/R0 = résistance du fil chauffant à chaud / à température ambiante :
    # c'est le RÉGLAGE de la température de chauffe (une condition de l'essai), pas un résultat.
    # La table ne contient aucune mesure de fumée (taille des particules…) -> rien à prédire.
    "SAME / SAME-R": "aerosols — fumées ; rt_r0 = réglage de chauffe (entrée), aucune mesure de résultat",
    # Retiré du ML le 14/11 : flow_min_cm_s / flow_max_cm_s = vitesse de l'air PENDANT l'essai
    # (souvent une rampe), pas le débit d'extinction. Avec un air constant, il reste 35 essais
    # dont 3 seulement où la flamme brûle : impossible d'apprendre « brûle / s'éteint » honnêtement.
    # Utiliser ces vitesses comme entrée quand l'air est en rampe serait une fuite d'information
    # (le minimum atteint dépend justement du moment où la flamme s'est éteinte).
    "Solides (BASS-II)": "solids — 96 essais avec issue, dont 87 % « éteint » par protocole ; "
                         "air souvent en rampe : affichage des essais réels seulement",
    # Version solids_2 (14/11, 16 h) : 3 colonnes ajoutées, toujours pas de modèle :
    # - extinction_flow_cm_s : 14 essais seulement, presque tous du PMMA -> trop peu pour apprendre
    # - extinction_pot : position du bouton du ventilateur (pas des cm/s, conversion inconnue),
    #   déduite des observations, quasi constante (~0,3) pour les extinctions par manque d'air
    # - extinction_mode : dépend surtout de la façon dont l'essai a été mené (protocole),
    #   pas des conditions de départ -> un modèle prédirait le comportement de l'opérateur
    # Ces colonnes sont précieuses À AFFICHER dans l'onglet Explorer.
}


def model_inputs(family: str) -> dict:
    """Entrées vues par le modèle : celles de l'utilisateur + les variables calculées."""
    fiche = FAMILIES[family]
    return {**fiche["entrees"], **{name: "nombre" for name in fiche.get("derivees", {})}}


# Modèle utilisé par (famille, sortie) quand il diffère du modèle par défaut (ForestModel).
# Décidé par tests/oversampling.py (14/11, règle fixée avant de lancer : IC 95 % du gain > 0) :
# SMOTE améliore le F1 macro du gaz de +0,047 [IC +0,005 ; +0,114]. Gain de justesse :
# 6 comparaisons ont été faites, une réussite pourrait être due au hasard -> à re-vérifier
# si les données changent.
MODEL_OVERRIDES = {
    ("Gaz (ACME CFI-G)", "issue"): "SmoteForest",
}
