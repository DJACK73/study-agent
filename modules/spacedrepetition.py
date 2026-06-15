from datetime import date, timedelta


def sm2(card: dict, score: int) -> dict:
    """
    Algorithme SM-2 standard.

    score : 0 à 5
        0 = blackout total
        1 = faux, réponse familière
        2 = faux mais réponse facile après
        3 = correct avec difficulté
        4 = correct facilement
        5 = parfait

    Retourne le card mis à jour avec :
        interval_days, ease_factor, repetitions, next_review
    """
    ef = card.get("ease_factor", 2.5)
    reps = card.get("repetitions", 0)
    interval = card.get("interval_days", 1)

    if score < 3:
        # Échec → on remet à zéro
        reps = 0
        interval = 1
    else:
        # Succès → on calcule le prochain intervalle
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            interval = round(interval * ef)

        # Mise à jour de l'ease factor (min 1.3)
        ef = ef + 0.1 - (5 - score) * (0.08 + (5 - score) * 0.02)
        ef = round(max(1.3, ef), 2)
        reps += 1

    next_review = (date.today() + timedelta(days=interval)).isoformat()

    return {
        **card,
        "interval_days": interval,
        "ease_factor": ef,
        "repetitions": reps,
        "next_review": next_review,
    }   