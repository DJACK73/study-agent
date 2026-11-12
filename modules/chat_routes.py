import json
import re
import uuid
from pathlib import Path
from flask import Blueprint, jsonify, request, send_from_directory
from modules import chat_db
from modules.chat_intent import detecter_image, detecter_pdf, extraire_partie, journaliser_rate, sujet_dans, veut_images

bp = Blueprint("chat", __name__, url_prefix="/api/chat")


@bp.get("/conversations")
def liste():
    return jsonify(chat_db.lister())


@bp.post("/conversations")
def nouvelle():
    titre = (request.get_json(silent=True) or {}).get("titre") or "Nouvelle discussion"
    return jsonify({"id": chat_db.creer(titre)}), 201


@bp.get("/conversations/<int:cid>")
def lecture(cid):
    c = chat_db.lire(cid)
    return (jsonify(c), 200) if c else (jsonify({"error": "Introuvable"}), 404)


@bp.patch("/conversations/<int:cid>")
def renomme(cid):
    titre = ((request.get_json(silent=True) or {}).get("titre") or "").strip()
    if not titre:
        return jsonify({"error": "Titre vide"}), 400
    ok = chat_db.renommer(cid, titre)
    return (jsonify({"ok": True}), 200) if ok else (jsonify({"error": "Introuvable"}), 404)


@bp.delete("/conversations/<int:cid>")
def supprime(cid):
    chemins = _chemins_images(cid)
    n = chat_db.supprimer(cid)
    if n:
        _purger(chemins)
    return (jsonify({"ok": True}), 200) if n else (jsonify({"error": "Introuvable"}), 404)


@bp.delete("/conversations")
def supprime_tout():
    if request.args.get("confirm") != "oui":
        return jsonify({"error": "Ajouter ?confirm=oui"}), 400
    chemins = _chemins_images()
    n = chat_db.supprimer(None)
    _purger(chemins)
    return jsonify({"supprimees": n})


def _chemins_images(cid=None) -> list[str]:
    """Chemins relatifs des fichiers (images et PDF) rattachés aux messages."""
    from modules.database import get_conn
    out = []
    with get_conn() as conn:
        for col in ("image_path", "pdf_path"):
            sql = f"SELECT {col} FROM messages WHERE {col} IS NOT NULL"
            rows = conn.execute(sql + (" AND conversation_id=?" if cid else ""),
                                (cid,) if cid else ()).fetchall()
            out += [r[col] for r in rows]
    return out


def _purger(chemins: list[str]) -> None:
    """Supprime les fichiers après la suppression en base. Seul le nom de fichier est utilisé."""
    for rel in chemins:
        base = PDF_DIR if rel.startswith("pdfs/") else UPLOAD_DIR
        (base / Path(rel).name).unlink(missing_ok=True)


CHAT_PROMPT = (
    "Tu es le tuteur d'un étudiant en santé qui se sert de cette application pour étudier toutes sortes de matières. "
    "Déduis la matière de la question et réponds en français, comme un bon prof qui explique simplement.\n"
    "Comprends d'abord ce que l'étudiant cherche vraiment (définition, mécanisme, comparaison, application), puis adapte la profondeur : "
    "question précise = réponse courte et exacte ; notion, maladie ou mécanisme = réponse structurée qui explique le pourquoi, pas seulement une liste de faits. "
    "Pour une maladie : définition, cause, physiopathologie, signes, diagnostic, traitement, prévention, en phrases courtes.\n"
    "Pas de salutation, pas d'analyse affichée : commence par la réponse. Un exemple concret quand il aide. Conserve accents et symboles (→ ≥ ₂ α). "
    "N'invente aucune URL ni aucun chiffre ; si tu ne sais pas, dis « je ne sais pas ». Appuie-toi sur la conversation précédente. "
    "Utilise toujours les termes complets du domaine, jamais les abréviations familières.\n"
    "Si un mot est une faute de frappe, un terme familier ou ambigu, ouvre par une phrase courte qui dit comment tu le comprends ; "
    "si le mot est déjà correct, n'ajoute aucune phrase d'interprétation. Si deux sens sont possibles, cite-les et demande lequel. N'invente jamais un sens.\n"
    "IMAGES : tu peux illustrer ta réponse avec des images libres de droits quand elles aident vraiment à comprendre "
    "(anatomie, schéma d'un mécanisme, cellule, coupe histologique, courbe). Une définition, une notion abstraite ou une question ponctuelle n'en demandent pas, ou une seule. "
    "Un sujet complet (un système, un organe, un mécanisme, une maladie) se présente comme une leçon de manuel : au moins trois images, "
    "de trois à cinq, une vue d'ensemble puis une image pour chaque grande partie que tu détailles (l'organe lui-même, sa structure fine ou sa coupe, le mécanisme). "
    "Place chaque image juste après le paragraphe qu'elle illustre, jamais en bloc à la fin, avec un marqueur sur une ligne seule : [[img: requête en anglais]] "
    "(2 à 5 mots, nom précis de ce qui est montré, suivi de « labeled diagram » quand les noms des parties comptent). "
    "Chaque image doit montrer précisément ce que le paragraphe vient d'expliquer : une requête différente par partie, jamais la même vue d'ensemble répétée. "
    "Chaque image est ensuite choisie parmi plusieurs candidats. Ne mentionne jamais ces marqueurs et ne dis jamais que tu ne peux pas montrer d'images."
)
HIST_MAX_MSG = 12
HIST_MAX_CAR = 12000


