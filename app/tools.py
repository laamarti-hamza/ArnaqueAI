from __future__ import annotations

import re
from typing import Dict, List

from langchain_core.tools import tool

SOUND_TAG_PATTERN = re.compile(r"\[SOUND_EFFECT:\s*([A-Z_]+)\s*\]")


@tool
def dog_bark() -> str:
    """Joue un bruitage d'aboiement de chien."""
    return "[SOUND_EFFECT: DOG_BARKING]"


@tool
def doorbell() -> str:
    """Joue un bruitage de sonnette de porte."""
    return "[SOUND_EFFECT: DOORBELL]"


@tool
def coughing_fit() -> str:
    """Simule une quinte de toux de dix secondes."""
    return "[SOUND_EFFECT: COUGHING_FIT]"


@tool
def tv_background() -> str:
    """Augmente le volume de la television en bruit de fond."""
    return "[SOUND_EFFECT: TV_BACKGROUND_BFMTV]"


SOUND_TOOL_REGISTRY: Dict[str, object] = {
    "dog_bark": dog_bark,
    "doorbell": doorbell,
    "coughing_fit": coughing_fit,
    "tv_background": tv_background,
}


def run_tool_by_name(tool_name: str, args: dict | None = None) -> str:
    tool_obj = SOUND_TOOL_REGISTRY.get(tool_name)
    if tool_obj is None:
        return "[SOUND_EFFECT: UNKNOWN]"

    payload = args or {}
    try:
        result = tool_obj.invoke(payload)
    except Exception:
        result = tool_obj.invoke({})
    return str(result)


def extract_sound_effects(text: str) -> List[str]:
    if not text:
        return []
    return SOUND_TAG_PATTERN.findall(text)
