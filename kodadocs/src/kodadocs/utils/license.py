"""License and Pro Kit detection for KodaDocs."""

import os
import re
from pathlib import Path
from typing import Optional

# Full format pattern for Pydantic field-level validation (deploy only).
LICENSE_KEY_PATTERN = r"^kd_pro_[A-Za-z0-9_-]{20,}$"

_PREFIX_RE = re.compile(r"^kd_pro_")

# ---------------------------------------------------------------------------
# Local Pro Kit detection
# ---------------------------------------------------------------------------

_SKILL_MARKERS = [
    "kodadocs-visual-guides",
    "kodadocs-brand-voice",
    "kodadocs-user-journeys",
]


def _find_skills_dir() -> Path | None:
    """Find the Claude Code skills directory."""
    home_skills = Path.home() / ".claude" / "skills"
    if home_skills.is_dir():
        return home_skills
    return None


def has_local_pro_kit() -> bool:
    """Return True if Pro Kit skill files are installed locally.

    Checks for at least 2 KodaDocs Pro skill directories in ~/.claude/skills/.
    """
    skills_dir = _find_skills_dir()
    if not skills_dir:
        return False
    found = 0
    for marker in _SKILL_MARKERS:
        skill_path = skills_dir / marker
        if skill_path.is_dir() and (skill_path / "SKILL.md").exists():
            found += 1
        if found >= 2:
            return True
    return False


def is_pro() -> bool:
    """Return True if the Pro Kit is installed locally.

    This is the primary gate for all Pro features (unlimited pages, themes,
    auth capture, targeted screenshots, GIF recording, custom branding).
    """
    return has_local_pro_kit()


def is_valid_license_key(key: Optional[str]) -> bool:
    """Return True if *key* matches the license key format.

    Used ONLY for kodadocs.com hosted deploy validation.
    Does not affect Pro Kit feature gates.
    """
    return bool(key and _PREFIX_RE.match(key))