def _requete_web(messages: list[dict], msg: str) -> str:
    """Message court (suivi) : on ajoute la dernière question de l'étudiant pour garder le sujet."""
    if len(msg) < 40:
        for m in reversed(messages):
            if m["role"] == "user":
                return f"{m['contenu'][:150]} {msg}"
    return msg[:200]


def _historique(messages: list[dict]) -> str:
    """12 derniers messages, plafonnés en caractères (les plus anciens sautent d'abord)."""
    out, total = [], 0
    for m in reversed(messages[-HIST_MAX_MSG:]):
        ligne = f"{'Étudiant' if m['role'] == 'user' else 'Tuteur'} : {m['contenu']}"
        total += len(ligne)
        if total > HIST_MAX_CAR:
            break
        out.append(ligne)
    return "\n\n".join(reversed(out))


UPLOAD_DIR = Path(__file__).resolve().parent.parent / "data" / "uploads"
PDF_DIR = Path(__file__).resolve().parent.parent / "data" / "pdfs"


def _ext_image(b: bytes) -> str | None:
    """Type réel par octets magiques. Le nom envoyé par le client n'est jamais utilisé."""
    if b[:3] == b"\xff\xd8\xff":
        return "jpg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    return None


PDF_MAX_OCTETS = 10 * 1024 * 1024
PDF_MAX_CAR = 8000


def _texte_pdf(b: bytes) -> str:
    """Texte d'un PDF (30 pages max, plafonné en caractères). Vide si scanné ou illisible."""
    import io
    try:
        import pypdf
        out, total = [], 0
        for p in pypdf.PdfReader(io.BytesIO(b)).pages[:30]:
            t = p.extract_text() or ""
            out.append(t)
            total += len(t)
            if total >= PDF_MAX_CAR:
                break
        return "\n".join(out).strip()[:PDF_MAX_CAR]
    except Exception:
        return ""


def _lire_requete():
    """Multipart (message, web, image) ou JSON (message, web)."""
    if request.mimetype == "multipart/form-data":
        f = request.form
        return ((f.get("message") or "").strip(),
                (f.get("web") or "").lower() in ("1", "true", "on"),
                request.files.get("image") or request.files.get("fichier"))
    d = request.get_json(silent=True) or {}
    return (d.get("message") or "").strip(), bool(d.get("web")), None


