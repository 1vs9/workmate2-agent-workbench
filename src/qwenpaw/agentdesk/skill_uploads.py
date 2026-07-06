# -*- coding: utf-8 -*-
"""AgentDesk skill upload archive helpers."""

from __future__ import annotations

import json
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Protocol

from fastapi import HTTPException


class SkillUpload(Protocol):
    filename: str | None

    async def read(self) -> bytes: ...


def parse_relative_paths(raw: str) -> list[str]:
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        parsed = []
    if isinstance(parsed, list):
        return [str(item) for item in parsed]
    return []


def safe_upload_rel_path(raw_path: str) -> Path:
    rel = Path(str(raw_path or "SKILL.md"))
    if rel.is_absolute() or rel.drive or rel.root or ".." in rel.parts:
        raise HTTPException(status_code=400, detail="Invalid upload path")
    safe_parts = [part for part in rel.parts if part not in {"", ".", ".."}]
    return Path(*safe_parts) if safe_parts else Path("SKILL.md")


async def uploads_to_zip_bytes(
    uploads: list[SkillUpload],
    relative_paths: list[str],
) -> bytes:
    with tempfile.TemporaryDirectory(prefix="agentdesk_skill_upload_") as tmp:
        root = Path(tmp)
        for idx, upload in enumerate(uploads):
            raw_name = str(upload.filename or "SKILL.md")
            rel = safe_upload_rel_path(
                relative_paths[idx] if idx < len(relative_paths) else raw_name,
            )
            dest = (root / rel).resolve()
            try:
                dest.relative_to(root.resolve())
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="Invalid upload path") from exc
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(await upload.read())

        buf = BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    zf.write(path, path.relative_to(root).as_posix())
        return buf.getvalue()
