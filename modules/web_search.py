import config
from core.keypool import KeyPool
from tavily import TavilyClient

_pool = KeyPool(config.TAVILY_API_KEYS) if config.TAVILY_API_KEYS else None


def chercher(requete: str, n: int = 5) -> list[dict]:
    """Retourne [{'titre','url','extrait'}]. Liste vide si aucune clé ou quota épuisé."""
    if _pool is None:
        return []
    for _ in range(len(config.TAVILY_API_KEYS)):
        key = _pool.get()
        if key is None:
            return []
        try:
            r = TavilyClient(api_key=key).search(query=requete, max_results=n, search_depth="basic")
            return [
                {"titre": x.get("title", ""), "url": x["url"], "extrait": x.get("content", "")}
                for x in r.get("results", [])
            ]
        except Exception:
            _pool.penalize(key, 3600)
    return []
