from modules.web_search import chercher
from modules.usage import peut_chercher, enregistrer

DOMAINES_MED = ["vidal.fr", "has-sante.fr", "who.int", "nih.gov", "ameli.fr"]


def enrichir(requete: str, contexte: str, medical: bool = False):
    """Retourne (contexte, sources, statut). statut: ok|aucun|plafond|indisponible."""
    if not peut_chercher():
        return contexte, [], "plafond"
    try:
        sources = chercher(requete[:200], n=4, domaines=DOMAINES_MED if medical else None)
    except Exception as e:
        print(f"web_search: {e}")
        return contexte, [], "indisponible"
    enregistrer()
    if not sources:
        return contexte, [], "aucun"
    bloc = "\n\n".join(
        f"[{i}] {s['titre']} ({s['date'] or 'date inconnue'}) {s['url']}\n{s['extrait']}"
        for i, s in enumerate(sources, 1)
    )
    ctx = (f"{contexte}\n\nSOURCES WEB. Cite uniquement ces sources avec [n]. "
           f"N'invente aucune URL. Si elles ne couvrent pas un point, dis-le.\n{bloc}")
    return ctx, sources, "ok"
