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

# 네이버 카페. 본문이 로그인 뒤에 있지만 검색 유입 토큰이 붙은 링크는 예외다.
RE_CAFE = re.compile(r"(^|\.)cafe\.naver\.com$")

# 본문이 iframe·JS 안에 있어 정적 응답의 길이가 본문 유무를 말해주지 않는 호스트.
# 카페 데스크톱 페이지는 게시글 없이도 8802자를 낸다(2026-09-22 실측) — 전부 GNB·메뉴다.
RE_RENDER_REQUIRED = RE_CAFE


def canonical_url(url: str) -> str:
    """정적 수집이 통하는 형태로 URL을 바꾼다. 해당 없으면 그대로 돌려준다."""
    parts = urllib.parse.urlsplit(url)
    if parts.fragment:
        parts = parts._replace(fragment="")
    if parts.netloc.lower() == "blog.naver.com":
        parts = _naver_blog_to_mobile(parts)
    return urllib.parse.urlunsplit(parts)


def is_login_walled(url: str) -> bool:
    """로그인 세션 없이는 본문을 못 읽는 주소인가.

    네이버 카페는 SERP 앵커에 붙는 `art` 토큰(JWT)이 있으면 로그인 없이 열린다.
    결정 요인은 Referer 가 아니라 이 토큰이다 — 2026-09-22 실측:

        requests + 네이버 검색 Referer   8849자 (레퍼러 없을 때와 동일한 껍데기)
        브라우저로 URL 직접 열기          로그인 리디렉트
        새 세션에서 토큰 URL 직접 열기     본문 799자, 리디렉트 없음
    """
    parts = urllib.parse.urlsplit(url)
    if not RE_CAFE.search(parts.netloc.lower()):
        return False
    return not _has_search_token(parts.query)


def needs_rendering(url: str) -> bool:
    """정적 응답 길이로는 본문 유무를 판단할 수 없는 주소인가.

    참이면 글자 수와 무관하게 브라우저로 받아야 한다. 정적 경로가 '성공'처럼 보이는
    뚱뚱한 껍데기를 내놓기 때문이다.
    """
    return bool(RE_RENDER_REQUIRED.search(urllib.parse.urlsplit(url).netloc.lower()))


def _has_search_token(query: str) -> bool:
    """네이버 검색 유입 토큰(`art`)이 값까지 채워져 있는가."""
    return any(value for value in urllib.parse.parse_qs(query).get("art", []))


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
