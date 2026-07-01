# Setup Guide: naver-mail

## 1. Enable IMAP and Create App Password

Go to: **https://mail.naver.com/v2/settings/smtp/imap**

1. Turn on **IMAP** access
2. Generate an **App Password** (application-specific password)
   - This is NOT your regular Naver account password
   - The app password can be revoked without changing your main password

## 2. Store Credentials

### macOS / Windows (Recommended — Keychain / Credential Manager)

```bash
pip install keyring   # or: uv pip install keyring
python3 -c "
import keyring
keyring.set_password('naver-mail', 'email', 'you@naver.com')
keyring.set_password('naver-mail', 'app-password', 'YOUR_APP_PASSWORD')
"
```

- **macOS**: stored in Keychain, auto-unlocked when logged in
- **Windows**: stored in Windows Credential Manager

To verify:
```bash
python3 -c "import keyring; print(keyring.get_password('naver-mail', 'email'))"
```

To delete:
```bash
python3 -c "
import keyring
keyring.delete_password('naver-mail', 'email')
keyring.delete_password('naver-mail', 'app-password')
"
```

### Environment Variables (Fallback)

```bash
export NAVER_EMAIL="you@naver.com"
export NAVER_APP_PASSWORD="YOUR_APP_PASSWORD"
```

Add to `~/.secrets`, `~/.zshrc` (macOS/Linux), or `$PROFILE` (Windows PowerShell).

### Priority

Keychain/Credential Manager → Environment Variables

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| Setup guide printed at runtime | Credentials not found in either location |
| `AUTHENTICATIONFAILED` | Using regular Naver password instead of app password |
| `keyring` not found | Run `pip install keyring` or `uv pip install keyring` |
| macOS Keychain prompt | First run may show a dialog — click "Always Allow" |
