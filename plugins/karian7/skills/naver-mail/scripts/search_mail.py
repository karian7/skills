#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["keyring"]
# ///
"""메일 하이브리드 검색 — 서버 필터 + 클라이언트 키워드 매칭, JSON 출력.

NOTE: Naver/Daum은 SUBJECT 서버 검색 미실측 — 표준 준수 서버라 동작 가능성 있으나
클라이언트측 매칭으로 안전하게 구현.

서버 실측(imap.kakaowork.com 기준): 순정 IMAP4rev1(확장 전무)로
FROM/TO/CC·날짜·플래그·크기 SEARCH만 정확하고, SUBJECT/BODY/TEXT/HEADER는
문법만 수락한 채 항상 0건을 돌려준다(BAD가 아니라 OK+빈 결과 — 평문 ASCII
제목 토큰조차 안 잡힌다). 그래서 서버 SUBJECT에 의존하지 않고 검색을 둘로 나눈다:

  ① 서버측 prefilter — 발신자/수신자 주소(ASCII)·날짜·읽음상태로 UID 후보 축소
  ② 클라이언트측 키워드 — 후보 헤더를 RFC 2047 디코딩한 뒤 제목·발신자·수신자
     (+옵션 본문)에서 NFC 정규화·casefold 부분 매칭(공백 구분 토큰 AND)

자격증명은 환경변수에서만 읽는다(NAVER_EMAIL / NAVER_APP_PASSWORD).

사용:
  QUERY="회의 일정" uv run search_mail.py
  uv run search_mail.py 회의 일정      (CLI 인자도 키워드로 합침)

선택 환경변수:
  SEARCH_FROM    발신자 필터. ASCII 주소(부분 일치)는 서버측, 한글 표시명은 클라이언트측.
  SEARCH_TO      수신자 필터(보낸메일함 검색용). 규칙은 SEARCH_FROM과 동일.
  SEARCH_SINCE   이 날짜 이후(YYYY-MM-DD, 그날 포함). SEARCH_BEFORE는 그날 미만.
  SEARCH_UNSEEN  on이면 안 읽은 메일만.
  SEARCH_BODY    on이면 본문까지 키워드 매칭(후보 전체 본문 fetch — 더 느림).
  SEARCH_LIMIT   결과 최대 건수 (기본 20)
  SCAN_LIMIT     키워드 매칭으로 살펴볼 최근 후보 상한 (기본 200). 결과의
                 scan_truncated=true면 더 오래된 메일은 안 봤다는 뜻 —
                 날짜·발신자 필터로 좁히거나 SCAN_LIMIT을 올린다.
  MAILBOX / SNIPPET_CHARS(기본 400) / PEEK_BYTES — fetch_inbox.py와 동일.
"""

from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from credentials import require_credentials

import email
import imaplib
import json
import re
import unicodedata
from datetime import date


def _log(*a, **k):  # type: ignore
    pass


from fetch_inbox import decode_mime, extract_snippet
from folders import encode_mailbox_name, select_mailbox_name

HOST = "imap.naver.com"
PORT = 993

_UID_RE = re.compile(rb"UID (\d+)")

# strftime %b는 로케일 의존이라 쓰지 않는다 — RFC 3501 date-month는 항상 영문 약어.
_MONTHS = (
    "Jan", "Feb", "Mar", "Apr", "May", "Jun",
    "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
)


def to_imap_date(value: str) -> str:
    """ISO 날짜(YYYY-MM-DD)를 IMAP date(DD-Mon-YYYY)로. 형식이 다르면 ValueError."""
    try:
        d = date.fromisoformat(value.strip())
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"날짜는 YYYY-MM-DD 형식이어야 합니다: {value!r}") from exc
    return f"{d.day:02d}-{_MONTHS[d.month - 1]}-{d.year}"


def _clean_addr(value: str | None) -> str:
    """IMAP quoted-string에 안전하게 넣도록 따옴표·역슬래시 제거."""
    return (value or "").replace('"', "").replace("\\", "").strip()


