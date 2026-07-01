# daum-mail Skill — Testing Reference

**Last run**: 2026-07-01  
**Credentials**: `source ~/.secrets` loads `DAUM_EMAIL` and `DAUM_APP_PASSWORD`  
**SCRIPTS variable**: set to the `scripts/` directory before each command

```bash
SCRIPTS=/Users/kit.t/workspace/agent-plugins/skills/plugins/karian7/skills/daum-mail/scripts
```

---

## Test Results

### T1 — Inbox List (fetch_inbox.py)

```bash
source ~/.secrets && RECENT_COUNT=5 SNIPPET_CHARS=0 uv run "$SCRIPTS/fetch_inbox.py"
```

**Result**: PASS  
- Returns JSON with `count`, `unread_total`, `items[]`
- Each item has `id` (UID), `unread`, `date`, `from`, `subject`, `message_id`, `snippet`
- Observed: `count=5`, `unread_total=326`, first UID `27500`

---

### T2 — Read Single Mail (read_mail.py)

Uses the first UID from T1.

```bash
source ~/.secrets && uv run "$SCRIPTS/read_mail.py" 27500
```

**Result**: PASS  
- Returns plain-text output with `UID`, `From`, `Date`, `Subject`, separator line, then full body
- Observed: subject "Share your thoughts on WWDC26." from Apple Developer

---

### T3 — Search by Korean Keyword (search_mail.py)

```bash
source ~/.secrets && QUERY="로그인" SEARCH_LIMIT=3 uv run "$SCRIPTS/search_mail.py"
```

**Result**: PASS  
- Returns JSON with `mailbox`, `server_hits`, `scanned`, `scan_truncated`, `count`, `items[]`
- Each item includes `id`, `unread`, `date`, `from`, `to`, `subject`, `snippet`
- Observed: `count=3`, all subjects contained "로그인"
- Note: `server_hits=400` indicates IMAP TEXT search returns many false positives; client-side
  subject/body filtering narrows to accurate matches.

---

### T4 — Search by Date Filter (search_mail.py)

```bash
source ~/.secrets && SEARCH_SINCE=2026-06-01 SEARCH_LIMIT=3 uv run "$SCRIPTS/search_mail.py"
```

**Result**: PASS  
- Returns JSON with `count=3`
- All items have dates on or after 2026-06-01
- Observed dates: 2026-06-28, 2026-06-29, 2026-06-30

---

### T5 — Sent Folder (fetch_inbox.py with MAILBOX alias)

```bash
source ~/.secrets && MAILBOX=보낸편지함 RECENT_COUNT=3 SNIPPET_CHARS=0 uv run "$SCRIPTS/fetch_inbox.py"
```

**Result**: PASS (after bug fix — see IMAP Notes below)  
- Returns JSON with `count`, `unread_total=0`, `items[]`
- Observed: 3 sent mails, all `unread=false`
- `보낸메일함` and `보낸편지함` are supported aliases; both resolve to `\Sent` flag.

---

### T6 — Briefing with Sent Cross-Reference (fetch_inbox.py with BRIEFING_REPLIED)

```bash
source ~/.secrets && BRIEFING_REPLIED=1 RECENT_COUNT=5 SNIPPET_CHARS=200 uv run "$SCRIPTS/fetch_inbox.py"
```

**Result**: PASS (after bug fix — see IMAP Notes below)  
- Returns inbox items enriched with `replied` (bool) and `replied_at` (datetime or null)
- Script reads Sent Messages folder and cross-references In-Reply-To/References headers
- Observed: all 5 items showed `"replied": false, "replied_at": null`

---

### T7 — Draft Save (compose_draft.py)

**Result**: SKIP  
Real data side-effect: saves an email to the Drafts folder. Excluded from automated testing.  
Manual test only, verify and delete the draft afterward.

---

### T8 — Move to Trash (move_to_trash.py)

**Result**: SKIP  
Real data side-effect: moves a mail to Deleted Messages. Excluded from automated testing.  
Manual test only, use a disposable test mail UID and verify in webmail.

---

## IMAP Server Notes (imap.daum.net)

### Folder Names

Daum's IMAP server uses English folder names with spaces:

| Role        | Actual folder name   | \Sent flag |
|-------------|----------------------|------------|
| Inbox       | `INBOX`              | `\Inbox`   |
| Sent        | `Sent Messages`      | `\Sent`    |
| Drafts      | `Drafts`             | `\Drafts`  |
| Trash       | `Deleted Messages`   | `\Trash`   |
| Junk        | (modified UTF-7)     | `\Junk`    |

The skill resolves Korean aliases (`보낸편지함`, `보낸메일함`, `임시보관함`, `휴지통`) via
IMAP LIST special-use flags — so it works regardless of the actual folder name.

### Bug Fixed: Space in Folder Name

**Root cause**: `imaplib.IMAP4.select()` requires folder names containing spaces to be passed
as IMAP quoted strings (`"Sent Messages"`), but the original code passed them unquoted
(`Sent Messages`), causing `EXAMINE command error: BAD [EXAMINE failed. Illegal arguments.]`.

**Fix applied** (2026-07-01): Added `imap_select_name(name: str) -> str` to `folders.py`.
This function encodes the name to modified UTF-7 and wraps it in double quotes when it
contains spaces. All `conn.select()` calls across the four scripts now use this function
instead of the raw `.decode("ascii")` pattern.

Files changed:
- `scripts/folders.py` — added `imap_select_name()`
- `scripts/fetch_inbox.py` — import + two `conn.select()` call sites
- `scripts/read_mail.py` — import + `conn.select()` call site
- `scripts/search_mail.py` — import + `conn.select()` call site
- `scripts/move_to_trash.py` — import + `conn.select()` call site

### Search Behavior

- IMAP `SEARCH TEXT "keyword"` on Daum returns a very broad match set
  (e.g., `server_hits=400` for "로그인"). Client-side filtering in `search_mail.py`
  narrows results to accurate subject/body matches.
- Date filter (`SEARCH_SINCE`) uses IMAP `SINCE` criterion which matches at day granularity
  (inclusive, server local timezone).
- `SEARCH_LIMIT` caps the number of client-side matches returned, not server-side candidates.

### Authentication

- Uses IMAP Application Password (`DAUM_APP_PASSWORD`), not the Kakao/Daum account password.
- The app password is generated in Daum Mail settings under "외부 접속 비밀번호".
- Server: `imap.daum.net:993` (IMAP over SSL).