@bp.post("/conversations/<int:cid>/messages")
def envoyer(cid):
    from modules.gemini_handler import analyser_texte, analyser_image  # import local : client créé à l'import
    conv = chat_db.lire(cid)
    if conv is None:
        return jsonify({"error": "Introuvable"}), 404
    msg, web, fichier = _lire_requete()
    stream = bool((request.get_json(silent=True) or {}).get("stream"))
    data = ext = texte_pdf = nom_pdf = None
    if fichier:
        data = fichier.read()
        if data[:5] == b"%PDF-":
            if len(data) > PDF_MAX_OCTETS:
                return jsonify({"error": "PDF trop lourd (10 Mo max)"}), 413
            texte_pdf = _texte_pdf(data)
            if not texte_pdf:
                return jsonify({"error": "PDF sans texte extractible (scanné ?) : envoie-le en image"}), 400
            nom_pdf = Path(fichier.filename or "document.pdf").name[:60]
            data = None
            msg = msg or "Résume ce document."
        else:
            ext = _ext_image(data)
            if ext is None:
                return jsonify({"error": "Fichier invalide (jpg, png, webp, pdf)"}), 400
            msg = msg or "Explique cette image."
    if not msg:
        return jsonify({"error": "Message vide"}), 400
    demande = None if (data or texte_pdf) else detecter_pdf(msg)
    journaliser_rate(msg, demande)
    if demande:
        return _repondre_pdf(cid, conv, msg, demande)
    if not (data or texte_pdf):
        sujet_img = detecter_image(msg)
        if sujet_img:
            return _repondre_images(cid, conv, msg, sujet_img)
    texte = f"{_historique(conv['messages'])}\n\nÉtudiant : {msg}".strip()
    if texte_pdf:
        texte += f"\n\nDocument joint « {nom_pdf} » (extrait) :\n{texte_pdf}"
    sources, web_statut = [], None
    veut_img = not (data or texte_pdf) and veut_images(msg)
    sujet_w = _sujet_web(conv['messages'], msg) if web else None
    if veut_img:
        texte += ("\n\n(L'étudiant demande des images : place plusieurs marqueurs [[img: ...]] aux endroits où elles aident, "
                  "jusqu'à 5, avec « labeled diagram » pour l'anatomie.)")
    if web:
        from modules.web_context import enrichir
        texte, sources, web_statut = enrichir(sujet_w, texte, medical=True)
    img_path = None
    if data:
        UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
        img_path = UPLOAD_DIR / f"{uuid.uuid4().hex}.{ext}"
        img_path.write_bytes(data)
    if stream and not img_path:
        return _flux_chat(cid, conv, msg, texte, sources, web_statut, veut_img)
    try:
        if img_path:
            rep = analyser_image(str(img_path), f"{CHAT_PROMPT}\n\n{texte}")
        else:
            from modules.gemini_handler import MODELE_BASE
            _tok = MODELE_BASE.set(_MODELE_CHAT)
            try:
                rep = analyser_texte(texte, CHAT_PROMPT)
            finally:
                MODELE_BASE.reset(_tok)
    except Exception as e:
        print(f"chat gemini: {e}")
        if img_path:
            img_path.unlink(missing_ok=True)
        if isinstance(e, TimeoutError):
            return jsonify({"error": "Gemini ne repond pas, reessaie"}), 504
        if isinstance(e, ConnectionError):
            return jsonify({"error": "Gemini injoignable, verifie ta connexion"}), 502
        return jsonify({"error": "Gemini indisponible"}), 502
    d, code = _finaliser_chat(cid, conv, msg, rep, img_path, texte_pdf, nom_pdf, sources, web_statut, veut_img)
    return jsonify(d), code


def _finaliser_chat(cid, conv, msg, rep, img_path, texte_pdf, nom_pdf, sources, web_statut, veut_img):
    # sauvegarde la reponse, retire les marqueurs, titre ; renvoie (dict, statut)
    rel = f"uploads/{img_path.name}" if img_path else None
    from sqlite3 import IntegrityError
    try:
        chat_db.ajouter_message(cid, "user", f"📎 {nom_pdf} — {msg}" if texte_pdf else msg, image_path=rel)
    except IntegrityError:  # discussion supprimée pendant l'appel Gemini
        if img_path:
            img_path.unlink(missing_ok=True)
        return {"error": "Discussion supprimée pendant la réponse"}, 404
    rep, marq = _extraire_marqueurs(rep)
    slots = [{"q": q, "apres": a} for q, a in marq[:5]]
    print(f"chat images: {len(marq)} marqueur(s) ecrit(s) par le modele")
    if veut_img and not slots:
        slots = [{"q": _sujet_image(conv['messages'], msg), "apres": None}]
    imgs = []
    mid = chat_db.ajouter_message(cid, "ai", rep, sources_json=(json.dumps(sources, ensure_ascii=False) if sources else None),
                                  images_json=(json.dumps(imgs, ensure_ascii=False) if imgs else None))
    titre = conv["titre"]
    if not conv["messages"] and titre == "Nouvelle discussion":
        titre = _titre_conv(msg)
        chat_db.renommer(cid, titre)
    return ({"reponse": rep, "message_id": mid, "titre": titre, "sources": sources,
                    "web_statut": web_statut, "image_path": rel, "pdf_path": None, "images": imgs, "slots": slots}, 200)


