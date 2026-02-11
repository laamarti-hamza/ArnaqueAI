from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ScenarioStep:
    key: str
    name: str
    objective: str
    trigger_keywords: List[str]


TECH_SUPPORT_STEPS: List[ScenarioStep] = [
    ScenarioStep(
        key="contact_opening",
        name="Ouverture",
        objective="Rester poli mais lent. Faire repeter l'identite de l'appelant.",
        trigger_keywords=["bonjour", "microsoft", "support", "service technique", "windows"],
    ),
    ScenarioStep(
        key="problem_claim",
        name="Probleme annonce",
        objective="Demander des precisions confuses sur le probleme pretendu.",
        trigger_keywords=["virus", "alerte", "infecte", "erreur", "securite"],
    ),
    ScenarioStep(
        key="remote_access_request",
        name="Acces distant",
        objective="Faire semblant de ne pas trouver le menu Demarrer et ralentir au maximum.",
        trigger_keywords=["teamviewer", "anydesk", "acces distant", "installer", "telecharger"],
    ),
    ScenarioStep(
        key="credential_or_payment",
        name="Identifiants ou paiement",
        objective="Refuser de partager tout mot de passe et demander une preuve officielle.",
        trigger_keywords=["mot de passe", "password", "carte bancaire", "paiement", "iban", "code"],
    ),
    ScenarioStep(
        key="pressure_closing",
        name="Pression finale",
        objective="Rester calme, multiplier les interruptions et ne rien divulguer.",
        trigger_keywords=["urgent", "tout de suite", "maintenant", "vite", "dernier avertissement"],
    ),
]


def detect_stage_from_text(latest_scammer: str, current_stage: int) -> int:
    text = latest_scammer.lower()
    next_stage = current_stage

    for idx in range(current_stage, len(TECH_SUPPORT_STEPS)):
        step = TECH_SUPPORT_STEPS[idx]
        if any(keyword in text for keyword in step.trigger_keywords):
            next_stage = max(next_stage, idx)

    return min(next_stage, len(TECH_SUPPORT_STEPS) - 1)
