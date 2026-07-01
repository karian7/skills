#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""IMAP 폴더명 해석/인코딩 순수함수 — fetch_inbox/read_mail/compose_draft/move_to_trash 공유.

IMAP I/O는 없다(연결·로그인은 호출부의 책임). 여기 있는 함수는 전부 결정론적이라
TDD 대상이다. 서버는 보낸함을 "Sent"(\\Sent), 임시보관함을 "Drafts"(\\Drafts),
휴지통을 "Trash"(\\Trash)로 노출하지만, 사용자는 "보낸메일함"처럼 한글로 부른다.
그래서 별칭을 special-use 플래그로 해석해 서버가 영문이든 한글이든 견고하게 동작한다.

폴더명은 ASCII가 아니면 modified UTF-7(RFC 3501 §5.1.3)로 인코딩된다 — 표준 base64에서
'/'를 ','로 바꾸고 패딩 '='을 떼며, 비-ASCII 구간을 '&' ... '-'로 감싼다. '&' 자체는 '&-'.
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import base64
import re

_LIST_RE = re.compile(r'^\((?P<flags>[^)]*)\)\s+(?:"[^"]*"|NIL)\s+(?P<name>.*)$')

# 별칭(소문자) → (special-use 플래그, 폴백 폴더명)
_ALIASES = {
    "sent": ("\\Sent", "Sent"),
    "보낸메일함": ("\\Sent", "Sent"),
    "보낸편지함": ("\\Sent", "Sent"),
    "drafts": ("\\Drafts", "Drafts"),
    "draft": ("\\Drafts", "Drafts"),
    "임시보관함": ("\\Drafts", "Drafts"),
    "임시편지함": ("\\Drafts", "Drafts"),  # Naver
    "trash": ("\\Trash", "Trash"),
    "휴지통": ("\\Trash", "Trash"),
    "스팸메일함": ("\\Junk", "Junk"),
    "스팸편지함": ("\\Junk", "Junk"),
    "junk": ("\\Junk", "Junk"),
    "spam": ("\\Junk", "Junk"),
}


def _b64_utf16_encode(chunk: str) -> str:
    raw = base64.b64encode(chunk.encode("utf-16-be")).decode("ascii")
    return raw.rstrip("=").replace("/", ",")


def _b64_utf16_decode(seq: str) -> str:
    standard = seq.replace(",", "/")
    standard += "=" * (-len(standard) % 4)
    return base64.b64decode(standard).decode("utf-16-be")


def encode_mailbox_name(name: str) -> bytes:
    """폴더명을 IMAP modified UTF-7 bytes로. 인쇄 가능 ASCII는 그대로, '&'는 '&-'."""
    out: list[str] = []
    run: list[str] = []

    def flush() -> None:
        if run:
            out.append("&" + _b64_utf16_encode("".join(run)) + "-")
            run.clear()

    for ch in name:
        if 0x20 <= ord(ch) <= 0x7E:
            flush()
            out.append("&-" if ch == "&" else ch)
        else:
            run.append(ch)
    flush()
    return "".join(out).encode("ascii")


def decode_mailbox_name(name: str | bytes) -> str:
    """modified UTF-7 폴더명을 사람이 읽는 유니코드로. '&-'는 '&', '&...-'는 base64 디코딩."""
    if isinstance(name, (bytes, bytearray)):
        name = bytes(name).decode("ascii", "replace")
    out: list[str] = []
    i, n = 0, len(name)
    while i < n:
        ch = name[i]
        if ch == "&":
            end = name.find("-", i + 1)
            if end == -1:
                out.append(name[i:])
                break
            seq = name[i + 1 : end]
            out.append("&" if seq == "" else _b64_utf16_decode(seq))
            i = end + 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def parse_list_line(line: bytes | str) -> tuple[frozenset[str], str]:
    """LIST 응답 한 줄을 (플래그 집합, 디코딩된 폴더명)으로 파싱. 매치 실패 시 (빈집합, "")."""
    if isinstance(line, (bytes, bytearray)):
        line = bytes(line).decode("ascii", "replace")
    match = _LIST_RE.match(line.strip())
    if not match:
        return frozenset(), ""
    flags = frozenset(match.group("flags").split())
    name = match.group("name").strip()
    if len(name) >= 2 and name[0] == '"' and name[-1] == '"':
        name = name[1:-1]
    return flags, decode_mailbox_name(name)


def resolve_special_mailbox(
    list_lines: list[bytes], special_flag: str, fallback: str
) -> str:
    """LIST 응답에서 special-use 플래그를 가진 폴더의 실제 이름. 없으면 fallback."""
    target = special_flag.lower()
    for line in list_lines:
        flags, name = parse_list_line(line)
        if any(flag.lower() == target for flag in flags):
            return name
    return fallback


def select_mailbox_name(requested: str, list_lines: list[bytes]) -> str:
    """요청한 메일박스 별칭을 서버의 실제 폴더명으로 해석.

    'INBOX'는 항상 'INBOX'. 'Sent'/'보낸메일함' 등은 special-use 플래그로 해석.
    아는 별칭이 아니면 그대로 통과(사용자가 실제 폴더명을 직접 줄 수 있다).
    """
    key = (requested or "").strip()
    if key.lower() == "inbox":
        return "INBOX"
    alias = _ALIASES.get(key.lower())
    if alias:
        flag, fallback = alias
        return resolve_special_mailbox(list_lines, flag, fallback)
    return key