def _flux_chat(cid, conv, msg, texte, sources, web_statut, veut_img):
    # flux NDJSON : {"t": morceau} ... puis {"fin": json final} ou {"erreur": texte}
    import time
    from flask import Response
    from modules.gemini_handler import analyser_texte_flux

    def ligne(o):
        return json.dumps(o, ensure_ascii=False) + "\n"

    def gen():
        t0, premier, morceaux = time.time(), None, []
        try:
            for m in analyser_texte_flux(texte, CHAT_PROMPT, _MODELE_CHAT):
                if premier is None:
                    premier = time.time() - t0
                morceaux.append(m)
                yield ligne({"t": m})
        except Exception as e:
            print(f"chat gemini: {e}")
            if isinstance(e, TimeoutError):
                err = "Gemini ne repond pas, reessaie"
            elif isinstance(e, ConnectionError):
                err = "Gemini injoignable, verifie ta connexion"
            else:
                err = "Gemini indisponible"
            yield ligne({"erreur": err})
            return
        rep = "".join(morceaux)
        if not rep.strip():
            print("chat gemini: flux vide")
            yield ligne({"erreur": "Gemini indisponible"})
            return
        print(f"chat gemini: premier morceau {premier:.1f} s, total {time.time() - t0:.1f} s")
        d, code = _finaliser_chat(cid, conv, msg, rep, None, None, None, sources, web_statut, veut_img)
        yield ligne({"fin": d} if code == 200 else {"erreur": d["error"]})

    return Response(gen(), mimetype="application/x-ndjson",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


_NOM_PDF = re.compile(r"[0-9a-f]{32}\.pdf")


@bp.get("/pdf/<nom>")
def telecharger_pdf(nom):
    if not _NOM_PDF.fullmatch(nom):
        return jsonify({"error": "Introuvable"}), 404
    return send_from_directory(PDF_DIR, nom, mimetype="application/pdf")


_NOM_IMG = re.compile(r"[0-9a-f]{32}\.(jpg|png|webp)")


@bp.get("/img/<nom>")
def lire_image(nom):
    if not _NOM_IMG.fullmatch(nom):
        return jsonify({"error": "Introuvable"}), 404
    return send_from_directory(UPLOAD_DIR, nom)


_MSG_RIEN = "Aucune réponse à exporter pour l'instant."


def _titre_conv(msg, n=50):
    """Titre de conversation : espaces normalisés, coupé à un mot entier."""
    msg = " ".join(msg.split())
    if len(msg) <= n:
        return msg
    cut = msg[:n + 1]
    cut = cut.rsplit(" ", 1)[0] if " " in cut else msg[:n]
    return cut.rstrip(" ,;:.-")
_TITRE_MD = re.compile(r"^#{1,3}[ \t]+(.+?)[ \t#]*$", re.M)


def _reponses_ia(messages):
    """Réponses IA exportables : exclut les messages PDF et le message « rien à exporter »."""
    return [m["contenu"] for m in messages
            if m["role"] == "ai" and not m["pdf_path"] and m["contenu"] != _MSG_RIEN]


def _titre_pdf(contenu, sujet, titre_conv):
    """Sujet explicite, sinon premier titre # / ## du contenu, sinon titre de conversation."""
    if sujet:
        return sujet[:60]
    m = _TITRE_MD.search(contenu or "")
    t = m.group(1).replace("*", "").replace("`", "").strip() if m else ""
    return (t or titre_conv)[:60]


def _repondre_pdf(cid, conv, msg, d):
    """Demande de PDF : règles fixes. Gemini seulement pour un sujet sans réponse préalable."""
    from modules.exporters.pdf import generer_pdf_bytes
    from modules.gemini_handler import analyser_texte
    ias = _reponses_ia(conv["messages"])
    note, contenu = "", ""
    if d["portee"] == "tout":
        contenu = "\n\n".join(ias)
    elif d["portee"] == "partie":
        contenu = next((p for p in (extraire_partie(c, d["partie"]) for c in reversed(ias)) if p), "")
        if not contenu and ias:
            contenu = ias[-1]
            note = f"Partie « {d['partie']} » introuvable : PDF du dernier message. "
    elif ias:
        contenu = ias[-1]
    sujet = d.get("sujet")
    try:
        if sujet and not (contenu and sujet_dans(contenu, sujet)):
            contenu = analyser_texte(f"Rédige un exposé structuré en Markdown sur : {sujet}", CHAT_PROMPT)
        if not contenu:
            rep, rel = _MSG_RIEN, None
        else:
            titre_pdf = _titre_pdf(contenu, sujet, conv["titre"])
            PDF_DIR.mkdir(parents=True, exist_ok=True)
            fichier = PDF_DIR / f"{uuid.uuid4().hex}.pdf"
            fichier.write_bytes(generer_pdf_bytes(contenu, titre_pdf, "moderne"))
            rel, rep = f"pdfs/{fichier.name}", f"{note}PDF prêt : {titre_pdf}"
    except Exception as e:
        print(f"chat pdf: {e}")
        return jsonify({"error": "Génération PDF échouée"}), 502
    chat_db.ajouter_message(cid, "user", msg)
    mid = chat_db.ajouter_message(cid, "ai", rep, pdf_path=rel)
    titre = conv["titre"]
    if not conv["messages"] and titre == "Nouvelle discussion":
        titre = _titre_conv(msg)
        chat_db.renommer(cid, titre)
    return jsonify({"reponse": rep, "message_id": mid, "titre": titre, "sources": [],
                    "web_statut": None, "image_path": None, "pdf_path": rel})


PROMPT_SUJET = ("Extrais le sujet de recherche web de la dernière question de l'étudiant, "
                "en 5 mots maximum, en français, sans ponctuation ni guillemets. "
                "Corrige les fautes de frappe évidentes et remplace « palu » par paludisme. Réponds uniquement par ces mots.")


import os as _os
import re as _re
from config import MODEL_SMART as _MS

_MODELE_CHAT = _os.environ.get("GEMINI_MODEL_CHAT") or _MS
_RE_MARQ = _re.compile(r"\[\[\s*img:\s*([^\]\n]{2,80}?)\s*\]\]", _re.I)


def _extraire_marqueurs(rep):
    """Texte sans marqueurs [[img: ...]] + [(requete, indice du bloc precedent)]. Blocs = separes par une ligne vide."""
    if not rep or not _RE_MARQ.search(rep):
        return rep, []
    blocs, marq = [], []
    for b in _re.split(r"\n\s*\n", rep.strip()):
        requetes = _RE_MARQ.findall(b)
        propre = _RE_MARQ.sub("", b).strip()
        if propre:
            blocs.append(propre)
        for q in requetes:
            marq.append((q.strip(), max(len(blocs) - 1, 0)))
    return "\n\n".join(blocs), marq


_PROMPT_VISION = (
    "Tu choisis les images qui illustreront une réponse de cours. Pour chaque EMPLACEMENT, des images candidates numérotées te sont montrées. "
    "Garde celle qui illustre le mieux ce que la réponse explique à cet endroit. "
    "Pour l'anatomie ou un mécanisme, préfère une image dont les noms des parties sont lisibles, en français si possible, sinon en anglais ; "
    "écarte les noms dans une autre langue, les images floues ou sans rapport. Si aucune ne convient, réponds null pour cet emplacement. "
    "Vérifie que l'image montre bien le SUJET de l'emplacement : une image d'un autre sujet (maladie, autre organe, autre animal) = null, même si c'est la seule. "
    "Réponds uniquement par un tableau JSON, un élément par emplacement : [{\"i\": numéro de l'emplacement, \"choix\": numéro de l'image ou null, \"raison\": une phrase courte en français (langue des noms, lisibilité, pertinence)}]."
)
_FORMATS_VISION = {"image/png", "image/jpeg", "image/webp"}


def _ua_commons():
    from modules.commons import _UA
    return _UA


def _telecharger(url):
    import time
    import requests
    for essai in range(2):
        try:
            r = requests.get(url, headers={"User-Agent": _ua_commons()}, timeout=15)
            if r.status_code == 429 and essai == 0:
                time.sleep(2)
                continue
            r.raise_for_status()
            break
        except Exception as e:
            print(f"chat vision telechargement: {e}")
            return None
    mime = r.headers.get("content-type", "").split(";")[0].strip().lower()
    if mime not in _FORMATS_VISION or len(r.content) > 2_000_000:
        return None
    return _reduire(r.content) or (r.content, mime)


def _vision_choix(cands, contenu):
    """Un seul appel de vision pour tous les emplacements. -> [index du candidat ou None] par emplacement, None si impossible."""
    from concurrent.futures import ThreadPoolExecutor
    from google.genai import types
    from modules.gemini_handler import MODELE_BASE, analyser_contenus
    taches = [(s, k, c["url"]) for s, (_, _, cs) in enumerate(cands) for k, c in enumerate(cs)]
    with ThreadPoolExecutor(max_workers=2) as ex:
        res = list(ex.map(lambda t: _telecharger(t[2]), taches))
    vus = {}
    for (s, k, _), r in zip(taches, res):
        if r:
            vus.setdefault(s, []).append((k, r[0], r[1]))
    if not vus:
        return None
    contenus = [f"Réponse du tuteur (contexte) :\n{contenu[:1500]}"]
    for s, (_, q, _cs) in enumerate(cands):
        contenus.append(f"EMPLACEMENT {s + 1} — sujet : {q}")
        for n, (_k, data, mime) in enumerate(vus.get(s, []), 1):
            contenus.append(f"Image {s + 1}.{n} :")
            contenus.append(types.Part.from_bytes(data=data, mime_type=mime))
    contenus.append(_PROMPT_VISION)
    cfg = types.GenerateContentConfig(response_mime_type="application/json",
                                      thinking_config=types.ThinkingConfig(thinking_level="low"))
    tok = MODELE_BASE.set(_MODELE_CHAT)
    try:
        import time as _tv
        _t = _tv.monotonic()
        rep = analyser_contenus(contenus, cfg)
        print(f"chat vision: appel en {_tv.monotonic() - _t:.0f} s, {sum(len(v) for v in vus.values())} image(s)")
    finally:
        MODELE_BASE.reset(tok)
    m = _re.search(r"\[.*\]", rep or "", _re.S)
    arr = json.loads(m.group(0)) if m else []
    choix = []
    for s in range(len(cands)):
        liste = vus.get(s, [])
        if not liste:
            choix.append(0)
            continue
        item = next((x for x in arr if isinstance(x, dict) and x.get("i") == s + 1), None)
        if item is None:
            choix.append(liste[0][0])
            continue
        n = item.get("choix")
        print(f"chat vision: emplacement {s + 1}: choix={n!r}, raison={str(item.get('raison', ''))[:160]!r}")
        if n is None:
            choix.append(None)
        else:
            mm = _re.fullmatch(r"\s*(?:(\d+)\.)?(\d+)\s*", str(n))
            if mm and mm.group(1) in (None, str(s + 1)) and 1 <= int(mm.group(2)) <= len(liste):
                choix.append(liste[int(mm.group(2)) - 1][0])
            else:
                print(f"chat vision: emplacement {s + 1}: choix illisible {n!r}, repli sur le 1er candidat")
                choix.append(liste[0][0])
    return choix


_GENERIQUES = {"diagram", "labeled", "labelled", "scheme", "chart", "anatomy", "structure", "human", "system",
               "overview", "and", "of", "the", "in", "with", "fr", "illustration", "drawing"}


def _pertinents(q, items):
    """Garde les candidats dont le titre ou le nom de fichier contient un mot du sujet (hors mots generiques)."""
    mots = [w for w in _re.findall(r"[a-z]{3,}", q.lower()) if w not in _GENERIQUES]
    if not mots:
        return items
    out = [x for x in items if any(m[:5] in (x.get("titre", "") + " " + x.get("page", "")).lower() for m in mots)]
    if len(out) < len(items):
        print(f"chat images: {q!r}: {len(items) - len(out)} candidat(s) hors sujet ecarte(s)")
    return out


_LANGUES = set("az tr es ar zh ja ko ru de it pt nl pl uk bn hi ml ta te th vi id fa he el sv da fi cs hu ro bg sr hr kk mn ln ku".split())


def _rang_langue(x):
    """0 = fichier _fr, 1 = anglais ou sans code de langue, 2 = langue etrangere connue."""
    m = _re.search(r"[ _-]([a-z]{2,3})\.\w+$", x.get("page", ""), _re.I)
    code = m.group(1).lower() if m else ""
    return 0 if code == "fr" else 2 if code in _LANGUES else 1


def _reduire(data):
    """Miniature 512 px en JPEG pour la vision (charge reseau divisee). None si echec."""
    try:
        import io
        from PIL import Image
        im = Image.open(io.BytesIO(data))
        im.load()
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            fond = Image.new("RGB", im.size, "white")
            fond.paste(im, mask=im.split()[-1])
            im = fond
        else:
            im = im.convert("RGB")
        im.thumbnail((512, 512))
        out = io.BytesIO()
        im.save(out, "JPEG", quality=70)
        return out.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"chat vision reduction: {e}")
        return None


