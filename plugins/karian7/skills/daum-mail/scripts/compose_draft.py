#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["keyring"]
# ///
"""메일 클라이언트(웹메일)의 임시보관함(Drafts)에 초안 메일을 저장한다 — 발송은 하지 않는다.

사용자가 "메일 작성해줘"라고 하면 본문을 받아 IMAP APPEND로 Drafts에 \\Draft 플래그로
넣어둔다. SMTP 발송 경로는 의도적으로 없다(외부로 메일이 나가지 않음). 사용자는 메일
클라이언트(웹메일)의 임시보관함에서 검토한 뒤 직접 보낸다.

자격증명은 환경변수에서만 읽으며 절대 출력하지 않는다(DAUM_EMAIL / DAUM_APP_PASSWORD).
입력:
  DRAFT_TO       수신자(콤마 구분, 필수)
  DRAFT_SUBJECT  제목
  DRAFT_BODY     본문
  DRAFT_CC       참조(콤마 구분, 선택)
"""

from __future__ import annotations

import imaplib
import mimetypes
import os
import pathlib
import sys
import time
from email import policy
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from credentials import require_credentials


def _log(*a, **k):
    pass


from folders import encode_mailbox_name, select_mailbox_name

HOST = "imap.daum.net"
PORT = 993

# Daum 서버 한도 미확인 — 보수적으로 25MB로 설정.
MAX_MESSAGE_BYTES = 25 * 1024 * 1024


def oversize_warning(raw_len: int, limit: int) -> str | None:
    """메시지가 한도 초과면 사람이 읽을 안내 문자열, 이하면 None.

    판정은 최종 메시지(raw) 크기 기준이라 base64 부풀림이 이미 반영돼 있다.
    첨부는 base64로 약 4/3배 커지므로 원본 합계는 한도의 75%쯤으로 안내한다.
    """
    if raw_len <= limit:
        return None
    mb = raw_len / 1024 / 1024
    limit_mb = limit / 1024 / 1024
    origin_mb = int(limit_mb * 3 / 4)  # 보수적으로 내림 — 본문·CRLF 오버헤드 여유.
    return (
        f"✗ 메일 크기 {mb:.1f}MB가 한도 {limit_mb:.0f}MB를 초과합니다. "
        f"첨부는 base64로 약 1.33배 커지니 원본 합계를 ~{origin_mb}MB 이하로 줄이거나, "
        f"큰 파일은 드라이브 링크로 공유하세요."
    )


def build_draft_message(
    sender: str,
    to: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    date: str | None = None,
    attachments: list[tuple[str, bytes]] | None = None,
) -> bytes:
    """초안 RFC822 메시지를 bytes로 생성. 한글 제목은 RFC2047, 본문은 UTF-8.

    attachments는 (파일명, 내용bytes) 튜플 목록 — 파일 I/O는 호출자(main)가 맡고
    이 순수 함수는 이미 읽은 데이터만 받아 MIME 타입을 확장자로 추론해 첨부한다.
    첨부가 하나라도 있으면 메시지는 multipart/mixed로 승격되고, 없으면 단일
    text/plain 그대로다. IMAP APPEND에 그대로 넘길 raw bytes(CRLF 줄바꿈)를 반환한다.
    """
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = ", ".join(to)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg["Date"] = date or formatdate(localtime=True)
    msg["Message-ID"] = make_msgid()
    msg.set_content(body)
    for filename, data in attachments or []:
        ctype, _ = mimetypes.guess_type(filename)
        maintype, subtype = (ctype or "application/octet-stream").split("/", 1)
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=filename)
    return msg.as_bytes(policy=policy.SMTP)


def _split(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(",") if part.strip()]


def _split_lines(value: str | None) -> list[str]:
    # 첨부 경로는 공백·콤마가 흔하므로 개행으로만 가른다.
    return [line.strip() for line in (value or "").splitlines() if line.strip()]


def _read_attachments(paths: list[str]) -> list[tuple[str, bytes]] | None:
    """경로 목록을 (파일명, bytes)로 읽는다. 하나라도 없거나 못 읽으면 None(중단 신호).

    파일 I/O는 여기(side-effectful glue)에 가두고 순수 함수에는 읽은 데이터만 넘긴다.
    """
    attachments: list[tuple[str, bytes]] = []
    for path in paths:
        p = pathlib.Path(path).expanduser()
        if not p.is_file():
            print(f"✗ 첨부 파일을 찾을 수 없습니다: {path}", file=sys.stderr)
            return None
        try:
            data = p.read_bytes()
        except OSError as exc:  # noqa: BLE001
            print(f"✗ 첨부 파일을 읽을 수 없습니다: {path} ({type(exc).__name__})", file=sys.stderr)
            return None
        attachments.append((p.name, data))
    return attachments


def main() -> int:
    user, password = require_credentials()

    to = _split(os.environ.get("DRAFT_TO"))
    subject = os.environ.get("DRAFT_SUBJECT", "")
    body = os.environ.get("DRAFT_BODY", "")
    cc = _split(os.environ.get("DRAFT_CC"))
    if not to:
        print("✗ DRAFT_TO(수신자)가 필요합니다.", file=sys.stderr)
        return 2

    attachments = _read_attachments(_split_lines(os.environ.get("DRAFT_ATTACHMENTS")))
    if attachments is None:
        return 2  # 첨부 누락·읽기 실패 — 저장하지 않고 즉시 중단(fail-fast).

    # 수신자 수·첨부 수·제목 길이만 로깅 — 주소·제목·파일명 평문은 남기지 않는다.
    _log(
        f"compose 시작 to_count={len(to)} cc_count={len(cc)} "
        f"attach_count={len(attachments)} subj_len={len(subject)}",
        "info",
        "compose",
    )

    raw = build_draft_message(
        user, to, subject, body, cc=cc or None, attachments=attachments or None
    )

    warning = oversize_warning(len(raw), MAX_MESSAGE_BYTES)
    if warning:
        # IMAP 로그인·APPEND를 시도조차 않고 차단 — 헛업로드를 막는다.
        _log(f"compose 거부 oversize bytes={len(raw)}", "warn", "compose")
        print(warning, file=sys.stderr)
        return 2

    conn = imaplib.IMAP4_SSL(HOST, PORT, timeout=20)
    conn.login(user, password)
    list_lines = [ln for ln in (conn.list()[1] or []) if isinstance(ln, bytes)]
    drafts = select_mailbox_name("Drafts", list_lines)
    # 발송 아님 — Drafts에 \Draft로 APPEND만 한다(외부로 나가지 않는다).
    typ, _resp = conn.append(
        encode_mailbox_name(drafts).decode("ascii"),
        r"(\Draft)",
        imaplib.Time2Internaldate(time.time()),
        raw,
    )
    conn.logout()

    if typ != "OK":
        _log(f"compose 실패 resp={typ}", "error", "compose")
        print(f"✗ 임시보관함 저장 실패: {typ}", file=sys.stderr)
        if attachments:
            print(
                "  서버가 거부했습니다 — 첨부가 서버 한도(25MB)를 넘었을 수 있습니다.",
                file=sys.stderr,
            )
        return 1
    _log(f"compose 완료 mailbox={drafts} bytes={len(raw)}", "info", "compose")
    print(
        f"✓ 임시보관함({drafts})에 저장됨 — 검토 후 메일 클라이언트(웹메일)에서 직접 보내세요. (발송 안 함)"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        _log(f"compose 실패: {type(exc).__name__}", "error", "compose")
        raise
