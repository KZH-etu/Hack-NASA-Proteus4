"""Entraîne le service ML une fois et le sauvegarde (le dashboard n'a plus qu'à le charger).

    python -m src.models.model_rf.train

Produit src/models/model_rf/artifacts/ml_service.joblib. À relancer quand les données ou les fiches changent.
"""
import time
import warnings

from .service import MLService
from .data_prep import load_tables
from .forest import ForestModel

warnings.filterwarnings("ignore")

if __name__ == "__main__":
    start = time.time()
    service = MLService(load_tables(), model_class=ForestModel)  # v4 retenue : le réglage imbriqué n'apportait pas de gain démontré
    service.save()
    print(f"Service entraîné et sauvegardé en {time.time() - start:.0f} s")
    for (family, output), model in service.models.items():
        q = service.quality.get((family, output), {})
        print(f"  {family} / {output} : réglages {getattr(model, 'best_params_', '-')}, "
              f"bat la référence : {q.get('bat_la_reference')}")
