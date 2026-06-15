from modules.gemini_handler import analyser_texte, analyser_image

SYSTEM_PROMPT = """Tu es un assistant pédagogique expert, intelligent et adaptatif.
Avant de répondre, tu analyses toujours :
1. La nature du sujet (maladie, concept, théorie, processus...)
2. Le domaine (médecine, sciences, histoire, droit...)
3. Ce que ce type de sujet nécessite obligatoirement comme sections
4. Le niveau de profondeur adapté au contenu

Pour une maladie → tu inclus automatiquement : définition, épidémiologie, 
causes/étiologie, physiopathologie, signes/symptômes, diagnostic, 
traitement, prévention, conclusion.

Pour un concept scientifique → définition, historique, mécanismes, 
applications, limites, conclusion.

Pour un processus → étapes, mécanismes, facteurs influents, applications.

Tu t'adaptes intelligemment. Tu réponds toujours en français."""

def _prompt(mode_texte: str) -> str:
    return f"""{SYSTEM_PROMPT}

--- TÂCHE ---
{mode_texte}"""

MODES = {
    1: _prompt("""Analyse ce contenu et explique-le clairement.
Adapte la longueur à la complexité réelle du sujet.
Pas de structure imposée — réponds comme un prof qui explique naturellement."""),

    2: _prompt("""Analyse ce contenu et génère un exposé COMPLET.
Détermine toi-même la meilleure structure selon le type de sujet.
Inclus obligatoirement : plan détaillé, introduction, développement 
structuré, exemples concrets, tableaux si pertinent, conclusion, 
points clés à retenir."""),

    3: _prompt("""Analyse ce contenu et génère des flashcards.
Détermine toi-même le nombre selon la richesse du contenu.
Couvre tous les aspects importants.
Format JSON uniquement, rien d'autre :
[{"question": "...", "reponse": "..."}]"""),

    4: _prompt("""Analyse ce contenu et génère des QCM variés et pertinents.
Détermine toi-même le nombre selon le contenu.
Assure-toi de couvrir tous les aspects importants.
Format JSON uniquement, rien d'autre :
[{"question":"...","choix":["A)...","B)...","C)...","D)..."],
"reponse":"A","explication":"..."}]"""),

    5: _prompt("""Analyse ce contenu et génère un plan de révision intelligent.
- Thèmes identifiés avec niveau de difficulté réel
- Ordre de révision optimal avec justification  
- Temps estimé réaliste par thème
- Points critiques à maîtriser absolument
- Stratégie adaptée au type de contenu
- Questions types susceptibles d'être posées à l'examen"""),

    6: _prompt("""Analyse ce contenu et génère un plan d'exposé optimal.
Adapte la structure au type de sujet détecté.
Pour chaque section indique : titre, points à développer, 
définitions clés, exemples à utiliser.
Justifie brièvement tes choix de structure."""),

    7: _prompt("""Génère un résumé en exactement 3 niveaux :
NIVEAU 1 — 3 lignes : l'essentiel absolu
NIVEAU 2 — 10 lignes : les points importants  
NIVEAU 3 — complet : tout ce qu'il faut savoir
Sépare clairement les 3 niveaux."""),

    8: _prompt("""Génère une mind map textuelle de ce contenu.
Format :
[SUJET CENTRAL]
├── Thème 1
│   ├── Sous-thème 1.1
│   └── Sous-thème 1.2
├── Thème 2
│   ├── Sous-thème 2.1
│   └── Sous-thème 2.2
Identifie toi-même les thèmes selon le contenu."""),

    9: _prompt("""Mode examen. Génère un examen complet sur ce contenu :
- 5 QCM (2 points chacun)
- 2 questions courtes (5 points chacune)  
- 1 question de synthèse (10 points)
Total : 30 points
Présente d'abord les questions SANS les réponses.
Termine par : '--- CORRIGÉ ---' avec toutes les réponses."""),
}

def generer(contenu: str, mode: int, est_image: bool = False,
            contexte: str = "") -> str:
    prompt = MODES.get(mode, MODES[1])
    if contexte:
        prompt += f"\n\nContexte supplémentaire : {contexte}"
    if est_image:
        return analyser_image(contenu, prompt)
    else:
        return analyser_texte(contenu, prompt)

