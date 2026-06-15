import os
import sys
import json
from config import INPUT_DIR, OUTPUT_DIR
from modules.database import (init_db, save_session, save_cards,
                               get_due_cards, update_card,
                               record_review, get_stats,
                               get_maitrise_par_sujet)
from modules.spacedrepetition import sm2

def afficher_menu():
    print("\n" + "="*55)
    print("      STUDY AGENT — Propulsé par Gemini 3.1")
    print("="*55)
    print("  [1]  Explication directe")
    print("  [2]  Exposé complet")
    print("  [3]  Flashcards interactives")
    print("  [4]  QCM avec corrigés")
    print("  [5]  Plan de révision")
    print("  [6]  Plan d'exposé automatique")
    print("  [7]  Résumé progressif (3 niveaux)")
    print("  [8]  Mind map")
    print("  [9]  Mode examen")
    print("  [10] Mode conversation (poser des questions)")
    print("  [11] Exposé depuis mon propre plan")
    print("  [12] Révision espacée (cartes dues aujourd'hui)")
    print("  [13] Score de maîtrise par sujet")
    print("  [0]  Quitter")
    print("="*55)

def choisir_entree():
    print("\n" + "="*55)
    print("Source du cours :")
    print("  [1] Image / photo (dossier inputs/)")
    print("  [2] Texte (coller directement)")
    choix = input("\nTon choix : ").strip()

    if choix == "1":
        fichiers = [f for f in os.listdir(INPUT_DIR)
                    if f.lower().endswith(('.jpg','.jpeg','.png','.pdf'))]
        if not fichiers:
            print("❌ Dossier inputs/ vide.")
            sys.exit()
        print("\nImages disponibles :")
        for i, f in enumerate(fichiers):
            print(f"  [{i}] {f}")
        idx = int(input("Choix : "))
        return os.path.join(INPUT_DIR, fichiers[idx]), True
    else:
        print("\nColle ton texte (ligne vide pour terminer) :")
        lignes = []
        while True:
            ligne = input()
            if ligne == "":
                break
            lignes.append(ligne)
        return "\n".join(lignes), False

def demander_contexte():
    print("\nContexte supplémentaire ? (niveau, objectif, examen...)")
    print("Appuie sur Entrée pour ignorer.")
    return input("Contexte : ").strip()

def proposer_export(resultat: str, nom_fichier: str):
    print("\n" + "-"*55)
    choix = input("Exporter ? [1] Fichier .txt  [2] PDF  [Entrée] Non : ").strip()
    if choix == "1":
        sauvegarder_txt(resultat, nom_fichier)
    elif choix == "2":
        sauvegarder_pdf(resultat, nom_fichier)
    else:
        print("✓ Résultat affiché uniquement.")

def sauvegarder_txt(contenu: str, nom: str):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    chemin = os.path.join(OUTPUT_DIR, f"{nom}.txt")
    with open(chemin, "w", encoding="utf-8") as f:
        f.write(contenu)
    print(f"✅ Sauvegardé : {chemin}")

def sauvegarder_pdf(contenu: str, nom: str):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import (SimpleDocTemplate, Paragraph,
                                        Spacer, HRFlowable)
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER

        os.makedirs(OUTPUT_DIR, exist_ok=True)
        chemin = os.path.join(OUTPUT_DIR, f"{nom}.pdf")
        doc = SimpleDocTemplate(chemin, pagesize=A4,
                                leftMargin=2.5*cm, rightMargin=2.5*cm,
                                topMargin=2.5*cm, bottomMargin=2.5*cm)
        styles = getSampleStyleSheet()
        style_titre = ParagraphStyle('titre',
            fontName='Helvetica-Bold', fontSize=18,
            textColor=colors.HexColor("#1a3557"),
            alignment=TA_CENTER, spaceAfter=20)
        style_corps = ParagraphStyle('corps',
            fontName='Helvetica', fontSize=11,
            leading=16, spaceAfter=8,
            alignment=TA_JUSTIFY)

        story = []
        story.append(Paragraph(nom.replace("_", " ").upper(), style_titre))
        story.append(HRFlowable(width="100%", thickness=1,
                                color=colors.HexColor("#1a3557"),
                                spaceAfter=15))
        for ligne in contenu.split("\n"):
            ligne = ligne.strip()
            if not ligne:
                story.append(Spacer(1, 6))
                continue
            ligne_safe = (ligne.replace("&","&amp;")
                              .replace("<","&lt;")
                              .replace(">","&gt;"))
            if ligne.startswith("# "):
                p = ParagraphStyle('h1', fontName='Helvetica-Bold',
                    fontSize=15, textColor=colors.HexColor("#185FA5"),
                    spaceBefore=14, spaceAfter=6)
                story.append(Paragraph(ligne_safe[2:], p))
            elif ligne.startswith("## "):
                p = ParagraphStyle('h2', fontName='Helvetica-Bold',
                    fontSize=13, textColor=colors.HexColor("#1a3557"),
                    spaceBefore=10, spaceAfter=4)
                story.append(Paragraph(ligne_safe[3:], p))
            elif ligne.startswith("### "):
                p = ParagraphStyle('h3', fontName='Helvetica-Bold',
                    fontSize=11, textColor=colors.HexColor("#3B6D11"),
                    spaceBefore=8, spaceAfter=3)
                story.append(Paragraph(ligne_safe[4:], p))
            elif ligne.startswith(("- ", "* ", "• ")):
                p = ParagraphStyle('bullet', fontName='Helvetica',
                    fontSize=11, leading=15, leftIndent=15, spaceAfter=4)
                story.append(Paragraph("• " + ligne_safe[2:], p))
            else:
                story.append(Paragraph(ligne_safe, style_corps))

        doc.build(story)
        print(f"✅ PDF sauvegardé : {chemin}")
    except Exception as e:
        print(f"❌ Erreur PDF : {e}")
        sauvegarder_txt(contenu, nom)

