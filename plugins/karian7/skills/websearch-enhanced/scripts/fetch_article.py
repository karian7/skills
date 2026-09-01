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
import re
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from bs4 import BeautifulSoup

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
    args = parser.parse_args()

    with ThreadPoolExecutor(max_workers=min(8, len(args.urls))) as pool:
        results = list(pool.map(lambda u: extract(u, args.chars, args.raw), args.urls))

    out_dir = Path(args.out_dir) if args.out_dir else None
    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)

    for index, (url, body) in enumerate(zip(args.urls, results), 1):
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