def generer_avec_plan(contenu: str, plan: str, est_image: bool = False) -> str:
    prompt = f"""{SYSTEM_PROMPT}

L'utilisateur a fourni ce plan :
{plan}

Génère un exposé COMPLET en suivant exactement ce plan.
Adapte la profondeur de chaque section selon son importance réelle."""
    if est_image:
        return analyser_image(contenu, prompt)
    else:
        return analyser_texte(contenu, prompt)

def generer_conversation(contenu: str, question: str,
                         est_image: bool = False) -> str:
    prompt = f"""{SYSTEM_PROMPT}

Voici le contenu du cours :
---
{contenu}
---

L'étudiant pose cette question : {question}

Réponds directement et précisément à cette question
en te basant sur le contenu fourni.
Si la question dépasse le contenu, indique-le clairement."""
    if est_image:
        return analyser_image(contenu,
            f"Question sur ce cours : {question}\nRéponds précisément.")
    else:
        return analyser_texte(contenu, prompt)


def proposer_plan(sujet: str, contexte: str = "", longueur: str = "complet",
                  consigne_perso: str = "") -> str:
    """
    Étape 1 de l'Option C.
    longueur : "court" | "moyen" | "long" | "complet" | "perso"
    consigne_perso : instruction libre si longueur == "perso"
    """
    specs = {
        "court":   "Plan COURT : 3 à 4 sections maximum. Essentiel uniquement.",
        "moyen":   "Plan MOYEN : 4 à 6 sections. Structuré et clair.",
        "long":    "Plan LONG : 6 à 8 sections. Détaillé avec sous-parties.",
        "complet": "Plan COMPLET : autant de sections que nécessaire. Exhaustif.",
        "perso":   f"Instruction personnalisée : {consigne_perso}" if consigne_perso
                   else "Plan MOYEN : 4 à 6 sections.",
    }
    spec = specs.get(longueur, specs["complet"])
    ctx  = f"\nContexte : {contexte}" if contexte else ""

    prompt = f"""{SYSTEM_PROMPT}

Le sujet est : {sujet}{ctx}

Contrainte : {spec}

Propose le meilleur plan selon cette contrainte.

Réponds UNIQUEMENT en JSON, sans texte avant ou après :
[
  {{"numero": "I", "titre": "Titre de la section", "points": ["Point clé 1", "Point clé 2"]}},
  {{"numero": "II", "titre": "...", "points": ["...", "..."]}},
  ...
]"""
    return analyser_texte(sujet, prompt)


def generer_section(sujet: str, plan_complet: list, index_section: int,
                    contenu_precedent: str = "", est_image: bool = False,
                    contenu: str = "", longueur: str = "complet",
                    consigne_perso: str = "") -> str:
    """
    Étape 2 de l'Option C — génère une section à la fois.
    longueur : "court" | "moyen" | "long" | "complet" | "perso"
    """
    section = plan_complet[index_section]
    total   = len(plan_complet)

    profondeur = {
        "court":   "Sois CONCIS — 1 paragraphe par point. Maximum 15 lignes.",
        "moyen":   "Sois CLAIR — 2 paragraphes par point. Entre 15 et 30 lignes.",
        "long":    "Sois DÉTAILLÉ — exemples inclus. Entre 30 et 50 lignes.",
        "complet": "Sois EXHAUSTIF — développe au maximum, tableaux et exemples.",
        "perso":   f"Instruction personnalisée à respecter STRICTEMENT : {consigne_perso}"
                   if consigne_perso else "Sois exhaustif.",
    }.get(longueur, "Sois exhaustif.")

    plan_txt   = "\n".join(f"{s['numero']}. {s['titre']}" for s in plan_complet)
    points_txt = "\n".join(f"- {p}" for p in section.get("points", []))

    ctx_precedent = ""
    if contenu_precedent:
        ctx_precedent = f"""
Sections déjà rédigées (pour cohérence) :
---
{contenu_precedent[-2000:]}
---"""

    prompt = f"""{SYSTEM_PROMPT}

Sujet global : {sujet}

Plan complet :
{plan_txt}

Rédige UNIQUEMENT la section {section['numero']} : {section['titre']}
Points à couvrir :
{points_txt}
{ctx_precedent}

{profondeur}
{"C'est l'introduction — pose le contexte général." if index_section == 0 else ""}
{"C'est la conclusion — synthétise et ouvre sur des perspectives." if index_section == total - 1 else ""}
Utilise ## et ### pour structurer.
"""

    if est_image and contenu:
        return analyser_image(contenu, prompt)
    elif contenu and not est_image:
        return analyser_texte(contenu, prompt)
    else:
        return analyser_texte(sujet, prompt)