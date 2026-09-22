# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "beautifulsoup4", "lxml"]
# ///
"""언론 기사 URL → 본문 텍스트. SERP 스니펫으로 부족할 때 원문을 읽는 단계.

여러 URL을 병렬로 받아 매체별 본문 컨테이너를 찾고, 실패하면 페이지 전체에서
기사 뒤에 붙는 추천·랭킹 블록을 잘라낸다. 이 절단이 없으면 컨테이너 셀렉터가
안 맞는 매체에서 '많이 본 뉴스'·'함께 보면 좋은 기사' 수백 줄이 그대로 딸려와
읽을 값어치가 있는 본문을 밀어낸다(2026-09-01 실측: 아시아경제에서 본문 30줄
대비 노이즈 80줄+).

사용:
    uv run fetch_article.py URL [URL ...]
    uv run fetch_article.py --chars 4000 URL
    uv run fetch_article.py --out-dir ./articles URL1 URL2
    uv run fetch_article.py --raw https://example.com/product   # 공식 사이트·기업 뉴스룸

`--raw`는 언론사 CMS 셀렉터를 건너뛰고 페이지 전체 텍스트를 뽑는다. 기업 공식
사이트·제품 랜딩·뉴스룸은 BODY_SELECTORS에 걸리지 않아 기본 모드에서 fallback으로
떨어지는데, 이런 1차 소스는 보도에 없는 제품 구조·일정·조건을 담고 있어 놓치면
조사가 통째로 언론 보도 사본이 된다.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from naver_search import find_agent_browser, run, session_name
from url_rules import canonical_url, is_login_walled

PAGE_TEXT_JS = Path(__file__).resolve().parent / "page_text.js"

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure:
        _reconfigure(encoding="utf-8", errors="replace")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)

# 한국 언론사 CMS는 몇 개 솔루션으로 수렴한다. 앞쪽이 더 구체적인 셀렉터다.
BODY_SELECTORS = [
    "#article-view-content-div",   # 뉴스팜 계열(지역·전문지 다수)
    "#dic_area", "#newsct_article",  # 네이버 뉴스
    "#articleBody", "#article_body", "#article-body", "#articeBody",
    ".article_body", ".article-body", ".news-contents", ".art_txt",
    ".news_cnt_detail_wrap",
    "#textBody", "#CmAdContent", ".view_con", ".articleView",
    "article",
]

# 본문 뒤에 붙는 추천·랭킹 블록의 시작 마커. 등장 지점부터 뒤를 버린다.
CUT_MARKERS = [
    "꼭 봐야 할 주요 뉴스", "함께 보면 좋은 기사", "많이 본 뉴스", "실시간 랭킹뉴스",
    "실시간 인기뉴스", "당신을 위한 추천", "취향저격 맞춤뉴스", "관련기사", "관련 기사",
    "댓글 쓰기", "기사 공유", "구독하기", "놓칠 수 없는 이슈", "오늘의 주요뉴스",
    "핫이슈", "추천 뉴스", "AD",
]

# 기업 공식 사이트·뉴스룸 푸터. --raw 모드에서 본문 뒤에 붙는 회사 정보를 잘라낸다.
SITE_CUT_MARKERS = [
    "개인정보처리방침", "개인정보 처리방침", "이용약관", "사업자등록번호",
    "통신판매업신고", "고객센터", "All rights reserved", "All Rights Reserved",
    "Copyright ©", "COPYRIGHT", "뉴스레터 구독", "문의하기", "Contact us",
]
MIN_BODY_CHARS = 300

# 이 밑이면 정적 수집이 껍데기만 받아온 것으로 본다(JS 렌더링·iframe·봇 차단).
THIN_BODY_CHARS = 300

RE_CHARS_HEADER = re.compile(r"^CHARS: (\d+)$", re.M)
RE_SELECTOR_HEADER = re.compile(r"^SELECTOR: (.+)$", re.M)


def body_chars(rendered: str) -> int | None:
    """extract() 출력 머리의 CHARS 값. 오류 출력이면 None."""
    matched = RE_CHARS_HEADER.search(rendered)
    return int(matched[1]) if matched else None


def needs_browser(rendered: str) -> bool:
    """정적 수집이 실패했으니 브라우저로 다시 받아야 하는가.

    네트워크 오류는 브라우저로 바꿔도 같은 결과라 재시도하지 않는다. 매체 CMS
    컨테이너를 찾은 건은 짧아도 그게 본문이다(단신). 컨테이너를 못 찾았는데
    본문까지 얇으면 껍데기를 받은 것이다 — 데스크톱 네이버 블로그가 전형적이다
    (2026-09-22 실측: CHARS 0).
    """
    chars = body_chars(rendered)
    if chars is None:
        return False
    selector = RE_SELECTOR_HEADER.search(rendered)
    if selector and not selector[1].startswith(("fallback:", "raw:")):
        return False
    return chars < THIN_BODY_CHARS


def strip_boilerplate(text: str, markers: list[str] = CUT_MARKERS) -> str:
    """추천 블록 마커가 나오는 첫 지점에서 자른다.

    마커가 본문 앞부분(전체의 30% 이전)에 나오면 그건 본문이 아니라 페이지 상단
    내비게이션일 가능성이 크므로 무시한다 — 자르면 본문까지 통째로 날아간다.
    """
    cut = len(text)
    for marker in markers:
        position = text.find(marker)
        if position > len(text) * 0.3:
            cut = min(cut, position)
    return text[:cut].rstrip()


def extract(url: str, limit: int, raw: bool = False) -> str:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"},
            timeout=25,
        )
        response.encoding = response.apparent_encoding or response.encoding
    except requests.RequestException as exc:
        return f"[ERR] {type(exc).__name__}: {str(exc)[:200]}"

    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup(["script", "style", "nav", "header", "footer", "aside", "iframe", "form"]):
        tag.decompose()

    title = soup.title.get_text(strip=True) if soup.title else ""
    node, matched = None, "fallback:body"
    if raw:
        matched = "raw:whole-page"
    else:
        for selector in BODY_SELECTORS:
            candidate = soup.select_one(selector)
            if candidate and len(candidate.get_text(strip=True)) > MIN_BODY_CHARS:
                node, matched = candidate, selector
                break

    text = (node or soup.body or soup).get_text("\n", strip=True)
    text = unicodedata.normalize("NFC", re.sub(r"\n{2,}", "\n", text))
    # 컨테이너를 찾은 경우에는 절단하지 않는다. 본문 중간에 추천 블록을 끼워 넣는
    # 매체(아시아경제 등)에서 마커 이후의 진짜 본문이 통째로 날아간다
    # (2026-09-01 실측: 4244자 → 1758자, 본부장 인용 소실).
    if raw:
        text = strip_boilerplate(text, CUT_MARKERS + SITE_CUT_MARKERS)
    elif node is None:
        text = strip_boilerplate(text)

    header = f"TITLE: {title}\nSELECTOR: {matched}\nCHARS: {len(text)}"
    return f"{header}\n{'-' * 80}\n{text[:limit]}"


def browser_extract(binary: str, session: str, url: str, limit: int, raw: bool) -> str:
    """agent-browser 로 렌더링된 본문을 받는다. 정적 경로가 실패한 URL 에만 쓴다.

    ⚠️ 브라우저 세션 하나를 공유하므로 **순차로만** 호출한다. 병렬로 부르면
    같은 탭을 서로 다른 URL 로 옮겨 결과가 섞인다.
    """
    if not PAGE_TEXT_JS.exists():
        return f"[ERR] {PAGE_TEXT_JS.name} 없음 — 브라우저 폴백 불가"
    opened = run(binary, session, ["open", url], timeout=60)
    if opened.returncode != 0:
        return f"[ERR] browser open: {opened.stderr.strip()[:200]}"
    run(binary, session, ["wait", "--load", "networkidle"], timeout=30)
    snippet_b64 = base64.b64encode(PAGE_TEXT_JS.read_bytes()).decode("ascii")
    result = run(binary, session, ["eval", "-b", snippet_b64], timeout=60)
    if result.returncode != 0:
        return f"[ERR] browser eval: {result.stderr.strip()[:200]}"
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return f"[ERR] browser JSON 파싱 실패: {result.stdout.strip()[:200]}"

    text = unicodedata.normalize("NFC", re.sub(r"\n{2,}", "\n", str(payload.get("text", ""))))
    text = strip_boilerplate(text, CUT_MARKERS + SITE_CUT_MARKERS) if raw else strip_boilerplate(text)
    header = (f"TITLE: {payload.get('title', '')}\n"
              f"SELECTOR: browser:{payload.get('source', '?')}\n"
              f"CHARS: {len(text)}")
    return f"{header}\n{'-' * 80}\n{text[:limit]}"


def rescue_with_browser(urls: list[str], results: list[str], limit: int, raw: bool,
                        session: str, keep_session: bool) -> None:
    """정적 수집이 얇게 끝난 항목만 골라 브라우저로 다시 받는다. results 를 제자리 수정."""
    targets = [i for i, body in enumerate(results) if needs_browser(body)]
    if not targets:
        return
    binary = find_agent_browser()
    if not binary:
        print(f"[WARN] 정적 수집이 얇은 {len(targets)}건이 있지만 agent-browser 가 없습니다. "
              "`pnpm add -g agent-browser` 로 설치하면 폴백이 생깁니다.", file=sys.stderr)
        return
    print(f"[INFO] 브라우저 폴백 {len(targets)}건 · 세션 {session}", file=sys.stderr)
    try:
        for index in targets:
            rescued = browser_extract(binary, session, urls[index], limit, raw)
            before, after = body_chars(results[index]) or 0, body_chars(rescued)
            if after is not None and after > before:
                results[index] = rescued
                print(f"[INFO] {urls[index][:70]} → {before}자 → {after}자", file=sys.stderr)
            else:
                print(f"[WARN] {urls[index][:70]} → 브라우저도 개선 없음", file=sys.stderr)
    finally:
        if not keep_session:
            run(binary, session, ["close"], timeout=30)


def main() -> int:
    parser = argparse.ArgumentParser(description="기사 URL → 본문 텍스트")
    parser.add_argument("urls", nargs="+", help="기사 URL(여러 개 가능, 병렬 수집)")
    parser.add_argument("--chars", type=int, default=6000, help="기사당 최대 출력 글자 수 (기본 6000)")
    parser.add_argument("--out-dir", help="지정 시 기사별 .txt로 저장하고 stdout에는 경로만 낸다")
    parser.add_argument(
        "--raw",
        action="store_true",
        help="언론사 셀렉터를 건너뛰고 페이지 전체를 뽑는다 (공식 사이트·기업 뉴스룸용)",
    )
    parser.add_argument("--no-browser", action="store_true",
                        help="정적 수집이 실패해도 agent-browser 폴백을 쓰지 않는다")
    parser.add_argument("--keep-session", action="store_true", help="폴백 후 브라우저를 닫지 않는다")
    parser.add_argument("--session", help="agent-browser 세션 이름(병렬 서브에이전트용)")
    args = parser.parse_args()

    urls: list[str] = []
    for raw_url in args.urls:
        fixed = canonical_url(raw_url)
        if fixed != raw_url:
            print(f"[INFO] URL 정규화: {raw_url} → {fixed}", file=sys.stderr)
        if is_login_walled(fixed):
            print(f"[WARN] 로그인 필요 호스트라 본문을 못 읽습니다: {fixed}", file=sys.stderr)
        urls.append(fixed)

    with ThreadPoolExecutor(max_workers=min(8, len(urls))) as pool:
        results = list(pool.map(lambda u: extract(u, args.chars, args.raw), urls))

    if not args.no_browser:
        rescue_with_browser(urls, results, args.chars, args.raw,
                            session_name(args.session, os.environ.get("CLAUDE_CODE_SESSION_ID")),
                            args.keep_session)

    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for index, (url, body) in enumerate(zip(urls, results), 1):
        if out_dir:
            path = out_dir / f"article-{index:02d}.txt"
            path.write_text(f"URL: {url}\n{body}\n", encoding="utf-8")
            print(f"{path}  ← {url}")
        else:
            print("=" * 90)
            print(f"URL: {url}")
            print(body)
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
