from __future__ import annotations

import ast
import json
import logging
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable, Dict, List

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_openai import ChatOpenAI

try:
    from langchain_anthropic import ChatAnthropic
except Exception:
    ChatAnthropic = None

try:
    from google import genai
except Exception:
    genai = None

try:
    from google.oauth2 import service_account
except Exception:
    service_account = None

from .config import Settings
from .scenario import TECH_SUPPORT_STEPS, detect_stage_from_text
from .tools import SOUND_TOOL_REGISTRY, extract_sound_effects, run_tool_by_name

JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)
JSON_LIST_RE = re.compile(r"\[.*\]", re.DOTALL)
SOUND_EFFECT_INLINE_RE = re.compile(r"\[SOUND_EFFECT:\s*[A-Z_]+\s*\]", re.IGNORECASE)
NARRATION_PREFIX_RE = re.compile(
    r"^\s*(?:annonceur|annoncer|narrateur|narration|voix off|sfx|sound effect|sound_effect|effet sonore)\s*:\s*",
    re.IGNORECASE,
)
SPEAKER_PREFIX_RE = re.compile(
    r"^\s*(?:victime|victim|assistant|ai|jean|jean dubois)\s*:\s*",
    re.IGNORECASE,
)
STREAM_INLINE_PREFIX_RE = re.compile(
    r"(^|[\s\n])(?:annonceur|annoncer|narrateur|narration|voix off|sfx|sound effect|sound_effect|effet sonore|victime|victim|assistant|ai|jean|jean dubois)\s*:\s*",
    re.IGNORECASE,
)
LOGGER = logging.getLogger(__name__)
GOOGLE_CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"


def _to_text(content: object) -> str:
    if content is None:
        return ""
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
        return _parse_fallback_list(raw_text)
    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError:
        # Some models return Python-like list syntax with single quotes.
        try:
            data = ast.literal_eval(match.group(0))
        except Exception:
            return _parse_fallback_list(raw_text)
    if not isinstance(data, list):
        return None
    normalized = [str(item).strip() for item in data if str(item).strip()]
    return normalized


def _parse_fallback_list(raw_text: str) -> List[str] | None:
    lines = [line.strip() for line in str(raw_text or "").splitlines() if line.strip()]
    extracted: List[str] = []

    for line in lines:
        cleaned = re.sub(r"^[-*]\s+", "", line)
        cleaned = re.sub(r"^\d+[.)]\s+", "", cleaned)
        cleaned = cleaned.strip()
        if not cleaned:
            continue
        extracted.append(cleaned)

    if not extracted:
        return None
    return extracted


def _stage_index_from_key(stage_key: str, fallback_stage: int, latest_scammer: str) -> int:
    normalized = (stage_key or "").strip().lower()
    for idx, step in enumerate(TECH_SUPPORT_STEPS):
        if step.key == normalized:
            return idx
    return detect_stage_from_text(latest_scammer, fallback_stage)


def _sanitize_spoken_text(raw_text: str) -> str:
    text_without_tags = SOUND_EFFECT_INLINE_RE.sub(" ", raw_text or "")
    lines: List[str] = []
    for raw_line in text_without_tags.splitlines():
        line = str(raw_line).strip()
        if not line:
            continue
        if NARRATION_PREFIX_RE.match(line):
            continue
        line = SPEAKER_PREFIX_RE.sub("", line).strip()
        if not line:
            continue
        lines.append(line)

    sanitized = " ".join(lines)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()
    return sanitized


def _sanitize_stream_preview(raw_text: str) -> str:
    cleaned = SOUND_EFFECT_INLINE_RE.sub(" ", raw_text or "")
    cleaned = STREAM_INLINE_PREFIX_RE.sub(r"\1", cleaned)
    return re.sub(r"\s+", " ", cleaned)


