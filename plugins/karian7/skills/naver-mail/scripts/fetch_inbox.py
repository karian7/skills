#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["keyring"]
# ///
"""INBOX 최근 메일을 헤더 + 본문 스니펫까지 읽어 JSON으로 출력한다.

분류/요약은 하지 않는다 — 그건 LLM의 몫이다. 이 스크립트의 책임은
"읽기 쉬운 구조화된 원본"을 만드는 것까지다.

자격증명은 환경변수에서만 읽으며 절대 출력하지 않는다:
  NAVER_EMAIL          IMAP 로그인 이메일
  NAVER_APP_PASSWORD   POP3/IMAP 전용 앱 비밀번호 (계정 본 비밀번호 아님)

선택 환경변수:
  MAILBOX        조회할 메일박스 (기본 INBOX). "Sent"/"보낸메일함",
                 "Drafts"/"임시보관함", "Trash"/"휴지통" 별칭은 서버 폴더로 자동 해석.
  RECENT_COUNT   최근 몇 통을 읽을지 (기본 30)
  SNIPPET_CHARS  본문 스니펫 최대 길이 (기본 400, 0이면 본문 생략)
  BRIEFING_REPLIED  on이면 INBOX 조회 시 보낸함을 교차 참조해 각 메일에
                    replied/replied_at을 부여한다 (브리핑 완료 표시용, 기본 off).
  SENT_LOOKBACK  교차 참조할 보낸함 최근 통수 (기본 50)
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from credentials import require_credentials

import email
import imaplib
import json
import re
from email.header import decode_header, make_header
from email.message import Message
from email.utils import parseaddr, parsedate_to_datetime


def _log(*a, **k):  # type: ignore
    pass


from folders import encode_mailbox_name, select_mailbox_name

_TAG_RE = re.compile(r"<[^>]+>")
_STYLE_RE = re.compile(r"<(script|style)[^>]*>.*?</\1>", re.DOTALL | re.IGNORECASE)
# 부분 fetch로 잘려 닫는 태그를 못 만난 style/script 블록은 끝까지 제거한다.
_DANGLING_RE = re.compile(r"<(script|style)[^>]*>.*$", re.DOTALL | re.IGNORECASE)

HOST = "imap.naver.com"
PORT = 993


def decode_mime(value: str | None) -> str:
    """RFC 2047 인코딩된 헤더(=?UTF-8?...?=)를 사람이 읽는 문자열로."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def extract_snippet(msg: Message, limit: int) -> str:
    """text/plain 본문을 best-effort로 추출해 limit 길이로 자른다.

    멀티파트면 첫 text/plain 파트를, 단일파트면 그대로 쓴다.
    인코딩 추정이 실패해도 죽지 않고 빈 문자열로 떨어진다.
    """
    if limit <= 0:
        return ""
    plain = ""
    html = ""
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.get_filename():
            continue
        ctype = part.get_content_type()
        if ctype == "text/plain" and not plain:
            plain = _decode_payload(part)
        elif ctype == "text/html" and not html:
            html = _decode_payload(part)
    # text/plain 우선, 없으면 HTML 태그를 걷어내 폴백한다(뉴스레터·공지는 HTML-only가 흔하다).
    body = plain or _strip_html(html)
    collapsed = " ".join(body.split())
    return collapsed[:limit]


def _strip_html(html: str) -> str:
    if not html:
        return ""
    no_blocks = _STYLE_RE.sub(" ", html)
    no_blocks = _DANGLING_RE.sub(" ", no_blocks)
    return _TAG_RE.sub(" ", no_blocks)


def _decode_payload(part: Message) -> str:
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


_REPLY_PREFIX_RE = re.compile(r"^\s*(re|fwd|fw|답장|회신|전달)\s*:\s*", re.IGNORECASE)
_MSGID_RE = re.compile(r"<[^>]+>")


def normalize_subject(subject: str) -> str:
    """회신/전달 프리픽스(Re:/답장: 등) 반복 제거 + 공백 정규화 + 소문자."""
    text = subject or ""
    while True:
        stripped = _REPLY_PREFIX_RE.sub("", text, count=1)
        if stripped == text:
            break
        text = stripped
    return " ".join(text.split()).lower()


