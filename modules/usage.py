import json, os, time

_CHEMIN = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "web_usage.json")
MAX_JOUR = int(os.getenv("WEB_MAX_JOUR", "30"))
MAX_MOIS = int(os.getenv("WEB_MAX_MOIS", "500"))


def _charger() -> dict:
    jour, mois = time.strftime("%Y-%m-%d"), time.strftime("%Y-%m")
    try:
        with open(_CHEMIN, encoding="utf-8") as f:
            d = json.load(f)
    except (OSError, ValueError):
        d = {}
    if d.get("jour") != jour:
        d["jour"], d["n_jour"] = jour, 0
    if d.get("mois") != mois:
        d["mois"], d["n_mois"] = mois, 0
    return d


def peut_chercher() -> bool:
    d = _charger()
    return d["n_jour"] < MAX_JOUR and d["n_mois"] < MAX_MOIS


def enregistrer() -> None:
    d = _charger()
    d["n_jour"] += 1
    d["n_mois"] += 1
    os.makedirs(os.path.dirname(_CHEMIN), exist_ok=True)
    with open(_CHEMIN, "w", encoding="utf-8") as f:
        json.dump(d, f)
