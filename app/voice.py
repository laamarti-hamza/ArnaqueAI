from __future__ import annotations

import base64
import logging
import re
import wave
from io import BytesIO
from typing import Tuple

try:
    from google import genai
    from google.genai import types as genai_types
except Exception:
    genai = None
    genai_types = None

try:
    from google.oauth2 import service_account
except Exception:
    service_account = None

from .config import Settings

LOGGER = logging.getLogger(__name__)
GOOGLE_CLOUD_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
L16_RATE_RE = re.compile(r"rate\s*=\s*(\d+)", re.IGNORECASE)


class VoiceSynthesisError(RuntimeError):
    pass


def _decode_maybe_base64(raw: str) -> bytes:
    try:
        return base64.b64decode(raw, validate=True)
    except Exception:
        return raw.encode("utf-8")


def _extract_audio_bytes(response: object) -> Tuple[bytes, str]:
    candidates = getattr(response, "candidates", None) or []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        parts = getattr(content, "parts", None) or []
        for part in parts:
            inline_data = getattr(part, "inline_data", None)
            if inline_data is None:
                continue
            mime_type = str(getattr(inline_data, "mime_type", "") or "").strip() or "audio/wav"
            data = getattr(inline_data, "data", None)
            if isinstance(data, (bytes, bytearray)) and data:
                return bytes(data), mime_type
            if isinstance(data, str) and data.strip():
                decoded = _decode_maybe_base64(data.strip())
                if decoded:
                    return decoded, mime_type
    return b"", ""


def _pcm_l16_to_wav(audio_bytes: bytes, mime_type: str) -> Tuple[bytes, str]:
    if not audio_bytes:
        return audio_bytes, mime_type

    normalized = str(mime_type or "").lower()
    if "audio/l16" not in normalized:
        return audio_bytes, mime_type

    rate = 24000
    match = L16_RATE_RE.search(normalized)
    if match:
        try:
            parsed = int(match.group(1))
            if parsed > 0:
                rate = parsed
        except Exception:
            rate = 24000

    out = BytesIO()
    with wave.open(out, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(rate)
        wav_file.writeframes(audio_bytes)

    return out.getvalue(), "audio/wav"


class VictimVoiceSynthesizer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._client = None
        self._unavailable_reason = ""
        self._init_client()

    @property
    def enabled(self) -> bool:
        return self._client is not None

    @property
    def unavailable_reason(self) -> str:
        return self._unavailable_reason

    def status(self) -> dict:
        status = {
            "enabled": self.enabled,
            "model": self.settings.vertex_tts_model,
            "voice": self.settings.vertex_tts_voice,
            "language": self.settings.vertex_tts_language,
        }
        if not self.enabled:
            status["reason"] = self._unavailable_reason or "Synthese vocale indisponible."
        return status

    def _init_client(self) -> None:
        if not self.settings.victim_voice_enabled:
            self._unavailable_reason = "Synthese vocale desactivee (VICTIM_VOICE_ENABLED=false)."
            return

        if genai is None or genai_types is None:
            self._unavailable_reason = "SDK google-genai indisponible."
            return

        if service_account is None:
            self._unavailable_reason = "google-auth indisponible pour charger les credentials."
            return

        if not self.settings.google_application_credentials:
            self._unavailable_reason = "GOOGLE_APPLICATION_CREDENTIALS manquant."
            return

        if not self.settings.vertex_project_id:
            self._unavailable_reason = "VERTEX_PROJECT_ID manquant."
            return

        try:
            credentials = service_account.Credentials.from_service_account_file(
                self.settings.google_application_credentials,
                scopes=[GOOGLE_CLOUD_SCOPE],
            )
            self._client = genai.Client(
                vertexai=True,
                project=self.settings.vertex_project_id,
                location=self.settings.vertex_location,
                credentials=credentials,
            )
        except Exception as exc:
            self._client = None
            self._unavailable_reason = f"Initialisation voix impossible: {exc}"
            LOGGER.warning("Victim voice init failed: %s", exc)

    def synthesize(self, text: str) -> Tuple[bytes, str]:
        clean_text = str(text or "").strip()
        if not clean_text:
            raise ValueError("Le texte a lire est vide.")
        if len(clean_text) > 4000:
            raise ValueError("Le texte a lire est trop long (max 4000 caracteres).")

        if not self.enabled:
            raise VoiceSynthesisError(self._unavailable_reason or "Synthese vocale indisponible.")

        style_prompt = str(self.settings.vertex_tts_style_prompt or "").strip()

        try:
            return self._synthesize_once(clean_text, style_prompt=style_prompt)
        except Exception as exc:
            if style_prompt:
                LOGGER.warning("Victim voice styled synthesis failed, retrying without style: %s", exc)
                try:
                    return self._synthesize_once(clean_text, style_prompt="")
                except Exception as fallback_exc:
                    LOGGER.warning("Victim voice fallback synthesis failed: %s", fallback_exc)
                    raise VoiceSynthesisError(f"Echec de generation vocale: {fallback_exc}") from fallback_exc
            LOGGER.warning("Victim voice synthesis failed: %s", exc)
            raise VoiceSynthesisError(f"Echec de generation vocale: {exc}") from exc

    def _synthesize_once(self, text: str, style_prompt: str) -> Tuple[bytes, str]:
        config_kwargs = {
            "response_modalities": ["AUDIO"],
            "speech_config": genai_types.SpeechConfig(
                language_code=self.settings.vertex_tts_language,
                voice_config=genai_types.VoiceConfig(
                    prebuilt_voice_config=genai_types.PrebuiltVoiceConfig(
                        voice_name=self.settings.vertex_tts_voice
                    )
                ),
            ),
        }
        if style_prompt:
            config_kwargs["system_instruction"] = style_prompt

        config = genai_types.GenerateContentConfig(**config_kwargs)
        response = self._client.models.generate_content(
            model=self.settings.vertex_tts_model,
            contents=text,
            config=config,
        )

        audio_bytes, mime_type = _extract_audio_bytes(response)
        if not audio_bytes:
            raise VoiceSynthesisError("Le modele TTS n'a retourne aucun audio exploitable.")

        converted_bytes, converted_mime = _pcm_l16_to_wav(audio_bytes, mime_type or "audio/wav")
        return converted_bytes, converted_mime