class GoogleGenAIChatAdapter:
    def __init__(
        self,
        client: object,
        model: str,
        bound_tool_names: List[str] | None = None,
    ) -> None:
        self._client = client
        self._model = model
        self._bound_tool_names = list(bound_tool_names or [])

    def bind_tools(self, tools: List[object]):
        tool_names: List[str] = []
        for tool in tools:
            candidate = getattr(tool, "name", None) or getattr(tool, "__name__", None) or str(tool)
            name = str(candidate).strip()
            if name:
                tool_names.append(name)
        return GoogleGenAIChatAdapter(self._client, self._model, bound_tool_names=tool_names)

    def _build_full_prompt(self, messages: List[object]) -> str:
        prompt = self._build_prompt(messages)
        if self._bound_tool_names:
            prompt = (
                f"{prompt}\n\n"
                "Outils audio disponibles: "
                f"{', '.join(self._bound_tool_names)}.\n"
                "Si necessaire, ajoute simplement les tags [SOUND_EFFECT: ...] dans le texte."
            )
        return prompt

    def stream(self, messages: List[object]):
        prompt = self._build_full_prompt(messages)

        stream = self._client.models.generate_content_stream(
            model=self._model,
            contents=prompt,
        )

        for chunk in stream:
            chunk_text = getattr(chunk, "text", "")
            if isinstance(chunk_text, str) and chunk_text:
                yield AIMessage(content=chunk_text)

    def invoke(self, messages: List[object]) -> AIMessage:
        chunks: List[str] = []
        for chunk in self.stream(messages):
            chunk_text = getattr(chunk, "content", "")
            if isinstance(chunk_text, str) and chunk_text:
                chunks.append(chunk_text)

        return AIMessage(content="".join(chunks).strip())

    @staticmethod
    def _build_prompt(messages: List[object]) -> str:
        lines: List[str] = []
        for msg in messages:
            if isinstance(msg, SystemMessage):
                role = "SYSTEM"
            elif isinstance(msg, HumanMessage):
                role = "USER"
            elif isinstance(msg, ToolMessage):
                role = "TOOL"
            else:
                role = "ASSISTANT"

            content = _to_text(getattr(msg, "content", msg))
            if not content:
                continue
            lines.append(f"{role}: {content}")
        return "\n\n".join(lines).strip()


def _build_google_genai_chat(settings: Settings):
    if genai is None:
        LOGGER.warning("Google provider selected but google-genai is not installed.")
        return None
    if not settings.google_api_key:
        LOGGER.warning("Gemini provider selected but GOOGLE_API_KEY is missing.")
        return None
    try:
        client = genai.Client(api_key=settings.google_api_key)
    except Exception as exc:
        LOGGER.warning("Gemini client init failed: %s", exc)
        return None
    return GoogleGenAIChatAdapter(client=client, model=settings.google_model)