def _choisir_images(slots, contenu):
    """Candidats Commons par emplacement, puis le modele regarde et choisit (ou rejette). Repli : 1er candidat.
    Une meme image n'est jamais posee deux fois."""
    from modules.commons import chercher_images
    import time as _t
    t0 = _t.monotonic()
    n = 3
    cands, vus = [], set()
    for q, apres in slots:
        if q.lower() in vus:
            continue
        vus.add(q.lower())
        try:
            c = _pertinents(q, chercher_images(q, n=12))
            if len(c) < 3:
                try:
                    from modules.commons import chercher_images_exa
                    deja = {x["page"] for x in c}
                    c += [x for x in _pertinents(q, chercher_images_exa(q)) if x["page"] not in deja]
                except Exception as e:
                    print(f"chat images: exa: {e}")
            c = sorted(c, key=_rang_langue)[:n]
            if _re.search(r"diagram|labell?ed", q, _re.I):
                try:
                    fr = [x for x in chercher_images(q + " fr", n=6) if _re.search(r"[ _-]fr\.\w+$", x["page"], _re.I)]
                except Exception:
                    fr = []
                if fr:
                    c = (fr[:1] + [x for x in c if x["page"] != fr[0]["page"]])[:n]
        except Exception as e:
            print(f"chat images: {e}")
            continue
        if c:
            print(f"chat images: {q!r} -> {len(c)} candidat(s): " + ", ".join(x["page"].rsplit("/", 1)[-1][:40] for x in c))
            cands.append((apres, q, c))
        else:
            print(f"chat images: aucune pour {q!r}")
    if not cands:
        return []
    try:
        choix = _vision_choix(cands, contenu)
    except Exception as e:
        print(f"chat vision: {e}")
        choix = None
    out, pris = [], set()
    for i, (apres, q, c) in enumerate(cands):
        k = 0 if choix is None else choix[i]
        if k is None:
            print(f"chat vision: aucune image retenue pour {q!r}")
            continue
        x = c[k]
        if x["page"] in pris:
            x = next((y for y in c if y["page"] not in pris), None) if choix is None else None
        if x is None:
            continue
        pris.add(x["page"])
        print(f"chat images: emplacement {i + 1}: retenue {x['page'].rsplit('/', 1)[-1][:60]} (candidat {k + 1})")
        out.append({**x, "apres": apres})
    print(f"chat images: {len(out)} retenue(s) sur {len(cands)} emplacement(s) en {_t.monotonic() - t0:.0f} s")
    return out