def mode_flashcards_interactif(resultat: str):
    try:
        texte = resultat.strip()
        if texte.startswith("```"):
            texte = texte.split("```")[1]
            if texte.startswith("json"):
                texte = texte[4:]
        cards = json.loads(texte)
        total = len(cards)
        score = 0
        print(f"\n{'='*55}")
        print(f"  {total} flashcards — appuie sur Entrée pour voir la réponse")
        print(f"{'='*55}")
        for i, card in enumerate(cards, 1):
            print(f"\n[{i}/{total}] {card['question']}")
            input("  → Entrée pour la réponse...")
            print(f"  ✓ {card['reponse']}")
            r = input("  Tu savais ? [o/n] : ").strip().lower()
            if r == "o":
                score += 1
        print(f"\n{'='*55}")
        print(f"  Score : {score}/{total} ({round(score/total*100)}%)")
        if score/total >= 0.8:
            print("  Excellent ! Tu maîtrises bien ce contenu.")
        elif score/total >= 0.5:
            print("  Bien ! Relis les points que tu n'avais pas.")
        else:
            print("  Continue à réviser — relis le cours et retente.")
        print(f"{'='*55}")
    except Exception:
        print(resultat)

def mode_qcm_interactif(resultat: str):
    try:
        texte = resultat.strip()
        if texte.startswith("```"):
            texte = texte.split("```")[1]
            if texte.startswith("json"):
                texte = texte[4:]
        questions = json.loads(texte)
        total = len(questions)
        score = 0
        print(f"\n{'='*55}")
        print(f"  QCM — {total} questions")
        print(f"{'='*55}")
        for i, q in enumerate(questions, 1):
            print(f"\n[{i}/{total}] {q['question']}")
            for choix in q['choix']:
                print(f"  {choix}")
            rep = input("\nTa réponse (A/B/C/D) : ").strip().upper()
            if rep == q['reponse'].upper():
                print("  ✅ Correct !")
                score += 1
            else:
                print(f"  ❌ Incorrect. Bonne réponse : {q['reponse']}")
            print(f"  → {q['explication']}")
        print(f"\n{'='*55}")
        print(f"  Score final : {score}/{total} ({round(score/total*100)}%)")
        if score/total >= 0.8:
            print("  Excellent !")
        elif score/total >= 0.5:
            print("  Bien — relis les points manqués.")
        else:
            print("  Révise ce contenu et retente.")
        print(f"{'='*55}")
        return score, total
    except Exception:
        print(resultat)
        return 0, 0

def mode_maitrise():
    sujets = get_maitrise_par_sujet()

    print(f"\n{'='*60}")
    print("  SCORE DE MAÎTRISE PAR SUJET")
    print(f"{'='*60}")

    if not sujets:
        print("\n  Aucun sujet trouvé. Fais d'abord des flashcards (mode 3).")
        return

    for s in sujets:
        pct   = s["score_pct"]
        bars  = round(pct / 10)               # 0 à 10 blocs
        barre = "█" * bars + "░" * (10 - bars)

        # Niveau
        if pct >= 80:
            niveau = "✅ Maîtrisé"
        elif pct >= 50:
            niveau = "📈 En progrès"
        else:
            niveau = "🔁 À retravailler"

        # Ligne sujet
        sujet_affiche = s["subject"][:35].ljust(35)
        print(f"\n  {sujet_affiche}")
        print(f"  {barre}  {pct}%  —  {niveau}")
        print(f"  Cartes : {s['maitrisees']}/{s['total']} maîtrisées  |  "
              f"Intervalle moyen : {s['intervalle_moyen']}j  |  "
              f"Dues : {s['dues']}")

    # Résumé global
    stats = get_stats()
    print(f"\n{'─'*60}")
    print(f"  Total : {stats['total_cards']} cartes  |  "
          f"À réviser aujourd'hui : {stats['due_today']}")
    print(f"{'='*60}")


