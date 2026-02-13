from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

try:
    from langchain_anthropic import ChatAnthropic
except Exception:
    ChatAnthropic = None

try:
    from langchain_google_genai import ChatGoogleGenerativeAI
except Exception:
    ChatGoogleGenerativeAI = None

try:
    from langchain_google_vertexai import ChatVertexAI
except Exception:
    ChatVertexAI = None

from .config import Settings
from .scenario import TECH_SUPPORT_STEPS, detect_stage_from_text
from .tools import SOUND_TOOL_REGISTRY, extract_sound_effects, run_tool_by_name

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
JSON_LIST_RE = re.compile(r"\[.*\]", re.DOTALL)
LOGGER = logging.getLogger(__name__)


def _to_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    return str(content).strip()


def _dedupe(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def _parse_json_object(raw_text: str) -> Dict[str, object] | None:
    match = JSON_OBJECT_RE.search(raw_text or "")
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def _parse_json_list(raw_text: str) -> List[str] | None:
    match = JSON_LIST_RE.search(raw_text or "")
    if not match:
        return None
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(data, list):
        return None
    normalized = [str(item).strip() for item in data if str(item).strip()]
    return normalized


def _stage_index_from_key(stage_key: str, fallback_stage: int, latest_scammer: str) -> int:
    normalized = (stage_key or "").strip().lower()
    for idx, step in enumerate(TECH_SUPPORT_STEPS):
        if step.key == normalized:
            return idx
    return detect_stage_from_text(latest_scammer, fallback_stage)


def _build_chat_model(settings: Settings, temperature: float):
    if settings.llm_provider == "openai":
        if not settings.openai_api_key:
            return None
        try:
            return ChatOpenAI(
                model=settings.openai_model,
                temperature=temperature,
                api_key=settings.openai_api_key,
            )
        except Exception as exc:
            LOGGER.warning("OpenAI model init failed: %s", exc)
            return None

    if settings.llm_provider == "anthropic":
        if ChatAnthropic is None:
            LOGGER.warning("Anthropic provider selected but langchain-anthropic is not installed.")
            return None
        if not settings.anthropic_api_key:
            LOGGER.warning("Anthropic provider selected but ANTHROPIC_API_KEY is missing.")
            return None
        try:
            return ChatAnthropic(
                model_name=settings.anthropic_model,
                temperature=temperature,
                api_key=settings.anthropic_api_key,
            )
        except Exception as exc:
            LOGGER.warning("Anthropic model init failed: %s", exc)
            return None

    if settings.llm_provider == "gemini":
        if ChatGoogleGenerativeAI is None:
            LOGGER.warning("Gemini provider selected but langchain-google-genai is not installed.")
            return None
        if not settings.google_api_key:
            LOGGER.warning("Gemini provider selected but GOOGLE_API_KEY is missing.")
            return None
        try:
            return ChatGoogleGenerativeAI(
                model=settings.google_model,
                temperature=temperature,
                google_api_key=settings.google_api_key,
            )
        except Exception as exc:
            LOGGER.warning("Gemini model init failed: %s", exc)
            return None

    if settings.llm_provider == "vertex":
        if ChatVertexAI is None:
            LOGGER.warning("Vertex provider selected but langchain-google-vertexai is not installed.")
            return None
        if not settings.google_application_credentials:
            LOGGER.warning("Vertex provider selected but GOOGLE_APPLICATION_CREDENTIALS is missing.")
            return None

        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.google_application_credentials
        kwargs = {
            "temperature": temperature,
            "project": settings.vertex_project_id or None,
            "location": settings.vertex_location,
        }
        try:
            return ChatVertexAI(model=settings.vertex_model, **kwargs)
        except TypeError:
            try:
                return ChatVertexAI(model_name=settings.vertex_model, **kwargs)
            except Exception as exc:
                LOGGER.warning("Vertex model init failed: %s", exc)
                return None
        except Exception as exc:
            LOGGER.warning("Vertex model init failed: %s", exc)
            return None

    return None


@dataclass
class DirectorDecision:
    stage_index: int
    objective: str
    reason: str


@dataclass
class VictimReply:
    text: str
    sound_effects: List[str]


class DirectorAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.chat = _build_chat_model(settings, temperature=0.1)

    def decide(self, latest_scammer: str, history: List[Dict[str, object]], current_stage: int) -> DirectorDecision:
        if self.chat is not None:
            decision = self._decide_with_llm(latest_scammer, history, current_stage)
            if decision is not None:
                return decision

        stage_index = detect_stage_from_text(latest_scammer, current_stage)
        objective = TECH_SUPPORT_STEPS[stage_index].objective
        reason = "Heuristique locale: progression basee sur mots-cles."
        return DirectorDecision(stage_index=stage_index, objective=objective, reason=reason)

    def _decide_with_llm(
        self,
        latest_scammer: str,
        history: List[Dict[str, object]],
        current_stage: int,
    ) -> DirectorDecision | None:
        history_excerpt = "\n".join(
            f"{msg.get('role', 'unknown')}: {msg.get('content', '')}"
            for msg in history[-8:]
        )
        available_stage_keys = ", ".join(step.key for step in TECH_SUPPORT_STEPS)
        current_stage_key = TECH_SUPPORT_STEPS[current_stage].key

        system_prompt = (
            "Tu es le Directeur de Scenario. Tu ne reponds jamais en langage naturel.\n"
            "Tu dois renvoyer strictement un JSON valide avec ce schema:\n"
            '{"next_stage_key":"...", "objective":"...", "reason":"..."}\n'
            f"Stages autorises: {available_stage_keys}.\n"
            "Ne regresse pas de stage. Aucune autre cle n'est autorisee."
        )

        user_prompt = (
            f"Stage actuel: {current_stage_key}\n"
            f"Dernier message arnaqueur: {latest_scammer}\n"
            f"Historique recent:\n{history_excerpt}"
        )

        try:
            raw = self.chat.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        except Exception as exc:
            LOGGER.warning("Director LLM call failed; fallback to heuristic: %s", exc)
            return None

        payload = _parse_json_object(_to_text(raw.content))
        if payload is None:
            return None

        stage_key = str(payload.get("next_stage_key", "")).strip()
        objective = str(payload.get("objective", "")).strip()
        reason = str(payload.get("reason", "")).strip()

        stage_index = _stage_index_from_key(stage_key, current_stage, latest_scammer)
        if not objective:
            objective = TECH_SUPPORT_STEPS[stage_index].objective
        if not reason:
            reason = "LLM decision sans justification explicite."
        return DirectorDecision(stage_index=stage_index, objective=objective, reason=reason)


class AudienceModeratorAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.chat = _build_chat_model(settings, temperature=0.2)

    def select_choices(self, proposals: List[str], stage_name: str, objective: str) -> List[str]:
        cleaned = self._sanitize_proposals(proposals)
        if not cleaned:
            return []

        corrected = self._correct_proposals(cleaned)
        if not corrected:
            return []

        if len(corrected) <= 3:
            return corrected

        if self.chat is not None:
            picked = self._select_with_llm(corrected, stage_name, objective)
            if picked:
                return picked

        return corrected[:3]

    def _correct_proposals(self, proposals: List[str]) -> List[str]:
        if self.chat is None:
            return proposals

        corrected = self._correct_with_llm(proposals)
        if corrected:
            return corrected
        return proposals

    def _correct_with_llm(self, proposals: List[str]) -> List[str] | None:
        numbered = "\n".join(f"- {item}" for item in proposals)
        system_prompt = (
            "Tu es correcteur orthographique. "
            "Corrige uniquement l'orthographe, les accents et la ponctuation legere. "
            "Ne change jamais le sens, n'ajoute rien, ne supprime rien. "
            "Conserve strictement le meme ordre et le meme nombre d'elements. "
            "Reponds strictement par une liste JSON de chaines."
        )
        user_prompt = (
            "Corrige les propositions suivantes:\n"
            f"{numbered}\n"
            f"Tu dois renvoyer exactement {len(proposals)} elements JSON."
        )

        try:
            raw = self.chat.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        except Exception as exc:
            LOGGER.warning("Moderator spelling correction failed; keeping original proposals: %s", exc)
            return None

        parsed = _parse_json_list(_to_text(raw.content))
        if not parsed or len(parsed) != len(proposals):
            return None

        corrected: List[str] = []
        for original, candidate in zip(proposals, parsed):
            normalized_candidate = " ".join(str(candidate).strip().split())
            if not normalized_candidate:
                corrected.append(original)
                continue
            if not self._is_safe_spelling_correction(original, normalized_candidate):
                corrected.append(original)
                continue
            corrected.append(normalized_candidate[:180])

        return self._sanitize_proposals(corrected)

    def _select_with_llm(self, proposals: List[str], stage_name: str, objective: str) -> List[str] | None:
        numbered = "\n".join(f"- {item}" for item in proposals)
        normalized_lookup = {self._normalize_key(item): item for item in proposals}
        system_prompt = (
            "Tu es moderateur audience. Tu dois uniquement selectionner parmi les propositions candidates. "
            "Ne cree jamais de nouvelle proposition. Renvoie strictement une liste JSON de 3 elements."
        )
        user_prompt = (
            f"Stage courant: {stage_name}\n"
            f"Objectif courant: {objective}\n"
            f"Propositions candidates:\n{numbered}\n"
            "Retourne exactement 3 elements JSON choisis dans la liste ci-dessus, sans reformulation."
        )

        try:
            raw = self.chat.invoke([SystemMessage(content=system_prompt), HumanMessage(content=user_prompt)])
        except Exception as exc:
            LOGGER.warning("Moderator LLM call failed; fallback to first proposals: %s", exc)
            return None

        parsed = _parse_json_list(_to_text(raw.content))
        if not parsed:
            return None

        result: List[str] = []
        seen = set()

        for candidate in parsed:
            matched = normalized_lookup.get(self._normalize_key(candidate))
            if not matched:
                continue
            if matched in seen:
                continue
            seen.add(matched)
            result.append(matched)
            if len(result) == 3:
                break

        if len(result) < 3:
            for candidate in proposals:
                if candidate in seen:
                    continue
                seen.add(candidate)
                result.append(candidate)
                if len(result) == 3:
                    break

        if len(result) < 3:
            return None
        return result

    @staticmethod
    def _sanitize_proposals(proposals: List[str]) -> List[str]:
        banned_words = {"haine", "raciste", "menace", "violence", "suicide", "arme"}
        out: List[str] = []
        seen = set()

        for raw in proposals:
            text = str(raw).strip()
            if not text:
                continue
            lowered = text.lower()
            if any(word in lowered for word in banned_words):
                continue
            if text in seen:
                continue
            seen.add(text)
            out.append(text[:180])
        return out

    @staticmethod
    def _is_safe_spelling_correction(original: str, corrected: str) -> bool:
        normalized_original = " ".join(str(original).strip().lower().split())
        normalized_corrected = " ".join(str(corrected).strip().lower().split())
        if not normalized_original or not normalized_corrected:
            return False
        if normalized_original == normalized_corrected:
            return True

        similarity = SequenceMatcher(None, normalized_original, normalized_corrected).ratio()
        original_tokens = {token for token in normalized_original.split() if len(token) > 2}
        corrected_tokens = {token for token in normalized_corrected.split() if len(token) > 2}
        if not original_tokens:
            token_overlap = 1.0
        else:
            token_overlap = len(original_tokens & corrected_tokens) / len(original_tokens)

        return similarity >= 0.6 and token_overlap >= 0.5

    @staticmethod
    def _normalize_key(text: str) -> str:
        return " ".join(str(text).strip().lower().split())


class VictimAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.chat = _build_chat_model(settings, temperature=0.7)
        self.chat_with_tools = self.chat.bind_tools(list(SOUND_TOOL_REGISTRY.values())) if self.chat else None

    def respond(
        self,
        latest_scammer: str,
        history: List[Dict[str, object]],
        objective: str,
        audience_constraint: str,
        stage_name: str,
    ) -> VictimReply:
        if self.chat is not None and self.chat_with_tools is not None:
            reply = self._respond_with_llm(latest_scammer, history, objective, audience_constraint, stage_name)
            if reply is not None:
                return reply

        return self._respond_with_heuristic(latest_scammer, objective, audience_constraint)

    def _build_system_prompt(self, objective: str, audience_constraint: str, stage_name: str) -> str:
        return (
            "Role: Vous etes Jean Dubois, 78 ans, grognon mais lucide. "
            "Vous ne donnez jamais de mot de passe ni informations bancaires.\n"
            f"Current Context: Stage={stage_name}. Objectif={objective}\n"
            f"Audience Event: {audience_constraint or 'Aucun evenement audience en cours.'}\n"
            "Available Tools: Vous pouvez utiliser les outils audio si la situation s'y prete "
            "(dog_bark, doorbell, coughing_fit, tv_background).\n"
            "Style: phrases courtes, naturelles, parfois irritees, avec lenteur volontaire."
        )

    def _respond_with_llm(
        self,
        latest_scammer: str,
        history: List[Dict[str, object]],
        objective: str,
        audience_constraint: str,
        stage_name: str,
    ) -> VictimReply | None:
        prompt = self._build_system_prompt(objective, audience_constraint, stage_name)
        messages = [SystemMessage(content=prompt)]

        for msg in history[-12:]:
            role = str(msg.get("role", ""))
            content = str(msg.get("content", ""))
            if not content:
                continue
            if role == "scammer":
                messages.append(HumanMessage(content=content))
            elif role == "victim":
                messages.append(AIMessage(content=content))

        messages.append(HumanMessage(content=latest_scammer))

        try:
            first = self.chat_with_tools.invoke(messages)
        except Exception as exc:
            LOGGER.warning("Victim LLM call failed; fallback to heuristic: %s", exc)
            return None

        sound_effects: List[str] = []
        tool_messages: List[ToolMessage] = []

        tool_calls = getattr(first, "tool_calls", []) or []
        for idx, tool_call in enumerate(tool_calls):
            name = str(tool_call.get("name", "")).strip()
            args = tool_call.get("args", {}) or {}
            effect_result = run_tool_by_name(name, args)
            sound_effects.extend(extract_sound_effects(effect_result))
            call_id = str(tool_call.get("id", "")).strip() or f"tool_call_{idx + 1}"
            tool_messages.append(ToolMessage(content=effect_result, tool_call_id=call_id))

        if tool_messages:
            try:
                final = self.chat.invoke(messages + [first] + tool_messages)
            except Exception as exc:
                LOGGER.warning("Victim final LLM call failed after tool calls: %s", exc)
                return None
            text = _to_text(final.content)
            sound_effects.extend(extract_sound_effects(text))
            return VictimReply(text=text, sound_effects=_dedupe(sound_effects))

        text = _to_text(first.content)
        sound_effects.extend(extract_sound_effects(text))
        return VictimReply(text=text, sound_effects=_dedupe(sound_effects))

    def _respond_with_heuristic(
        self,
        latest_scammer: str,
        objective: str,
        audience_constraint: str,
    ) -> VictimReply:
        lower = latest_scammer.lower()
        chunks: List[str] = []

        if "mot de passe" in lower or "password" in lower or "carte" in lower:
            chunks.append("Je ne donne jamais mes informations privees par telephone.")
        elif "installer" in lower or "telecharger" in lower or "anydesk" in lower or "teamviewer" in lower:
            chunks.append("Attendez... je ne trouve pas le bouton Demarrer. Vous pouvez repeter lentement ?")
        elif "urgent" in lower or "vite" in lower or "maintenant" in lower:
            chunks.append("Vous allez trop vite. Je comprends rien si vous criez.")
            chunks.append(run_tool_by_name("coughing_fit"))
        else:
            chunks.append("D'accord... vous dites quoi exactement sur mon ordinateur ?")

        if audience_constraint:
            chunks.append(f"Attendez deux secondes, {audience_constraint.lower()}")
            if "sonne" in audience_constraint.lower() or "porte" in audience_constraint.lower():
                chunks.append(run_tool_by_name("doorbell"))
            if "chien" in audience_constraint.lower():
                chunks.append(run_tool_by_name("dog_bark"))
            if "tele" in audience_constraint.lower():
                chunks.append(run_tool_by_name("tv_background"))
        text = " ".join(chunks)
        return VictimReply(text=text, sound_effects=extract_sound_effects(text))
