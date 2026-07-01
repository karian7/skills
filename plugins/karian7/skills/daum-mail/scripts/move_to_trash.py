#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# dependencies = ["keyring"]
# ///
"""메일을 휴지통(Trash)으로 이동한다 — 영구 삭제는 하지 않는다.

UID로 지정한 메일을 원본 폴더에서 Trash로 옮긴다. 이 서버 CAPABILITY엔 MOVE가 없어
COPY → \\Deleted 플래그 → EXPUNGE로 에뮬레이션한다. Trash에 복사본이 남으므로 복구 가능하다.
영구 삭제(Trash 비우기/직접 destroy) 경로는 의도적으로 두지 않는다.

UIDPLUS 미지원이라 EXPUNGE는 원본 폴더의 \\Deleted 전체를 제거한다(보통 우리가 방금
표시한 메일뿐). 영구 삭제가 아니라 Trash로의 이동이며 복사본은 유지된다.

자격증명은 환경변수에서만 읽는다(DAUM_EMAIL / DAUM_APP_PASSWORD).
입력:
  UID            이동할 메일 UID(콤마로 여러 개). argv로도 받는다.
  MAILBOX        원본 폴더(기본 INBOX)
"""

from __future__ import annotations

import imaplib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from credentials import require_credentials


def _log(*a, **k):
    pass


from folders import encode_mailbox_name, imap_select_name, select_mailbox_name

HOST = "imap.daum.net"
PORT = 993


def _uids(argv: list[str], env: str | None) -> list[str]:
    """argv(우선) 또는 env에서 UID 목록을 추출. 콤마·공백 혼용 허용."""
    raw = " ".join(argv[1:]) if len(argv) > 1 else (env or "")
    return [u.strip() for u in raw.replace(",", " ").split() if u.strip()]


def main() -> int:
    user, password = require_credentials()

    uids = _uids(sys.argv, os.environ.get("UID"))
    if not uids:
        print("✗ UID가 필요합니다. 예: move_to_trash.py 516350", file=sys.stderr)
        return 2

    requested = os.environ.get("MAILBOX", "INBOX")
    # UID는 식별자라 감사/복구 추적용으로 남긴다(메일 내용·개인정보 아님).
    _log(f"trash 시작 source={requested} uids={','.join(uids)}", "info", "trash")

    conn = imaplib.IMAP4_SSL(HOST, PORT, timeout=20)
    conn.login(user, password)
    list_lines = [ln for ln in (conn.list()[1] or []) if isinstance(ln, bytes)]
    source = select_mailbox_name(requested, list_lines)
    trash = select_mailbox_name("Trash", list_lines)
    if source == trash:
        conn.logout()
        print("✗ 원본이 이미 휴지통입니다.", file=sys.stderr)
        return 1

    # COPY 후 원본에서 제거해야 '이동'이 된다 → 원본을 쓰기 모드로 연다.
    conn.select(imap_select_name(source), readonly=False)
    trash_box = encode_mailbox_name(trash).decode("ascii")
    moved: list[str] = []
    for uid in uids:
        typ, _ = conn.uid("COPY", uid, trash_box)
        if typ != "OK":
            _log(f"trash COPY 실패 uid={uid}", "error", "trash")
            continue
        conn.uid("STORE", uid, "+FLAGS", r"(\Deleted)")
        moved.append(uid)
    if moved:
        conn.expunge()  # 원본의 \Deleted 제거 — Trash 복사본은 그대로(영구 삭제 아님)
    conn.logout()

    _log(f"trash 완료 source={source} trash={trash} moved={len(moved)}/{len(uids)}", "info", "trash")
    if not moved:
        print("✗ 휴지통 이동 실패.", file=sys.stderr)
        return 1
    print(
        f"✓ 휴지통({trash})으로 이동 — {len(moved)}건 (복구 가능, 영구 삭제 아님). "
        f"UID {', '.join(moved)}"
    )
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        _log(f"trash 실패: {type(exc).__name__}", "error", "trash")
        raise