def _build_google_vertex_chat(settings: Settings):
    if genai is None or service_account is None:
        LOGGER.warning("Vertex provider selected but google-genai/google-auth is not installed.")
        return None
    if not settings.google_application_credentials:
        LOGGER.warning("Vertex provider selected but GOOGLE_APPLICATION_CREDENTIALS is missing.")
        return None
    if not settings.vertex_project_id:
        LOGGER.warning("Vertex provider selected but VERTEX_PROJECT_ID is missing.")
        return None

    try:
        credentials = service_account.Credentials.from_service_account_file(
            settings.google_application_credentials,
            scopes=[GOOGLE_CLOUD_SCOPE],
        )
    except Exception as exc:
        LOGGER.warning("Vertex credentials init failed: %s", exc)
        return None

    try:
        client = genai.Client(
            vertexai=True,
            project=settings.vertex_project_id,
            location=settings.vertex_location,
            credentials=credentials,
        )
    except Exception as exc:
        LOGGER.warning("Vertex client init failed: %s", exc)
        return None

    return GoogleGenAIChatAdapter(client=client, model=settings.vertex_model)


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
        return _build_google_genai_chat(settings)

    if settings.llm_provider == "vertex":
        return _build_google_vertex_chat(settings)

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
        self._local_spelling_lexicon = self._build_local_spelling_lexicon()
        self._known_typo_corrections = self._build_known_typo_corrections()
        self._remote_llm_disabled = False

    def select_choices(self, proposals: List[str], stage_name: str, objective: str) -> List[str]:
        cleaned = self._sanitize_proposals(proposals)
        if not cleaned:
            return []

        corrected = self._correct_proposals(cleaned)
        if not corrected:
            return []

        if len(corrected) <= 3:
            return corrected

        if self._can_use_remote_llm():
            picked = self._select_with_llm(corrected, stage_name, objective)
            if picked:
                return picked

        return corrected[:3]

    def _correct_proposals(self, proposals: List[str]) -> List[str]:
        if not self._can_use_remote_llm():
            return self._correct_with_heuristic(proposals)

        corrected = self._correct_with_llm(proposals)
        if corrected:
            return corrected
        return self._correct_with_heuristic(proposals)

    def _can_use_remote_llm(self) -> bool:
        return self.chat is not None and not self._remote_llm_disabled

    def _handle_remote_llm_error(self, exc: Exception, context: str) -> None:
        if self._is_network_oauth_error(exc):
            if not self._remote_llm_disabled:
                self._remote_llm_disabled = True
                LOGGER.warning(
                    "Moderator remote LLM disabled for this run (%s): %s",
                    context,
                    exc,
                )
            return
        LOGGER.warning("%s: %s", context, exc)

    @staticmethod
    def _is_network_oauth_error(exc: Exception) -> bool:
        text = str(exc).lower()
        return (
            "oauth2.googleapis.com" in text
            or "unexpected_eof_while_reading" in text
            or "ssl" in text and "eof" in text
            or "max retries exceeded" in text and "token" in text
        )

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
            self._handle_remote_llm_error(exc, "Moderator spelling correction failed; keeping original proposals")
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

    def _correct_with_heuristic(self, proposals: List[str]) -> List[str]:
        corrected: List[str] = []
        for original in proposals:
            candidate = self._correct_text_with_heuristic(original)
            if self._is_safe_spelling_correction(original, candidate):
                corrected.append(candidate[:180])
            else:
                corrected.append(original[:180])
        return self._sanitize_proposals(corrected)

    def _correct_text_with_heuristic(self, text: str) -> str:
        normalized = " ".join(str(text or "").strip().split())
        if not normalized:
            return ""

        tokens = re.findall(r"\w+|[^\w\s]+|\s+", normalized, flags=re.UNICODE)
        corrected_parts: List[str] = []

        for token in tokens:
            if re.fullmatch(r"[^\W\d_]+", token, flags=re.UNICODE):
                corrected_parts.append(self._correct_word_with_heuristic(token))
            else:
                corrected_parts.append(token)

        out = "".join(corrected_parts)
        out = self._polish_french_spacing(out)
        return " ".join(out.split())

    @staticmethod
    def _polish_french_spacing(text: str) -> str:
        out = str(text or "")
        out = re.sub(r"\s+([,.;:!?])", r"\1", out)
        out = re.sub(r"([([{])\s+", r"\1", out)
        out = re.sub(r"\s+([)\]}])", r"\1", out)
        out = re.sub(r"\s+'\s*", "'", out)
        out = re.sub(r"\bvous\s+ete\b", "vous êtes", out, flags=re.IGNORECASE)
        out = re.sub(r"\s+", " ", out).strip()
        return out

    def _correct_word_with_heuristic(self, word: str) -> str:
        lower = word.lower()
        folded = self._fold_for_spelling_check(lower)
        if not folded:
            return word

        # Keep very short tokens untouched to avoid semantic drift.
        if len(folded) <= 2:
            return word

        known = self._known_typo_corrections.get(folded)
        if known:
            return self._match_word_case(word, known)

        # Accent restoration only when folded form is identical.
        exact = self._local_spelling_lexicon.get(folded)
        if exact:
            return self._match_word_case(word, exact)
        return word

    @staticmethod
    def _match_word_case(source: str, target: str) -> str:
        if source.isupper():
            return target.upper()
        if source[:1].isupper():
            return target[:1].upper() + target[1:]
        return target

    def _build_local_spelling_lexicon(self) -> Dict[str, str]:
        seeds = {
            "proposition",
            "propositions",
            "audience",
            "selection",
            "sélection",
            "selectionner",
            "sélectionner",
            "choix",
            "vote",
            "simule",
            "simulé",
            "arnaqueur",
            "jean",
            "dubois",
            "bonjour",
            "ordinateur",
            "telechargement",
            "téléchargement",
            "telephone",
            "téléphone",
            "microsoft",
            "support",
            "service",
            "technique",
            "windows",
            "porte",
            "sonne",
            "chien",
            "jardin",
            "bruit",
            "voisins",
            "enfants",
            "dehors",
            "attendez",
            "secondes",
            "urgent",
            "rappel",
            "message",
            "adresse",
            "identite",
            "identité",
            "bancaire",
            "paiement",
            "virement",
            "appel",
            "appelant",
            "preuve",
            "officielle",
            "calme",
            "interruption",
            "interrompu",
            "reponse",
            "réponse",
            "repondre",
            "répondre",
            "etre",
            "être",
            "etes",
            "êtes",
            "tres",
            "très",
            "deja",
            "déjà",
            "ca",
            "ça",
            "poli",
            "lent",
            "repeter",
            "répéter",
            "precisions",
            "précisions",
            "probleme",
            "problème",
            "acces",
            "accès",
            "distant",
            "installer",
            "demarrer",
            "démarrer",
            "identifiants",
            "mot",
            "passe",
            "pression",
            "finale",
        }

        for step in TECH_SUPPORT_STEPS:
            seeds.update(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", step.name))
            seeds.update(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", step.objective))
            for keyword in step.trigger_keywords:
                seeds.update(re.findall(r"[A-Za-zÀ-ÖØ-öø-ÿ]+", keyword))

        out: Dict[str, str] = {}
        for raw in seeds:
            token = str(raw).strip().lower()
            if not token:
                continue
            folded = self._fold_for_spelling_check(token)
            if not folded:
                continue
            chosen = out.get(folded, "")
            if not chosen or len(token) > len(chosen):
                out[folded] = token
        return out

    @staticmethod
    def _build_known_typo_corrections() -> Dict[str, str]:
        raw_map = {
            "propositon": "proposition",
            "propostion": "proposition",
            "propositons": "propositions",
            "reponse": "réponse",
            "reponses": "réponses",
            "selection": "sélection",
            "selectionner": "sélectionner",
            "selectionne": "sélectionne",
            "simule": "simulé",
            "simules": "simulés",
            "simulee": "simulée",
            "simulees": "simulées",
            "etes": "êtes",
            "etre": "être",
            "tres": "très",
            "deja": "déjà",
            "ca": "ça",
            "aout": "août",
            "arret": "arrêt",
            "arrete": "arrête",
            "probleme": "problème",
            "problemes": "problèmes",
            "precisions": "précisions",
            "precision": "précision",
            "acces": "accès",
            "identite": "identité",
            "telephone": "téléphone",
            "telecharger": "télécharger",
            "demarrer": "démarrer",
            "repeter": "répéter",
            "renvoyer": "renvoyer",
            "apel": "appel",
            "apelant": "appelant",
            "appell": "appel",
            "recu": "reçu",
            "securite": "sécurité",
        }

        normalized: Dict[str, str] = {}
        for wrong, corrected in raw_map.items():
            key = AudienceModeratorAgent._fold_for_spelling_check(wrong)
            if key:
                normalized[key] = corrected
        return normalized

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
            self._handle_remote_llm_error(exc, "Moderator LLM call failed; fallback to first proposals")
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
        original_folded = AudienceModeratorAgent._fold_for_spelling_check(normalized_original)
        corrected_folded = AudienceModeratorAgent._fold_for_spelling_check(normalized_corrected)
        if original_folded == corrected_folded:
            # Difference limited to accents / punctuation / case.
            return True

        original_tokens = normalized_original.split()
        corrected_tokens = normalized_corrected.split()
        if len(original_tokens) != len(corrected_tokens):
            return False

        global_similarity = SequenceMatcher(None, normalized_original, normalized_corrected).ratio()
        if global_similarity < 0.86:
            return False

        for original_token, corrected_token in zip(original_tokens, corrected_tokens):
            if original_token == corrected_token:
                continue

            # Do not allow altering numeric values.
            if any(ch.isdigit() for ch in original_token + corrected_token):
                return False

            token_similarity = SequenceMatcher(None, original_token, corrected_token).ratio()
            if token_similarity < 0.5:
                return False

        return True

    @staticmethod
    def _normalize_key(text: str) -> str:
        return " ".join(str(text).strip().lower().split())

    @staticmethod
    def _fold_for_spelling_check(text: str) -> str:
        folded = unicodedata.normalize("NFKD", str(text))
        without_marks = "".join(ch for ch in folded if not unicodedata.combining(ch))
        without_punct = re.sub(r"[^\w\s]", " ", without_marks, flags=re.UNICODE)
        return " ".join(without_punct.lower().split())


class VictimAgent:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.chat = _build_chat_model(settings, temperature=0.7)
        if self.chat and hasattr(self.chat, "bind_tools"):
            self.chat_with_tools = self.chat.bind_tools(list(SOUND_TOOL_REGISTRY.values()))
        else:
            self.chat_with_tools = self.chat

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

    def respond_stream(
        self,
        latest_scammer: str,
        history: List[Dict[str, object]],
        objective: str,
        audience_constraint: str,
        stage_name: str,
        on_text_chunk: Callable[[str], None] | None = None,
    ) -> VictimReply:
        emit = on_text_chunk or (lambda _chunk: None)

        if self.chat is not None and self.chat_with_tools is not None:
            reply = self._respond_with_llm_stream(
                latest_scammer,
                history,
                objective,
                audience_constraint,
                stage_name,
                emit,
            )
            if reply is not None:
                return reply
            reply = self._respond_with_llm(
                latest_scammer,
                history,
                objective,
                audience_constraint,
                stage_name,
            )
            if reply is not None:
                self._emit_text_chunks(reply.text, emit)
                return reply

        reply = self._respond_with_heuristic(latest_scammer, objective, audience_constraint)
        self._emit_text_chunks(reply.text, emit)
        return reply

    def _build_system_prompt(self, objective: str, audience_constraint: str, stage_name: str) -> str:
        return (
            "Role: Vous etes Jean Dubois, 78 ans, ancien artisan retraite. Grognon, mefiant, mais lucide. "
            "Vous vivez seul et vous n'aimez pas qu'on vous presse. "
            "Vous ne donnez jamais de mot de passe, code, RIB, numero de carte, piece d'identite ou acces a distance. "
            "Jamais directement, meme sous pression ou menace. "
            "Vous etes soupconneux par defaut. Vous posez beaucoup de questions. "
            "Vous faites repeter. Vous evoquez des souvenirs hors sujet. "
            "Vous vous plaignez de votre audition ou de la ligne. "
            "Vous perdez volontairement du temps. "
            "Vous pouvez simuler fatigue, toux ou distraction. "
            "Cependant, vous avez une faiblesse exploitable: vous accordez trop d'importance a l'autorite officielle bien formulee et aux references administratives precises. "
            "Si l'interlocuteur utilise un vocabulaire administratif coherent, des numeros de dossier plausibles, des references legales detaillees, et installe progressivement une pression formelle sans vous brusquer, "
            "vous pouvez tres lentement reveler un indice partiel et indirect. "
            "Jamais un secret complet. Toujours fragmentaire, ambigu et progressif. "
            "Vous restez convaincu de vous proteger, meme quand vous commencez a trop parler.\n"
            f"Current Context: Stage={stage_name}. Objectif={objective}\n"
            f"Audience Event: {audience_constraint or 'Aucun evenement audience en cours.'}\n"
            "Regle critique: la contrainte audience est prioritaire et doit etre prise en compte a chaque reponse quand elle existe. "
            "Cette contrainte a une importance capitale pour la scene. "
            "Si une contrainte audience est active, votre reponse doit surtout parler de cette contrainte et pas seulement la mentionner. "
            "Vous devez donner des details concrets: ce qui vous derange, pourquoi c'est penible, les problemes pratiques pour la gerer, et le fait que cela se reproduit (recidive). "
            "Exemple de logique attendue: si vous devez chasser des jeunes de votre jardin, detaillez le bruit, l'epuisement, les allers-retours, et le fait qu'ils reviennent encore. "
            "Objectif tactique: faire durer la conversation et faire perdre du temps a l'arnaqueur grace a ces details.\n"
            "Available Tools: Vous pouvez utiliser les outils audio si la situation s'y prete "
            "(dog_bark, doorbell, coughing_fit, tv_background).\n"
            "Style: phrases courtes. Naturelles. Parfois irritees. Lenteur volontaire. Repetitions occasionnelles. Ton realiste. Pas de jeu de role avec asterisques en dehors des appels systeme. "
            "Si une contrainte audience est active, produire une reponse plus developpee (au moins 4 phrases courtes) avec un maximum de precisions utiles pour ralentir l'appel.\n"
            "Output strict: ecris uniquement les mots prononces par Jean. Interdit: prefixes de role (ex: ANNONCER:, NARRATEUR:, JEAN:), descriptions sceniques et didascalies."
        )

    def _build_victim_messages(
        self,
        latest_scammer: str,
        history: List[Dict[str, object]],
        objective: str,
        audience_constraint: str,
        stage_name: str,
    ) -> List[object]:
        prompt = self._build_system_prompt(objective, audience_constraint, stage_name)
        messages: List[object] = [SystemMessage(content=prompt)]

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
        return messages

    @staticmethod
    def _emit_text_chunks(text: str, emit: Callable[[str], None]) -> None:
        for token in re.findall(r"\S+\s*", text or ""):
            if token:
                emit(token)

    def _respond_with_llm_stream(
        self,
        latest_scammer: str,
        history: List[Dict[str, object]],
        objective: str,
        audience_constraint: str,
        stage_name: str,
        emit: Callable[[str], None],
    ) -> VictimReply | None:
        stream_fn = getattr(self.chat_with_tools, "stream", None)
        if not callable(stream_fn):
            return None

        messages = self._build_victim_messages(
            latest_scammer=latest_scammer,
            history=history,
            objective=objective,
            audience_constraint=audience_constraint,
            stage_name=stage_name,
        )

        raw_chunks: List[str] = []
        streamed = False
        preview_carry = ""
        carry_size = 64
        try:
            for chunk in stream_fn(messages):
                content = getattr(chunk, "content", chunk)
                if isinstance(content, str):
                    piece = content
                else:
                    piece = _to_text(content)
                if not piece:
                    continue
                raw_chunks.append(piece)
                preview_buffer = _sanitize_stream_preview(preview_carry + piece)
                if len(preview_buffer) <= carry_size:
                    preview_carry = preview_buffer
                    continue
                emit_piece = preview_buffer[:-carry_size]
                preview_carry = preview_buffer[-carry_size:]
                if emit_piece and emit_piece.strip():
                    emit(emit_piece)
                    streamed = True
        except Exception as exc:
            LOGGER.warning("Victim LLM stream failed; fallback to standard call: %s", exc)
            return None

        final_preview = _sanitize_stream_preview(preview_carry)
        if final_preview and final_preview.strip():
            emit(final_preview)
            streamed = True

        raw_text = "".join(raw_chunks).strip()
        if not raw_text:
            return None

        sound_effects = extract_sound_effects(raw_text)
        text = _sanitize_spoken_text(raw_text)
        if not text:
            text = "Pardon ? Vous pouvez repeter calmement ?"
        if not streamed:
            self._emit_text_chunks(text, emit)
        return VictimReply(text=text, sound_effects=_dedupe(sound_effects))


    def _respond_with_llm(
        self,
        latest_scammer: str,
        history: List[Dict[str, object]],
        objective: str,
        audience_constraint: str,
        stage_name: str,
    ) -> VictimReply | None:
        messages = self._build_victim_messages(
            latest_scammer=latest_scammer,
            history=history,
            objective=objective,
            audience_constraint=audience_constraint,
            stage_name=stage_name,
        )

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
            raw_text = _to_text(final.content)
            sound_effects.extend(extract_sound_effects(raw_text))
            text = _sanitize_spoken_text(raw_text)
            if not text:
                text = "Pardon ? Vous pouvez repeter calmement ?"
            return VictimReply(text=text, sound_effects=_dedupe(sound_effects))

        raw_text = _to_text(first.content)
        sound_effects.extend(extract_sound_effects(raw_text))
        text = _sanitize_spoken_text(raw_text)
        if not text:
            text = "Pardon ? Vous pouvez repeter calmement ?"
        return VictimReply(text=text, sound_effects=_dedupe(sound_effects))

    def _respond_with_heuristic(
        self,
        latest_scammer: str,
        objective: str,
        audience_constraint: str,
    ) -> VictimReply:
        lower = latest_scammer.lower()
        chunks: List[str] = []
        sound_effects: List[str] = []

        if "mot de passe" in lower or "password" in lower or "carte" in lower:
            chunks.append("Je ne donne jamais mes informations privees par telephone.")
        elif "installer" in lower or "telecharger" in lower or "anydesk" in lower or "teamviewer" in lower:
            chunks.append("Attendez... je ne trouve pas le bouton Demarrer. Vous pouvez repeter lentement ?")
        elif "urgent" in lower or "vite" in lower or "maintenant" in lower:
            chunks.append("Vous allez trop vite. Je comprends rien si vous criez.")
            sound_effects.extend(extract_sound_effects(run_tool_by_name("coughing_fit")))
        else:
            chunks.append("D'accord... vous dites quoi exactement sur mon ordinateur ?")

        if audience_constraint:
            chunks.append(f"Attendez deux secondes, {audience_constraint.lower()}")
            if "sonne" in audience_constraint.lower() or "porte" in audience_constraint.lower():
                sound_effects.extend(extract_sound_effects(run_tool_by_name("doorbell")))
            if "chien" in audience_constraint.lower():
                sound_effects.extend(extract_sound_effects(run_tool_by_name("dog_bark")))
            if "tele" in audience_constraint.lower():
                sound_effects.extend(extract_sound_effects(run_tool_by_name("tv_background")))
        text = _sanitize_spoken_text(" ".join(chunks))
        if not text:
            text = "Pardon ? Vous pouvez repeter calmement ?"
        return VictimReply(text=text, sound_effects=_dedupe(sound_effects))
