"""자격증명 로드 — keyring(macOS Keychain / Windows Credential Manager) 우선, 환경변수 폴백."""
from __future__ import annotations

import os
import sys

KEYRING_SERVICE = "naver-mail"
EMAIL_KEY = "email"
PASSWORD_KEY = "app-password"
EMAIL_ENV = "NAVER_EMAIL"
PASSWORD_ENV = "NAVER_APP_PASSWORD"

SETUP_GUIDE = """
✗ Naver Mail IMAP 자격증명을 찾을 수 없습니다.

아래 단계를 따라 설정하세요.

━━ 1단계: 앱 비밀번호 발급 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  https://mail.naver.com/v2/settings/smtp/imap
  ① IMAP 사용 설정 ON
  ② 애플리케이션 비밀번호 생성 후 복사

━━ 2단계: 자격증명 저장 ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  [권장] 키체인/자격증명 저장소:
    python3 -c "
  import keyring
  keyring.set_password('naver-mail', 'email', 'you@naver.com')
  keyring.set_password('naver-mail', 'app-password', '발급받은앱비밀번호')
  "
  ▸ macOS : Keychain에 저장 (별도 인증 없이 자동 로드)
  ▸ Windows: Windows Credential Manager에 저장

  [대안] 환경변수:
    export NAVER_EMAIL="you@naver.com"
    export NAVER_APP_PASSWORD="발급받은앱비밀번호"
    (~ /.secrets 또는 ~/.zshrc / %USERPROFILE%\\Documents\\env.ps1 에 추가)
"""


def load_credentials() -> tuple[str, str] | None:
    """(email, password) 반환. 못 찾으면 None."""
    try:
        import keyring  # type: ignore[import]
        email = keyring.get_password(KEYRING_SERVICE, EMAIL_KEY)
        password = keyring.get_password(KEYRING_SERVICE, PASSWORD_KEY)
        if email and password:
            return email, password
    except Exception:
        pass

    email = os.environ.get(EMAIL_ENV)
    password = os.environ.get(PASSWORD_ENV)
    if email and password:
        return email, password

    return None


def require_credentials() -> tuple[str, str]:
    """자격증명 반환. 없으면 안내 출력 후 sys.exit(2)."""
    result = load_credentials()
    if result:
        return result
    print(SETUP_GUIDE, file=sys.stderr)
    sys.exit(2)
