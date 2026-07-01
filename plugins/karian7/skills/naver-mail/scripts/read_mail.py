#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["keyring"]
# ///
"""INBOX의 특정 메일 하나를 UID로 읽어 헤더 + 전체 본문을 출력한다.

브리핑은 스니펫만 보지만, 사용자가 "이 메일 본문 보여줘"라고 하면 이 스크립트로
전문을 펼친다. 인용 스레드까지 그대로 디코딩한다(순수 IMAP, 웹메일 불필요).

사용:
  UID=516350 uv run read_mail.py
  uv run read_mail.py 516350

자격증명은 환경변수에서만 읽는다(NAVER_EMAIL / NAVER_APP_PASSWORD).
출력은 JSON이 아니라 사람이 읽는 텍스트(에이전트가 그대로 사용자에게 전달).
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from credentials import require_credentials

import email
import imaplib
import re
from email.header import decode_header, make_header
from email.message import Message


def _log(*a, **k):  # type: ignore
    pass


from folders import encode_mailbox_name, select_mailbox_name

HOST = "imap.naver.com"
PORT = 993

_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
_DANGLING_RE = re.compile(r"<(script|style)[^>]*>.*$", re.DOTALL | re.IGNORECASE)


def decode_mime(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def decode_payload(part: Message) -> str:
    payload = part.get_payload(decode=True)
    if not isinstance(payload, (bytes, bytearray)):
        return ""
    charset = part.get_content_charset() or "utf-8"
    for enc in (charset, "utf-8", "euc-kr", "cp949"):
        try:
            return bytes(payload).decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return bytes(payload).decode("utf-8", errors="replace")


def strip_html(html: str) -> str:
    no_blocks = _STYLE_RE.sub(" ", html)
    no_blocks = _DANGLING_RE.sub(" ", no_blocks)
    return _TAG_RE.sub(" ", no_blocks)


def extract_body(msg: Message) -> str:
    plain = ""
    html = ""
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_filename():
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain" and not plain:
            plain = decode_payload(part)
        elif ctype == "text/html" and not html:
            html = decode_payload(part)
    body = plain or strip_html(html)
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n\s*\n\s*\n+", "\n\n", body)
    return body.strip()


def main() -> int:
    uid = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("UID", "")).strip()
    if not uid:
        print("✗ UID가 필요합니다. 예: read_mail.py 516350", file=sys.stderr)
        return 2

    user, password = require_credentials()

    _log(f"read 시작 uid={uid}", "info", "read")
    conn = imaplib.IMAP4_SSL(HOST, PORT, timeout=20)
    conn.login(user, password)
    requested = os.environ.get("MAILBOX", "INBOX")
    if requested.strip().lower() == "inbox":
        list_lines: list[bytes] = []
    else:
        list_lines = [ln for ln in (conn.list()[1] or []) if isinstance(ln, bytes)]
    target = select_mailbox_name(requested, list_lines)
    conn.select(encode_mailbox_name(target).decode("ascii"), readonly=True)
    _, data = conn.uid("fetch", uid, "(BODY.PEEK[])")
    raw = next((part[1] for part in data if isinstance(part, tuple) and part[1]), None)
    conn.logout()
    if not raw:
        print(f"✗ UID {uid} 메일을 찾지 못했습니다.", file=sys.stderr)
        _log(f"read 실패: uid={uid} 없음", "error", "read")
        return 1
    _log(f"read 완료 uid={uid}", "info", "read")

    msg = email.message_from_bytes(raw)
    attachments = [decode_mime(p.get_filename()) for p in msg.walk() if p.get_filename()]

    print(f"UID    : {uid}")
    print(f"From   : {decode_mime(msg['From'])}")
    print(f"Date   : {decode_mime(msg['Date'])}")
    print(f"Subject: {decode_mime(msg['Subject'])}")
    if attachments:
        print(f"첨부   : {len(attachments)}개 — {', '.join(a for a in attachments if a)}")
    print("=" * 70)
    print(extract_body(msg))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        _log(f"read 실패: {type(exc).__name__}: {exc}", "error", "read")
        raise
