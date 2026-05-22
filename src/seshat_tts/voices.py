from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .config import APP_DIR


VOICE_PROFILES_PATH = APP_DIR / "voice_profiles.json"


@dataclass(slots=True)
class VoiceProfile:
    name: str
    path: str


def safe_voice_slug(name: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", name.strip()).strip("-._")
    return slug or "custom-voice"


def load_voice_profiles(path: Path = VOICE_PROFILES_PATH) -> list[VoiceProfile]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    profiles: list[VoiceProfile] = []
    for item in data if isinstance(data, list) else []:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", "")).strip()
        voice_path = str(item.get("path", "")).strip()
        if name and voice_path:
            profiles.append(VoiceProfile(name=name, path=voice_path))
    return profiles


def save_voice_profiles(profiles: list[VoiceProfile], path: Path = VOICE_PROFILES_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([asdict(profile) for profile in profiles], indent=2), encoding="utf-8")


def upsert_voice_profile(profile: VoiceProfile, path: Path = VOICE_PROFILES_PATH) -> list[VoiceProfile]:
    profiles = [item for item in load_voice_profiles(path) if item.name != profile.name]
    profiles.append(profile)
    profiles.sort(key=lambda item: item.name.casefold())
    save_voice_profiles(profiles, path)
    return profiles


def voice_profile_by_name(name: str, profiles: list[VoiceProfile]) -> VoiceProfile | None:
    return next((profile for profile in profiles if profile.name == name), None)