def extract_addr(header_value: str) -> str:
    """'홍길동 <a@b.com>' → 'a@b.com'(소문자). 주소만 있으면 그대로."""
    return parseaddr(header_value or "")[1].strip().lower()


def is_reply_to(inbox_item: dict, sent_msg: dict) -> bool:
    """sent_msg가 inbox_item에 대한 회신인지 판정.

    1순위: 받은 메일 Message-ID가 보낸 메일 In-Reply-To/References에 포함(정확).
    2순위(폴백): 제목(프리픽스 제거 후) 일치 AND 보낸 수신자에 받은 발신자 포함.
    """
    mid = (inbox_item.get("message_id") or "").strip()
    if mid:
        refs = f"{sent_msg.get('in_reply_to', '')} {sent_msg.get('references', '')}"
        ref_ids = set(_MSGID_RE.findall(refs))
        token = mid if mid.startswith("<") else f"<{mid}>"
        if token in ref_ids or mid in ref_ids:
            return True

    isubj = normalize_subject(inbox_item.get("subject", ""))
    if isubj and isubj == normalize_subject(sent_msg.get("subject", "")):
        ifrom = extract_addr(inbox_item.get("from", ""))
        to_addrs = {extract_addr(a) for a in (sent_msg.get("to", "") or "").split(",")}
        if ifrom and ifrom in to_addrs:
            return True
    return False


def _sent_ts(sent_msg: dict) -> float | None:
    """보낸 메일 Date 헤더를 정렬용 epoch 초로. 파싱 불가 시 None.

    timestamp()는 naive/aware datetime 모두 안전하게 float로 떨어뜨려 tz 비교 충돌을 피한다.
    """
    try:
        return parsedate_to_datetime(sent_msg.get("date", "") or "").timestamp()
    except (TypeError, ValueError, OverflowError):
        return None


def mark_replied(items: list[dict], sent_headers: list[dict]) -> list[dict]:
    """각 받은 메일에 replied/replied_at 부여(새 list 반환, 입력 불변).

    여러 회신이 매칭되면 가장 최근 보낸 날짜를 replied_at으로 쓴다.
    """
    result: list[dict] = []
    for item in items:
        matches = [s for s in sent_headers if is_reply_to(item, s)]
        new = dict(item)
        if matches:
            latest, best = matches[-1], _sent_ts(matches[-1])
            for candidate in matches:
                ts = _sent_ts(candidate)
                if ts is not None and (best is None or ts > best):
                    latest, best = candidate, ts
            new["replied"] = True
            new["replied_at"] = latest.get("date") or None
        else:
            new["replied"] = False
            new["replied_at"] = None
        result.append(new)
    return result


def _imap_mailbox_arg(name: str) -> str:
    """IMAP SELECT/EXAMINE 명령에 넘길 메일박스 인자를 만든다.
    공백이 포함된 이름(e.g. 'Sent Messages')은 따옴표로 감싸야 한다."""
    encoded = encode_mailbox_name(name).decode("ascii")
    if " " in encoded:
        return f'"{encoded}"'
    return encoded


def _read_sent_headers(conn, mailbox: str, lookback: int) -> list[dict]:
    """보낸함 최근 lookback통의 스레딩 헤더만 읽는다(본문 미수집). 회신 매칭용 IMAP glue."""
    conn.select(_imap_mailbox_arg(mailbox), readonly=True)
    _, ids = conn.uid("search", "ALL")
    sent_ids = ids[0].split()[-lookback:] if ids and ids[0] else []
    spec = "(BODY.PEEK[HEADER.FIELDS (MESSAGE-ID IN-REPLY-TO REFERENCES SUBJECT TO DATE)])"
    headers: list[dict] = []
    for sid in sent_ids:
        _, data = conn.uid("fetch", sid, spec)
        raw = next((p[1] for p in data if isinstance(p, tuple) and p[1]), None)
        if not raw:
            continue
        m = email.message_from_bytes(raw)
        headers.append(
            {
                "in_reply_to": decode_mime(m["In-Reply-To"]),
                "references": decode_mime(m["References"]),
                "subject": decode_mime(m["Subject"]),
                "to": decode_mime(m["To"]),
                "date": decode_mime(m["Date"]),
            }
        )
    return headers


