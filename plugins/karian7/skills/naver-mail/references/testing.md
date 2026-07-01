# naver-mail skill — Testing Reference

**Date tested:** 2026-07-01  
**Credentials:** `source ~/.secrets` loads `NAVER_EMAIL` and `NAVER_APP_PASSWORD`  
**SCRIPTS variable:** `SCRIPTS=/Users/kit.t/workspace/agent-plugins/skills/plugins/karian7/skills/naver-mail/scripts`

---

## T1 — Inbox List

**Command:**
```bash
source ~/.secrets && RECENT_COUNT=5 SNIPPET_CHARS=0 uv run "$SCRIPTS/fetch_inbox.py"
```

**Result:** PASS (2026-07-01)  
- `count: 5`, `unread_total: 980`  
- First item: `id: "9535"`, `from: "네이버 <account_noreply@navercorp.com>"`, `date: "Fri, 26 Jun 2026 20:58:24 +0900"`  
- All items have `id`, `unread`, `date`, `from`, `subject`, `message_id` fields

---

## T2 — Read Single Mail

**Command:**
```bash
source ~/.secrets && uv run "$SCRIPTS/read_mail.py" <UID>
```

**Example with UID from T1:**
```bash
source ~/.secrets && uv run "$SCRIPTS/read_mail.py" 9535
```

**Result:** PASS (2026-07-01)  
- Outputs `UID`, `From`, `Date`, `Subject` header block followed by full body text  
- Subject: `2단계 인증을 위한 애플리케이션 비밀번호 생성`  
- Body: HTML mail rendered as plain text

---

## T3 — Search by Korean Keyword

**Command:**
```bash
source ~/.secrets && QUERY="네이버" SEARCH_LIMIT=3 uv run "$SCRIPTS/search_mail.py"
```

**Result:** PASS (2026-07-01)  
- `count: 3`, `server_hits: 1000`, `scanned: 3`, `scan_truncated: false`  
- All 3 results have "네이버" in the `from` field (sender domain `navercorp.com`)  
- UIDs: `9535`, `9534`, `9529`

**Note:** `server_hits: 1000` indicates Naver's IMAP SEARCH returns all matching UIDs; the `SEARCH_LIMIT` parameter controls how many the script fetches and returns. Korean keyword search matches both subject and from fields.

---

## T4 — Search by Date Filter

**Command:**
```bash
source ~/.secrets && SEARCH_SINCE=2026-06-01 SEARCH_LIMIT=3 uv run "$SCRIPTS/search_mail.py"
```

**Result:** PASS (2026-07-01)  
- `count: 3`, `server_hits: 3`, all items dated on or after 2026-06-01  
- Oldest returned: `id: "9529"`, date `Thu, 4 Jun 2026`  
- Server-side `SINCE` filter works correctly; all results are within the date range

---

## T5 — Sent Mail Folder

**Command:**
```bash
source ~/.secrets && MAILBOX=보낸메일함 RECENT_COUNT=3 SNIPPET_CHARS=0 uv run "$SCRIPTS/fetch_inbox.py"
```

**Result:** PASS (2026-07-01) — after bug fix applied  
- `count: 1` (only 1 item in sent folder)  
- `id: "7043"`, `date: "Tue, 04 Jul 2023 17:47:15 +0900"`, `unread: false`  
- Zero items is also valid output; the JSON structure is correct regardless

**Bug fixed:** Naver IMAP exposes the sent folder as `"Sent Messages"` (name contains a space). The IMAP `EXAMINE` command requires mailbox names with spaces to be quoted (e.g. `"Sent Messages"`). The script was not quoting them, causing `BAD [Error in IMAP command EXAMINE: Invalid arguments.]`. Fixed by adding `_imap_mailbox_arg()` helper in `fetch_inbox.py` that wraps space-containing names in double quotes.

---

## T6 — Briefing with Replied Cross-Reference

**Command:**
```bash
source ~/.secrets && BRIEFING_REPLIED=1 RECENT_COUNT=5 SNIPPET_CHARS=200 uv run "$SCRIPTS/fetch_inbox.py"
```

**Result:** PASS (2026-07-01) — after bug fix applied (same fix as T5)  
- All 5 items include `replied: false` and `replied_at: null` fields  
- The script successfully opens the sent folder to cross-reference reply state  
- The `replied`/`replied_at` fields are present on every inbox item when `BRIEFING_REPLIED=1`

---

## T7 — Save Draft (SKIPPED)

**Command (for reference only — do NOT run in automated tests):**
```bash
source ~/.secrets && TO="..." SUBJECT="..." BODY="..." uv run "$SCRIPTS/compose_draft.py"
```

**Reason skipped:** This command saves a real draft to the Drafts folder. Run manually only when you explicitly intend to create a draft.

---

## T8 — Move to Trash (SKIPPED)

**Command (for reference only — do NOT run in automated tests):**
```bash
source ~/.secrets && uv run "$SCRIPTS/move_to_trash.py" <UID>
```

**Reason skipped:** This command moves a real mail to Trash. Run manually only when you explicitly intend to delete a message.

---

## IMAP Server Notes (imap.naver.com:993)

### Actual folder names (from LIST response)

| Alias (Korean/English) | Actual server name | Special-use flag |
|---|---|---|
| `INBOX` | `INBOX` | `\Inbox` |
| `보낸메일함` / `Sent` | `Sent Messages` | `\Sent` |
| `임시보관함` / `Drafts` | `Drafts` | `\Drafts` |
| `휴지통` / `Trash` | `Deleted Messages` | `\Trash` |
| `스팸메일함` / `Junk` | `Junk` | `\Junk` |

**Critical:** Folder names `"Sent Messages"` and `"Deleted Messages"` contain spaces and **must be quoted** in IMAP SELECT/EXAMINE commands. `imaplib` does not auto-quote them. The `_imap_mailbox_arg()` helper in `fetch_inbox.py` handles this.

### Search behavior

- Naver IMAP SEARCH returns up to 1000 UIDs for broad queries (e.g., sender domain search).
- `SEARCH_SINCE` maps to the IMAP `SINCE` criterion, which is server-side and efficient.
- Korean keyword search (`QUERY=...`) uses IMAP `TEXT` or `OR SUBJECT ... FROM ...` criteria — the server handles UTF-8 search natively.
- `SEARCH_LIMIT` is a client-side cap on how many results are fully fetched; `server_hits` in the JSON reflects the total server-side match count.

### Known limitations

- Large mailboxes: `unread_total` counts all UNSEEN messages across the full mailbox, not just the fetched window. With 980 unread messages, search + fetch can be slow without limit caps.
- Partial fetch: `PEEK_BYTES` (default 32768) is used for snippet extraction. Mails with large HTML headers before the text content may yield HTML-heavy snippets rather than plain text.
