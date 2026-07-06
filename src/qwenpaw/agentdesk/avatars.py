# -*- coding: utf-8 -*-
"""Deterministic human portrait avatars for AgentDesk agents (DiceBear Personas)."""

from __future__ import annotations

import hashlib
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..constant import WORKING_DIR

logger = logging.getLogger(__name__)

AVATARS_DIR = WORKING_DIR / "avatars"
DICEBEAR_BASE = "https://api.dicebear.com/9.x/personas/svg"
BACKGROUND_COLORS = ("b6e3f4", "c0aede", "d1d4f9", "ffd5dc", "ffdfbf", "d1f4e0")
_EMOJI_RE = re.compile(
    r"^[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    r"\U00002300-\U000023FF\U00002B50\U0001F004\U0001F0CF]+$"
)
_SAFE_FILENAME = re.compile(r"^[a-f0-9]{16}\.svg$")


def avatar_seed(name: str, description: str = "", role: str = "employee") -> str:
    """Stable 16-char seed from display name, description, and role."""
    raw = f"{role.strip().lower()}:{name.strip()}:{description.strip()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def is_avatar_image_url(avatar: str | None) -> bool:
    trimmed = str(avatar or "").strip()
    if not trimmed:
        return False
    return (
        trimmed.startswith("/api/avatars/")
        or trimmed.startswith("http://")
        or trimmed.startswith("https://")
        or trimmed.startswith("data:")
    )


def is_legacy_emoji_avatar(avatar: str | None) -> bool:
    """True when avatar is missing, emoji, or other non-image placeholder."""
    trimmed = str(avatar or "").strip()
    if not trimmed:
        return True
    if is_avatar_image_url(trimmed):
        return False
    if _EMOJI_RE.match(trimmed):
        return True
    return len(trimmed) <= 4


def _background_for_seed(seed: str) -> str:
    idx = int(seed[:8], 16) % len(BACKGROUND_COLORS)
    return ",".join(
        (
            BACKGROUND_COLORS[idx],
            BACKGROUND_COLORS[(idx + 2) % len(BACKGROUND_COLORS)],
        )
    )


def dicebear_source_url(seed: str) -> str:
    params = urllib.parse.urlencode(
        {
            "seed": seed,
            "backgroundColor": _background_for_seed(seed),
            "radius": "50",
        }
    )
    return f"{DICEBEAR_BASE}?{params}"


def portrait_public_url(seed: str) -> str:
    return f"/api/avatars/{seed}.svg"


def _avatars_dir() -> Path:
    path = AVATARS_DIR
    path.mkdir(parents=True, exist_ok=True)
    return path


def ensure_portrait_file(seed: str) -> Path:
    """Download and cache DiceBear SVG when missing; return local path."""
    filename = f"{seed}.svg"
    if not _SAFE_FILENAME.match(filename):
        raise ValueError(f"Invalid avatar seed: {seed!r}")
    dest = _avatars_dir() / filename
    if dest.exists() and dest.stat().st_size > 0:
        return dest

    source = dicebear_source_url(seed)
    try:
        with urllib.request.urlopen(source, timeout=15) as response:  # noqa: S310
            data = response.read()
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.warning("DiceBear fetch failed for %s: %s", seed, exc)
        raise

    if not data.strip():
        raise RuntimeError(f"DiceBear returned empty payload for seed {seed!r}")

    dest.write_bytes(data)
    return dest


def generate_portrait_url(
    name: str,
    description: str = "",
    *,
    role: str = "employee",
) -> str:
    """Return persistent `/api/avatars/<seed>.svg` URL and ensure file exists."""
    seed = avatar_seed(name, description, role)
    ensure_portrait_file(seed)
    return portrait_public_url(seed)


def portrait_url_for_record(
    record: dict[str, Any],
    *,
    role: str = "employee",
    name_key: str = "name",
    desc_key: str = "desc",
) -> str | None:
    """Return a portrait URL without downloading or persisting (for list reads)."""
    name = str(record.get(name_key) or "").strip()
    if not name:
        return None
    current = str(record.get("avatar") or "").strip()
    if not is_legacy_emoji_avatar(current):
        return None
    description = str(record.get(desc_key) or record.get("description") or "").strip()
    return portrait_public_url(avatar_seed(name, description, role))


def enrich_record_avatar_lazy(
    record: dict[str, Any],
    *,
    role: str = "employee",
    name_key: str = "name",
    desc_key: str = "desc",
) -> dict[str, Any]:
    """Attach portrait URL on list reads; file fetch happens on GET /api/avatars/."""
    url = portrait_url_for_record(
        record,
        role=role,
        name_key=name_key,
        desc_key=desc_key,
    )
    if url:
        return {**record, "avatar": url}
    return record


def ensure_record_avatar(
    record: dict[str, Any],
    *,
    role: str = "employee",
    name_key: str = "name",
    desc_key: str = "desc",
) -> tuple[dict[str, Any], bool]:
    """Fill avatar with a portrait URL when missing or still emoji."""
    name = str(record.get(name_key) or "").strip()
    if not name:
        return record, False

    current = str(record.get("avatar") or "").strip()
    if not is_legacy_emoji_avatar(current):
        return record, False

    description = str(record.get(desc_key) or record.get("description") or "").strip()
    try:
        url = generate_portrait_url(name, description, role=role)
    except Exception as exc:  # noqa: BLE001 - best-effort avatar generation
        logger.warning("Avatar generation failed for %r: %s", name, exc)
        return record, False

    return {**record, "avatar": url}, True