def build_uid_criteria(
    sender: str | None = None,
    recipient: str | None = None,
    since: str | None = None,
    before: str | None = None,
    unseen: bool = False,
) -> tuple[list[str], dict[str, str]]:
    """필터를 (서버측 UID SEARCH criteria, 클라이언트측 잔여 필터)로 나눈다.

    서버 FROM/TO는 raw 주소 substring만 매칭하므로 ASCII 필터만 서버로 보내고,
    한글 표시명 필터는 디코딩된 헤더에 대고 클라이언트에서 매칭한다.
    """
    criteria: list[str] = []
    client: dict[str, str] = {}
    if unseen:
        criteria.append("UNSEEN")
    if since:
        criteria += ["SINCE", to_imap_date(since)]
    if before:
        criteria += ["BEFORE", to_imap_date(before)]
    for key, label, value in (("sender", "FROM", sender), ("recipient", "TO", recipient)):
        cleaned = _clean_addr(value)
        if not cleaned:
            continue
        if cleaned.isascii():
            criteria += [label, f'"{cleaned}"']
        else:
            client[key] = cleaned
    return (criteria or ["ALL"]), client


_CRITERIA_KEYS = frozenset({"ALL", "UNSEEN", "SINCE", "BEFORE", "FROM", "TO"})


def criteria_keys(criteria: list[str]) -> str:
    """로그용 비식별 요약 — criteria에서 키워드만 추린다(날짜·주소 값 제외)."""
    return ",".join(c for c in criteria if c in _CRITERIA_KEYS)


def normalize_for_match(text: str) -> str:
    """NFC 정규화 + casefold + 공백 축약 — 한글 NFD(macOS)와 대소문자 차이를 흡수."""
    return " ".join(unicodedata.normalize("NFC", text or "").casefold().split())


def tokenize_query(query: str) -> list[str]:
    """검색어를 공백 기준 토큰으로 쪼개 정규화한다. 빈 검색어는 빈 리스트."""
    return [normalize_for_match(t) for t in (query or "").split()]


def item_matches(
    item: dict,
    tokens: list[str],
    include_body: bool = False,
    client: dict[str, str] | None = None,
) -> bool:
    """디코딩된 헤더(+옵션 본문)에 모든 토큰이 부분 일치하는지(AND) 판정.

    tokens가 비면 키워드 조건은 통과 — 서버 필터만 쓰는 검색을 허용한다.
    client의 sender/recipient는 한글 표시명 폴백 필터(해당 필드에만 매칭).
    """
    fields = [item.get("from", ""), item.get("to", ""), item.get("subject", "")]
    if include_body:
        fields.append(item.get("snippet", ""))
    haystack = normalize_for_match(" ".join(fields))
    if any(token not in haystack for token in tokens):
        return False
    for key, field in (("sender", "from"), ("recipient", "to")):
        want = (client or {}).get(key)
        if want and normalize_for_match(want) not in normalize_for_match(item.get(field, "")):
            return False
    return True


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


def _batch_fetch(conn, uids: list[bytes], spec: str) -> dict[bytes, bytes]:
    """UID 묶음을 한 번의 FETCH로 가져와 {uid: raw} 매핑으로.

    일부 서버(Naver 등)는 응답을 두 파트로 분리한다:
      part[N]   = (b'SEQ (BODY[...] {size}', b'<header bytes>')  — 헤더 본문
      part[N+1] = b' UID 9534)'                                  — UID + 닫는 괄호

    두 파트를 함께 스캔해 UID를 찾고 헤더 본문과 연결한다.
    """
    out: dict[bytes, bytes] = {}
    if not uids:
        return out
    _, data = conn.uid("fetch", b",".join(uids).decode("ascii"), spec)
    items = list(data or [])
    i = 0
    while i < len(items):
        part = items[i]
        if isinstance(part, tuple) and part[1]:
            raw = part[1]
            # UID가 part[0]에 있으면 (KakaoWork 등)
            m = _UID_RE.search(part[0])
            if not m and i + 1 < len(items):
                # UID가 다음 bytes 파트에 있으면 (Naver 등)
                nxt = items[i + 1]
                if isinstance(nxt, bytes):
                    m = _UID_RE.search(nxt)
                    i += 1  # 다음 파트 소비
            if m:
                out[m.group(1)] = raw
        i += 1
    return out


