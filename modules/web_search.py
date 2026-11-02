import requests

import config
from core.keypool import KeyPool

_TIMEOUT = 15
_QUOTA = {429, 432, 433}  # limites de débit / plan : on bascule sur la clé suivante


class RechercheIndisponible(Exception):
    def __init__(self, fournisseur: str, statut: int | None = None, detail: str = ""):
        super().__init__(f"{fournisseur}: statut={statut} {detail}".strip())
        self.fournisseur, self.statut = fournisseur, statut


def _exa(cle: str, q: str, n: int, domaines: list[str] | None) -> requests.Response:
    corps = {"query": q, "numResults": n, "contents": {"text": {"maxCharacters": 500}}}
    if domaines:
        corps["includeDomains"] = domaines
    return requests.post("https://api.exa.ai/search", headers={"x-api-key": cle}, json=corps, timeout=_TIMEOUT)


def _tavily(cle: str, q: str, n: int, domaines: list[str] | None) -> requests.Response:
    corps = {"query": q, "max_results": n, "search_depth": "basic"}
    if domaines:
        corps["include_domains"] = domaines
    return requests.post("https://api.tavily.com/search", headers={"Authorization": f"Bearer {cle}"}, json=corps, timeout=_TIMEOUT)


def _norme(nom: str, data: dict) -> list[dict]:
    if nom == "exa":
        return [{"titre": x.get("title", ""), "url": x["url"], "extrait": x.get("text", ""),
                 "date": (x.get("publishedDate") or "")[:10]} for x in data.get("results", [])]
    return [{"titre": x.get("title", ""), "url": x["url"], "extrait": x.get("content", ""),
             "date": ""} for x in data.get("results", [])]


_FOURNISSEURS = {
    "exa": (_exa, lambda: config.EXA_API_KEYS),
    "tavily": (_tavily, lambda: config.TAVILY_API_KEYS),
}
_pools: dict[str, KeyPool] = {}


def _essayer(nom: str, q: str, n: int, domaines: list[str] | None) -> list[dict] | None:
    """None = aucune clé configurée. Lève RechercheIndisponible si l'appel échoue."""
    appel, cles = _FOURNISSEURS[nom]
    liste = cles()
    if not liste:
        return None
    pool = _pools.setdefault(nom, KeyPool(liste))
    statut = None
    for _ in range(len(liste)):
        cle = pool.get()
        if cle is None:
            break
        try:
            r = appel(cle, q, n, domaines)
        except requests.RequestException as e:
            raise RechercheIndisponible(nom, None, type(e).__name__)
        if r.status_code == 200:
            return _norme(nom, r.json())
        statut = r.status_code
        if statut in _QUOTA:
            pool.penalize(cle, 3600)
            continue
        raise RechercheIndisponible(nom, statut)  # 401/403/400 : pas de pénalité
    raise RechercheIndisponible(nom, statut, "toutes les clés épuisées")


def chercher(requete: str, n: int = 5, domaines: list[str] | None = None) -> list[dict]:
    """[{'titre','url','extrait','date'}]. [] si aucune clé. RechercheIndisponible si tout échoue."""
    derniere = None
    for nom in config.SEARCH_PROVIDERS:
        if nom not in _FOURNISSEURS:
            continue
        try:
            res = _essayer(nom, requete, n, domaines)
        except RechercheIndisponible as e:
            derniere = e
            continue
        if res is not None:
            return res
    if derniere:
        raise derniere
    return []