@bp.route("/messages/<int:mid>/images", methods=["POST"])
def resoudre_images(mid):
    m = chat_db.lire_message(mid)
    if not m or m["role"] != "ai":
        return jsonify({"error": "Message introuvable"}), 404
    slots = []
    for s in ((request.get_json(silent=True) or {}).get("slots") or [])[:5]:
        q = str((s or {}).get("q", "")).strip()[:80]
        a = (s or {}).get("apres")
        if len(q) >= 2:
            slots.append((q, a if isinstance(a, int) and not isinstance(a, bool) and 0 <= a < 200 else None))
    imgs = _choisir_images(slots, m["contenu"])
    if imgs:
        chat_db.maj_images(mid, json.dumps(imgs, ensure_ascii=False))
    return jsonify({"images": imgs})


PROMPT_SUJET_IMG = (
    "Donne uniquement le nom du sujet à illustrer par une image, en français, 1 à 3 mots. "
    "Sans les mots image, photo, schéma, illustration, traitement, définition, explication. "
    "Corrige les fautes de frappe (palu, palus, palusdime = paludisme). "
    "Utilise le terme complet du domaine. Réponds par le sujet seul, sans ponctuation ni phrase."
)


def _sujet_image(messages: list[dict], msg: str) -> str:
    """Sujet court pour Commons (distinct de _sujet_web). Repli : message nettoyé, ne bloque jamais."""
    import re
    from modules.gemini_handler import analyser_texte
    prec = next((m["contenu"] for m in reversed(messages) if m["role"] == "user"), "")
    entree = (f"Question précédente : {prec[:200]}\n" if prec else "") + f"Dernière question : {msg[:300]}"
    try:
        s = " ".join((analyser_texte(entree, PROMPT_SUJET_IMG) or "").split()).strip(" \"'.")
    except Exception as e:
        print(f"sujet image: {e}")
        s = ""
    if s and len(s) <= 40 and len(s.split()) <= 4:
        return s
    brut = re.sub(r"(?i)\b(c'est quoi|qu'est-ce que|explique|expliquer|montre|montres|montrer|affiche|ajoute|"
                  r"avec|et|des|de|du|la|le|les|un|une|moi|images?|photos?|illustrations?|sch[ée]mas?)\b", " ", msg)
    return " ".join(brut.replace("?", " ").split())[:60] or msg[:60]


