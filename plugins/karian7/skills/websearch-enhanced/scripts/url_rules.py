# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""URL 정규화 규칙 — 정적 수집이 빈손으로 끝나는 주소를 읽히는 주소로 바꾼다.

브라우저를 띄우기 전에 먼저 적용한다. 브라우저 폴백은 비싸고 느리므로, URL만
바꿔서 해결되는 건은 여기서 끝낸다.

실측(2026-09-22):
    blog.naver.com/spartaclub/223966332768    → CHARS: 0
    m.blog.naver.com/spartaclub/223966332768  → CHARS: 3334

데스크톱 네이버 블로그는 본문을 iframe(`#mainFrame`)에 넣기 때문에 상위 문서에는
본문이 없다. 모바일 주소는 같은 글을 단일 문서로 낸다.
"""

from __future__ import annotations

import re
import urllib.parse

# blog.naver.com/{blogId}/{logNo} — logNo는 숫자만
RE_BLOG_PATH = re.compile(r"^/(?P<blog_id>[^/]+)/(?P<log_no>\d+)/?$")

# 로그인 없이는 본문이 나오지 않는 호스트. 브라우저 폴백도 무의미하므로 미리 건너뛴다.
RE_LOGIN_WALLED = re.compile(r"(^|\.)cafe\.naver\.com$")


def canonical_url(url: str) -> str:
    """정적 수집이 통하는 형태로 URL을 바꾼다. 해당 없으면 그대로 돌려준다."""
    parts = urllib.parse.urlsplit(url)
    if parts.fragment:
        parts = parts._replace(fragment="")
    if parts.netloc.lower() == "blog.naver.com":
        parts = _naver_blog_to_mobile(parts)
    return urllib.parse.urlunsplit(parts)


def is_login_walled(url: str) -> bool:
    """로그인 세션 없이는 본문을 못 읽는 주소인가."""
    return bool(RE_LOGIN_WALLED.search(urllib.parse.urlsplit(url).netloc.lower()))


def _naver_blog_to_mobile(parts: urllib.parse.SplitResult) -> urllib.parse.SplitResult:
    """데스크톱 네이버 블로그 주소를 모바일 주소로. 글 번호를 못 찾으면 그대로 둔다."""
    matched = RE_BLOG_PATH.match(parts.path)
    if matched:
        blog_id, log_no = matched["blog_id"], matched["log_no"]
    else:
        query = urllib.parse.parse_qs(parts.query)
        blog_id = (query.get("blogId") or [""])[0]
        log_no = (query.get("logNo") or [""])[0]
        if not (blog_id and log_no.isdigit()):
            return parts
    return parts._replace(netloc="m.blog.naver.com", path=f"/{blog_id}/{log_no}", query="")