def main() -> int:
    user, password = require_credentials()

    recent_count = int(os.environ.get("RECENT_COUNT", "30"))
    snippet_chars = int(os.environ.get("SNIPPET_CHARS", "1000"))
    _log(f"fetch 시작 recent={recent_count} snippet={snippet_chars}", "info", "fetch")

    conn = imaplib.IMAP4_SSL(HOST, PORT, timeout=20)
    conn.login(user, password)
    # 별칭(보낸메일함 등)은 LIST의 special-use 플래그로 실제 폴더명을 찾는다.
    # INBOX는 해석이 불필요하므로 LIST 왕복을 생략한다.
    requested = os.environ.get("MAILBOX", "INBOX")
    if requested.strip().lower() == "inbox":
        list_lines: list[bytes] = []
    else:
        list_lines = [ln for ln in (conn.list()[1] or []) if isinstance(ln, bytes)]
    target = select_mailbox_name(requested, list_lines)
    conn.select(_imap_mailbox_arg(target), readonly=True)
    # 폴더명은 식별자라 로그에 남겨도 메일 내용·개인정보가 아니다.
    _log(f"mailbox 선택 target={target}", "info", "fetch")

    # 시퀀스 번호는 새 메일 도착 시 통째로 밀리는 휘발성 식별자다.
    # UID는 메일박스 수명 동안 안정적이라 브리핑의 #id 참조가 깨지지 않는다.
    _, ids = conn.uid("search", "ALL")
    all_ids = ids[0].split()
    recent = all_ids[-recent_count:]

    _, unseen = conn.uid("search", "UNSEEN")
    unseen_set = set(unseen[0].split()) if unseen and unseen[0] else set()

    # 본문 스니펫이 필요하면 전체 메시지를 한 번에 파싱해야 멀티파트 구조가 살아난다.
    # 첨부 메가바이트를 피하려고 앞 PEEK_BYTES만 부분 fetch한다(text/plain은 보통 앞쪽).
    peek_bytes = int(os.environ.get("PEEK_BYTES", "32768"))
    if snippet_chars > 0:
        fetch_spec = f"(BODY.PEEK[]<0.{peek_bytes}>)"
    else:
        fetch_spec = "(BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)])"

    items: list[dict] = []
    for mid in reversed(recent):
        _, msg_data = conn.uid("fetch", mid, fetch_spec)
        raw = next(
            (part[1] for part in msg_data if isinstance(part, tuple) and part[1]),
            None,
        )
        if not raw:
            continue
        msg = email.message_from_bytes(raw)
        items.append(
            {
                "id": mid.decode(),
                "unread": mid in unseen_set,
                "date": decode_mime(msg["Date"]),
                "from": decode_mime(msg["From"]),
                "subject": decode_mime(msg["Subject"]),
                "message_id": decode_mime(msg["Message-ID"]),
                "snippet": extract_snippet(msg, snippet_chars),
            }
        )

    # 브리핑 한정: 보낸함을 교차 참조해 이미 회신한 액션 항목을 표시한다.
    # 목록 조회 등에서는 불필요한 Sent 왕복을 피하려고 BRIEFING_REPLIED로만 켠다.
    replied_count = 0
    briefing_replied = os.environ.get("BRIEFING_REPLIED", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if briefing_replied and target == "INBOX":
        lookback = int(os.environ.get("SENT_LOOKBACK", "50"))
        sent_lines = [ln for ln in (conn.list()[1] or []) if isinstance(ln, bytes)]
        sent_box = select_mailbox_name("Sent", sent_lines)
        items = mark_replied(items, _read_sent_headers(conn, sent_box, lookback))
        replied_count = sum(1 for it in items if it.get("replied"))
        # 카운트만 남긴다 — 어떤 메일이 회신됐는지는 로그로 유추 불가.
        _log(f"회신 매칭 replied={replied_count}/{len(items)} lookback={lookback}", "info", "fetch")

    conn.logout()
    _log(
        f"fetch 완료 mailbox={target} count={len(items)} "
        f"unread={len(unseen_set)} replied={replied_count}",
        "info",
        "fetch",
    )
    print(
        json.dumps(
            {"count": len(items), "unread_total": len(unseen_set), "items": items},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        _log(f"fetch 실패: {type(exc).__name__}: {exc}", "error", "fetch")
        raise