def _sujet_web(messages: list[dict], msg: str) -> str:
    """Sujet de recherche extrait par Gemini. Repli sur l'heuristique : ne bloque jamais l'envoi."""
    from modules.gemini_handler import analyser_texte
    prec = next((m["contenu"] for m in reversed(messages) if m["role"] == "user"), "")
    entree = (f"Question précédente : {prec[:300]}\n" if prec else "") + f"Dernière question : {msg[:300]}"
    try:
        s = " ".join((analyser_texte(entree, PROMPT_SUJET) or "").split()).strip(" \"'.")
    except Exception as e:
        print(f"sujet web: {e}")
        s = ""
    if not s or len(s) > 80 or len(s.split()) > 8:
        return _requete_web(messages, msg)
    return s


def _repondre_images(cid, conv, msg, sujet):
    """Demande d'image : Commons cote serveur, aucun appel Gemini, aucune URL inventee."""
    from modules.commons import chercher_images
    try:
        imgs = chercher_images(sujet)
    except Exception as e:
        print(f"chat images: {e}")
        return jsonify({"error": "Wikimedia Commons injoignable, reessaie"}), 502
    rep = (f"Images libres de droits pour « {sujet} » (Wikimedia Commons)." if imgs
           else f"Aucune image libre trouvee pour « {sujet} ».")
    chat_db.ajouter_message(cid, "user", msg)
    mid = chat_db.ajouter_message(cid, "ai", rep,
                                  images_json=(json.dumps(imgs, ensure_ascii=False) if imgs else None))
    titre = conv["titre"]
    if not conv["messages"] and titre == "Nouvelle discussion":
        titre = _titre_conv(msg)
        chat_db.renommer(cid, titre)
    return jsonify({"reponse": rep, "message_id": mid, "titre": titre, "sources": [],
                    "web_statut": None, "image_path": None, "pdf_path": None, "images": imgs})
