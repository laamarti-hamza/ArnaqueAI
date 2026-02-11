from __future__ import annotations

import random
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Dict, List, Optional

from .agents import AudienceModeratorAgent, DirectorAgent, VictimAgent
from .config import Settings
from .scenario import TECH_SUPPORT_STEPS


def _utc_now_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


@dataclass
class ConversationMessage:
    role: str
    content: str
    timestamp: str
    sound_effects: List[str] = field(default_factory=list)


@dataclass
class SimulationState:
    scenario_name: str = "tech_support_microsoft"
    stage_index: int = 0
    current_objective: str = TECH_SUPPORT_STEPS[0].objective
    director_reason: str = "Simulation initialisee."
    audience_constraint: str = ""
    audience_constraint_turns_left: int = 0
    turn_count: int = 0
    messages: List[ConversationMessage] = field(default_factory=list)
    pending_proposals: List[str] = field(default_factory=list)
    selected_choices: List[str] = field(default_factory=list)
    last_winner: str = ""


class SimulationEngine:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.director = DirectorAgent(settings)
        self.moderator = AudienceModeratorAgent(settings)
        self.victim = VictimAgent(settings)
        self._lock = Lock()
        self.state = SimulationState()

    def reset(self) -> Dict[str, object]:
        with self._lock:
            self.state = SimulationState()
            return self._snapshot_unlocked()

    def snapshot(self) -> Dict[str, object]:
        with self._lock:
            return self._snapshot_unlocked()

    def submit_proposal(self, proposal: str) -> Dict[str, object]:
        clean = proposal.strip()
        if not clean:
            raise ValueError("La proposition audience est vide.")

        with self._lock:
            self.state.pending_proposals.append(clean[:180])
            return self._snapshot_unlocked()

    def select_choices(self, proposals: Optional[List[str]] = None) -> Dict[str, object]:
        with self._lock:
            if proposals:
                for proposal in proposals:
                    clean = str(proposal).strip()
                    if clean:
                        self.state.pending_proposals.append(clean[:180])

            stage_name = TECH_SUPPORT_STEPS[self.state.stage_index].name
            objective = self.state.current_objective
            self.state.selected_choices = self.moderator.select_choices(
                proposals=self.state.pending_proposals,
                stage_name=stage_name,
                objective=objective,
            )
            self.state.pending_proposals = []
            return self._snapshot_unlocked()

    def vote_choice(self, winner_index: int) -> Dict[str, object]:
        with self._lock:
            if not self.state.selected_choices:
                raise ValueError("Aucun choix audience disponible. Lancez /api/audience/select.")
            if winner_index < 0 or winner_index >= len(self.state.selected_choices):
                raise ValueError("winner_index est hors limite.")

            winner = self.state.selected_choices[winner_index]
            self.state.last_winner = winner
            self.state.audience_constraint = winner
            self.state.audience_constraint_turns_left = 2
            return self._snapshot_unlocked()

    def simulate_vote(self) -> Dict[str, object]:
        with self._lock:
            if not self.state.selected_choices:
                raise ValueError("Aucun choix audience disponible pour un vote simule.")
            winner = random.choice(self.state.selected_choices)
            self.state.last_winner = winner
            self.state.audience_constraint = winner
            self.state.audience_constraint_turns_left = 2
            return self._snapshot_unlocked()

    def step(self, scammer_input: str) -> Dict[str, object]:
        clean_input = scammer_input.strip()
        if not clean_input:
            raise ValueError("Le message arnaqueur est vide.")

        with self._lock:
            prior_history = [asdict(msg) for msg in self.state.messages]
            history_window = prior_history[-self.settings.max_history_messages :]

            self.state.turn_count += 1
            self._add_message_unlocked(role="scammer", content=clean_input)

            decision = self.director.decide(
                latest_scammer=clean_input,
                history=history_window,
                current_stage=self.state.stage_index,
            )
            self.state.stage_index = decision.stage_index
            self.state.current_objective = decision.objective
            self.state.director_reason = decision.reason

            stage_name = TECH_SUPPORT_STEPS[self.state.stage_index].name
            victim_reply = self.victim.respond(
                latest_scammer=clean_input,
                history=history_window,
                objective=self.state.current_objective,
                audience_constraint=self.state.audience_constraint,
                stage_name=stage_name,
            )
            self._add_message_unlocked(
                role="victim",
                content=victim_reply.text,
                sound_effects=victim_reply.sound_effects,
            )

            self._tick_audience_constraint_unlocked()
            return self._snapshot_unlocked()

    def _add_message_unlocked(self, role: str, content: str, sound_effects: Optional[List[str]] = None) -> None:
        self.state.messages.append(
            ConversationMessage(
                role=role,
                content=content,
                timestamp=_utc_now_iso(),
                sound_effects=sound_effects or [],
            )
        )

    def _tick_audience_constraint_unlocked(self) -> None:
        if self.state.audience_constraint_turns_left <= 0:
            return
        self.state.audience_constraint_turns_left -= 1
        if self.state.audience_constraint_turns_left == 0:
            self.state.audience_constraint = ""

    def _snapshot_unlocked(self) -> Dict[str, object]:
        llm_runtime_enabled = bool(self.director.chat and self.moderator.chat and self.victim.chat)
        return {
            "scenario_name": self.state.scenario_name,
            "stage_index": self.state.stage_index,
            "stage_name": TECH_SUPPORT_STEPS[self.state.stage_index].name,
            "current_objective": self.state.current_objective,
            "director_reason": self.state.director_reason,
            "audience_constraint": self.state.audience_constraint,
            "audience_constraint_turns_left": self.state.audience_constraint_turns_left,
            "turn_count": self.state.turn_count,
            "messages": [asdict(msg) for msg in self.state.messages],
            "pending_proposals": list(self.state.pending_proposals),
            "selected_choices": list(self.state.selected_choices),
            "last_winner": self.state.last_winner,
            "available_stages": [step.name for step in TECH_SUPPORT_STEPS],
            "llm_enabled": llm_runtime_enabled,
            "llm_configured": self.settings.llm_enabled,
            "llm_provider": self.settings.llm_provider,
            "llm_model": self.settings.llm_model,
        }