def main() -> int:
    user, password = require_credentials()

    query = os.environ.get("QUERY") or " ".join(sys.argv[1:])
    tokens = tokenize_query(query)
    try:
        criteria, client = build_uid_criteria(
            sender=os.environ.get("SEARCH_FROM"),
            recipient=os.environ.get("SEARCH_TO"),
            since=os.environ.get("SEARCH_SINCE"),
            before=os.environ.get("SEARCH_BEFORE"),
            unseen=_env_flag("SEARCH_UNSEEN"),
        )
    except ValueError as exc:
        print(f"✗ {exc}", file=sys.stderr)
        return 2
    if not tokens and criteria == ["ALL"] and not client:
        print(
            "✗ 검색 조건이 없습니다. QUERY 키워드 또는 SEARCH_FROM/SEARCH_TO/"
            "SEARCH_SINCE/SEARCH_BEFORE/SEARCH_UNSEEN 필터를 주세요.",
            file=sys.stderr,
        )
        return 2

    limit = int(os.environ.get("SEARCH_LIMIT", "20"))
    scan_limit = int(os.environ.get("SCAN_LIMIT", "200"))
    snippet_chars = int(os.environ.get("SNIPPET_CHARS", "400"))
    peek_bytes = int(os.environ.get("PEEK_BYTES", "32768"))
    body_mode = _env_flag("SEARCH_BODY")
    # 검색어·주소는 메일 내용에 준해 로그에 남기지 않는다 — 필터 종류·카운트만.
    _log(
        f"search 시작 criteria={criteria_keys(criteria)} "
        f"tokens={len(tokens)} body={body_mode}",
        "info",
        "search",
    )

    conn = imaplib.IMAP4_SSL(HOST, PORT, timeout=20)
    conn.login(user, password)
    requested = os.environ.get("MAILBOX", "INBOX")
    if requested.strip().lower() == "inbox":
        list_lines: list[bytes] = []
    else:
        list_lines = [ln for ln in (conn.list()[1] or []) if isinstance(ln, bytes)]
    target = select_mailbox_name(requested, list_lines)
    conn.select(encode_mailbox_name(target).decode("ascii"), readonly=True)

    _, ids = conn.uid("search", *criteria)
    server_uids = ids[0].split() if ids and ids[0] else []
    candidates = server_uids[-scan_limit:]
    candidates.reverse()  # 최신 우선

    _, unseen = conn.uid("search", "UNSEEN")
    unseen_set = set(unseen[0].split()) if unseen and unseen[0] else set()

    if body_mode:
        fetch_spec = f"(BODY.PEEK[]<0.{peek_bytes}>)"
        chunk_size = 20
    else:
        fetch_spec = "(BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE)])"
        chunk_size = 100

    matched: list[dict] = []
    scanned = 0
    for start in range(0, len(candidates), chunk_size):
        chunk = candidates[start : start + chunk_size]
        fetched = _batch_fetch(conn, chunk, fetch_spec)
        for uid in chunk:
            scanned += 1
            raw = fetched.get(uid)
            if not raw:
                continue
            msg = email.message_from_bytes(raw)
            # 매칭은 fetch한 본문 전체로, 표시는 snippet_chars로 자른다.
            body_text = extract_snippet(msg, peek_bytes) if body_mode else ""
            item = {
                "id": uid.decode(),
                "unread": uid in unseen_set,
                "date": decode_mime(msg["Date"]),
                "from": decode_mime(msg["From"]),
                "to": decode_mime(msg["To"]),
                "subject": decode_mime(msg["Subject"]),
                "snippet": body_text,
            }
            if item_matches(item, tokens, include_body=body_mode, client=client):
                item["snippet"] = body_text[:snippet_chars]
                matched.append(item)
                if len(matched) >= limit:
                    break
        if len(matched) >= limit:
            break

    # 헤더 모드에선 매칭된 결과만 본문을 가져와 스니펫을 채운다(≤limit 통).
    if not body_mode and snippet_chars > 0 and matched:
        uids = [it["id"].encode("ascii") for it in matched]
        bodies = _batch_fetch(conn, uids, f"(BODY.PEEK[]<0.{peek_bytes}>)")
        for it in matched:
            raw = bodies.get(it["id"].encode("ascii"))
            if raw:
                it["snippet"] = extract_snippet(
                    email.message_from_bytes(raw), snippet_chars
                )

    conn.logout()
    scan_truncated = len(server_uids) > scan_limit and len(matched) < limit
    _log(
        f"search 완료 mailbox={target} server_hits={len(server_uids)} "
        f"scanned={scanned} matched={len(matched)} truncated={scan_truncated}",
        "info",
        "search",
    )
    print(
        json.dumps(
            {
                "mailbox": target,
                "server_hits": len(server_uids),
                "scanned": scanned,
                "scan_truncated": scan_truncated,
                "count": len(matched),
                "items": matched,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        _log(f"search 실패: {type(exc).__name__}: {exc}", "error", "search")
        raise