def mode_revision_espacee():
    stats = get_stats()
    dues = get_due_cards()

    print(f"\n{'='*55}")
    print(f"  RÉVISION ESPACÉE")
    print(f"  Cartes dues aujourd'hui : {stats['due_today']}")
    print(f"  Total cartes : {stats['total_cards']}")
    print(f"{'='*55}")

    if not dues:
        print("\n✅ Aucune carte à réviser aujourd'hui. Reviens demain !")
        return

    score_total = 0
    for i, card in enumerate(dues, 1):
        print(f"\n[{i}/{len(dues)}] 📚 {card['subject']}")
        print(f"  {card['question']}")
        input("  → Entrée pour voir la réponse...")
        print(f"  ✓ {card['answer']}")
        print("\n  Score (0=blackout / 3=correct / 5=parfait) :")
        print("  0: oublié  1: vague  2: faux mais proche")
        print("  3: correct difficile  4: correct  5: parfait")
        while True:
            try:
                score = int(input("  Ton score : ").strip())
                if 0 <= score <= 5:
                    break
                print("  ⚠️  Entre un nombre entre 0 et 5.")
            except ValueError:
                print("  ⚠️  Nombre invalide.")

        updated = sm2(card, score)
        update_card(updated)
        record_review(card["id"], score, updated["interval_days"])

        if score >= 3:
            score_total += 1
            print(f"  ✅ Prochain rappel dans {updated['interval_days']} jour(s).")
        else:
            print(f"  🔁 À revoir demain.")

    print(f"\n{'='*55}")
    print(f"  Session terminée : {score_total}/{len(dues)} cartes maîtrisées")
    print(f"{'='*55}")


def mode_conversation(contenu: str, est_image: bool):
    from modules.generator import generer_conversation
    print(f"\n{'='*55}")
    print("  Mode conversation — pose tes questions sur le cours")
    print("  Tape 'fin' pour quitter")
    print(f"{'='*55}")
    while True:
        question = input("\nTa question : ").strip()
        if question.lower() == "fin":
            break
        if not question:
            continue
        print("\n⏳ Réponse en cours...")
        rep = generer_conversation(contenu, question, est_image)
        print(f"\n{rep}")
        exporter = input("\nExporter cette réponse ? [1] txt  [2] pdf  [Entrée] Non : ").strip()
        if exporter == "1":
            sauvegarder_txt(rep, "conversation")
        elif exporter == "2":
            sauvegarder_pdf(rep, "conversation")

def mode_exposé_mon_plan(contenu: str, est_image: bool):
    from modules.generator import generer_avec_plan
    print("\nColle ton plan (ligne vide pour terminer) :")
    lignes = []
    while True:
        ligne = input()
        if ligne == "":
            break
        lignes.append(ligne)
    plan = "\n".join(lignes)
    if not plan.strip():
        print("❌ Plan vide.")
        return
    print("\n⏳ Génération de l'exposé selon ton plan...")
    resultat = generer_avec_plan(contenu, plan, est_image)
    print(f"\n{'='*55}\n{resultat}")
    proposer_export(resultat, "expose_mon_plan")

def main():
    from modules.generator import generer

    init_db()  # initialisation SQLite (idempotent)

    # Mode 12 — pas besoin de charger un cours
    afficher_menu()
    try:
        mode = int(input("\nTon choix : ").strip())
    except ValueError:
        print("❌ Choix invalide.")
        sys.exit()

    if mode == 0:
        print("Au revoir !")
        sys.exit()

    if mode == 12:
        mode_revision_espacee()
        return

    if mode == 13:
        mode_maitrise()
        return

    contenu, est_image = choisir_entree()

    # Mode conversation — pas de génération initiale
    if mode == 10:
        mode_conversation(contenu, est_image)
        return

    # Mode exposé avec mon plan
    if mode == 11:
        mode_exposé_mon_plan(contenu, est_image)
        return

    # Contexte optionnel
    contexte = demander_contexte()

    print("\n⏳ Génération en cours...")
    resultat = generer(contenu, mode, est_image, contexte)

    noms = {
        1:"explication", 2:"expose", 3:"flashcards",
        4:"qcm", 5:"plan_revision", 6:"plan_expose",
        7:"resume_progressif", 8:"mind_map", 9:"examen"
    }
    nom = noms.get(mode, "resultat")

    # Modes interactifs — pas d'affichage brut
    if mode == 3:
        mode_flashcards_interactif(resultat)
        # Sauvegarde dans SQLite pour répétition espacée
        try:
            texte = resultat.strip()
            if texte.startswith("```"):
                texte = texte.split("```")[1]
                if texte.startswith("json"):
                    texte = texte[4:]
            cards_data = json.loads(texte)
            sujet = contenu[:60] if not est_image else "cours (image)"
            session_id = save_session(sujet, "flashcards",
                                      "image" if est_image else "text")
            save_cards(session_id, cards_data)
        except Exception as e:
            print(f"⚠️  Sauvegarde SQLite échouée : {e}")
        proposer_export(resultat, nom)
        return

    if mode == 4:
        mode_qcm_interactif(resultat)
        proposer_export(resultat, nom)
        return

    # Tous les autres modes — affichage + export optionnel
    print(f"\n{'='*55}\n{resultat}\n{'='*55}")
    proposer_export(resultat, nom)

if __name__ == "__main__":
    main()
