# Setup Guide: daum-mail

## 1. Enable IMAP and Create App Password

Go to: **https://mail.daum.net/setting/POP3IMAP**

1. Turn on **IMAP** access
2. Generate an **App Password** (application-specific password)
   - This is NOT your regular Kakao account password
   - The app password can be revoked without changing your main password

## 2. Store Credentials

### macOS / Windows (Recommended — Keychain / Credential Manager)

```bash
pip install keyring   # or: uv pip install keyring
python3 -c "
import keyring
keyring.set_password('daum-mail', 'email', 'you@daum.net')
keyring.set_password('daum-mail', 'app-password', 'YOUR_APP_PASSWORD')
"
```

- **macOS**: stored in Keychain, auto-unlocked when logged in
- **Windows**: stored in Windows Credential Manager

To verify:
```bash
python3 -c "import keyring; print(keyring.get_password('daum-mail', 'email'))"
```

To delete:
```bash
python3 -c "
import keyring
keyring.delete_password('daum-mail', 'email')
keyring.delete_password('daum-mail', 'app-password')
"
```

### Environment Variables (Fallback)

```bash
export DAUM_EMAIL="you@daum.net"
export DAUM_APP_PASSWORD="YOUR_APP_PASSWORD"
```

Add to `~/.secrets`, `~/.zshrc` (macOS/Linux), or `$PROFILE` (Windows PowerShell).

### Priority

Keychain/Credential Manager → Environment Variables

## Troubleshooting

| Symptom | Cause / Fix |
|---------|-------------|
| Setup guide printed at runtime | Credentials not found in either location |
| `AUTHENTICATIONFAILED` | Using regular Kakao password instead of app password |
| `keyring` not found | Run `pip install keyring` or `uv pip install keyring` |
| macOS Keychain prompt | First run may show a dialog — click "Always Allow" |
