# -*- coding: utf-8 -*-
from __future__ import annotations

import io
import zipfile

import pytest
from fastapi import HTTPException

from qwenpaw.agentdesk import skill_uploads


class _Upload:
    def __init__(self, filename: str, content: bytes) -> None:
        self.filename = filename
        self._content = content

    async def read(self) -> bytes:
        return self._content


def test_parse_relative_paths_ignores_invalid_json() -> None:
    assert skill_uploads.parse_relative_paths("not-json") == []
    assert skill_uploads.parse_relative_paths('["SKILL.md", 123]') == [
        "SKILL.md",
        "123",
    ]


@pytest.mark.parametrize("unsafe_path", ["../x.md", "/x.md", "C:x.md"])
def test_safe_upload_rel_path_rejects_escape(unsafe_path: str) -> None:
    with pytest.raises(HTTPException) as exc:
        skill_uploads.safe_upload_rel_path(unsafe_path)

    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_uploads_to_zip_bytes_uses_relative_paths() -> None:
    payload = await skill_uploads.uploads_to_zip_bytes(
        [
            _Upload("ignored.md", b"# Demo"),
            _Upload("tool.py", b"print('ok')"),
        ],
        ["SKILL.md", "src/tool.py"],
    )

    with zipfile.ZipFile(io.BytesIO(payload)) as zf:
        assert sorted(zf.namelist()) == ["SKILL.md", "src/tool.py"]
        assert zf.read("SKILL.md") == b"# Demo"
        assert zf.read("src/tool.py") == b"print('ok')"
