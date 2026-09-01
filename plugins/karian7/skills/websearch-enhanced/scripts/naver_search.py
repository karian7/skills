# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""네이버 검색 SERP 수집 — 내장 웹 검색이 놓치는 한국어 자료를 찾는 검색 경로.

키워드별로 네이버 SERP HTML을 정적으로 받아 파싱하고,
{query, title, url, press, date_label, desc} 레코드를 표 또는 JSON으로 낸다.

수집 경로는 2단이다.

1. **requests**(코어) — SERP HTML을 정적으로 받아 파싱한다. 브라우저·Chrome·node
   불필요. 2026-08-20 실측으로 agent-browser 경로와 결과가 동일함을 확인했다
   (54/54건, 56/56건, 134/134건 · title·press·desc 전 항목 일치).
2. **agent-browser**(폴백) — requests가 HTTP 오류를 내거나 전 키워드 0건일 때만
   구동한다. 네이버가 정적 응답을 막거나 마크업이 바뀌었을 때의 안전망이다.
   설치되어 있지 않으면 조용히 건너뛴다.

사용:
    uv run naver_search.py --query "크래프톤 코파 프로브"
    uv run naver_search.py --query "A" --query "B" --pages 3
    uv run naver_search.py --query "정책명" --from 20260101 --to 20260901
    uv run naver_search.py --query "키워드" --format json --out result.json
    uv run naver_search.py --query "키워드" --where blog     # 실험적
"""

from __future__ import annotations

import argparse
import base64
import html as htmllib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unicodedata
import urllib.parse
from pathlib import Path

import requests

SNIPPET_JS = Path(__file__).resolve().parent / "naver_serp.js"
SESSION = "naver-search"

# ⚠️ Windows 기본 인코딩(cp949)에는 기사 제목에 흔한 구분자(‧ ・ ⋅ ･)와 이 스크립트가 쓰는
# 기호(— ⚠)가 없다. 강제하지 않으면 `> out.json` 리다이렉션이 UnicodeEncodeError로 죽는다
# (2026-08-20 실측: 수집 54건 중 U+2D48·U+2027 포함 → cp949 기록 실패).
for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure:
        _reconfigure(encoding="utf-8", errors="replace")

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
REQUEST_INTERVAL = 0.4

FALLBACK_BINS = [
    Path.home() / "Library" / "pnpm" / "agent-browser",
    Path.home() / "Library" / "pnpm" / "bin" / "agent-browser",
    Path.home() / ".local" / "bin" / "agent-browser",
    Path.home() / "AppData" / "Local" / "pnpm" / "agent-browser.cmd",
    Path.home() / "AppData" / "Roaming" / "npm" / "agent-browser.cmd",
]

# SERP 항목 필드. 언론사·시간은 제목보다 앞에 오므로 '제목 직전'을 골라야 한다
# (직후를 고르면 다음 기사의 언론사가 붙는다 — 2026-08-20 실측에서 51건 중 50건 오류).
RE_TITLE = re.compile(r"sds-comps-text-type-headline1[^>]*>(.*?)</span>", re.S)
RE_DESC = re.compile(r"sds-comps-text-type-body1[^>]*>(.*?)</span>", re.S)
RE_PRESS = re.compile(r"sds-comps-profile-info-title-text[^>]*>(.*?)</", re.S)
RE_SUBTEXT = re.compile(r"sds-comps-profile-info-subtext[^>]*>(.*?)</", re.S)
RE_TITLE_ANCHOR = re.compile(r'<a[^>]*data-heatmap-target="\.tit"[^>]*href="([^"]+)"')
RE_ANCHOR_TITLE = re.compile(r'<a[^>]+href="(https?://[^"]+)"[^>]*data-heatmap-target="\.tit"')
# blog·view 버티컬은 .tit 마커가 없다. 제목 직전의 마지막 외부 앵커로 폴백한다.
RE_ANY_ANCHOR = re.compile(r'<a[^>]+href="(https?://[^"]+)"')

RE_DATE_LABEL = re.compile(r"^\d+(?:분|시간|일|주|개월)\s*전$|^\d{4}\.\d{2}\.\d{2}\.?$")
RE_SKIP_HOST = re.compile(
    r"(keep|help|search|nid|note|blog|cafe|shopping|m)\.naver\.com|naver\.me|malls\."
)


def log(msg: str) -> None:
    print(msg, file=sys.stderr)


def resolve_native(path: Path) -> Path:
    """Windows npm 셰임(.cmd/.bat)을 네이티브 exe로 바꾼다.

    ⚠️ 셰임 내용은 `"%~dp0...\\agent-browser-win32-x64.exe" %*` 한 줄인데, `%*`가
    원본 명령줄을 그대로 재전개하므로 cmd.exe가 먼저 파싱한다. 검색 URL의 `&`가
    명령 구분자로 잘려 `&query=...`가 Windows `query.exe`로 실행된다
    (2026-08-14 실측: 전 키워드 0건 + "Invalid parameter(s) QUERY {...}").
    네이티브 exe를 직접 부르면 cmd.exe를 거치지 않아 URL이 온전히 전달된다.
    """
    if path.suffix.lower() not in (".cmd", ".bat"):
        return path
    native = path.parent / "node_modules" / "agent-browser" / "bin" / "agent-browser-win32-x64.exe"
    return native if native.exists() else path


def find_agent_browser() -> str | None:
    found = shutil.which("agent-browser")
    if found:
        return str(resolve_native(Path(found)))
    for candidate in FALLBACK_BINS:
        if candidate.exists():
            return str(resolve_native(candidate))
    return None


def build_url(query: str, where: str, date_from: str | None, date_to: str | None, start: int) -> str:
    params = {"where": where, "query": query}
    if where == "news":
        params["sort"] = "1"  # 최신순
        if date_from and date_to:
            params["nso"] = f"so:dd,p:from{date_from}to{date_to}"
    if start > 1:
        params["start"] = str(start)
    return "https://search.naver.com/search.naver?" + urllib.parse.urlencode(params)


def clean_text(fragment: str) -> str:
    """HTML 조각 → 표시 텍스트. 검색어가 <mark>로 감싸여 오므로 태그를 먼저 벗긴다."""
    text = re.sub(r"<[^>]+>", "", fragment)
    text = htmllib.unescape(text).replace("새 창 열림", "")
    return unicodedata.normalize("NFC", re.sub(r"\s+", " ", text)).strip()


def parse_serp(body: str) -> list[dict]:
    """SERP HTML에서 항목을 뽑는다. 필드는 문서 내 위치로 제목과 짝짓는다."""
    titles = [(m.start(), clean_text(m.group(1))) for m in RE_TITLE.finditer(body)]
    descs = [(m.start(), clean_text(m.group(1))) for m in RE_DESC.finditer(body)]
    presses = [(m.start(), clean_text(m.group(1))) for m in RE_PRESS.finditer(body)]
    subtexts = [(m.start(), clean_text(m.group(1))) for m in RE_SUBTEXT.finditer(body)]

    def anchors_from(pattern: re.Pattern) -> list[tuple[int, str]]:
        return [(m.start(), htmllib.unescape(m.group(1)).split("#")[0]) for m in pattern.finditer(body)]

    marked = sorted(anchors_from(RE_TITLE_ANCHOR) + anchors_from(RE_ANCHOR_TITLE))
    # .tit 마커가 제목 수에 못 미치면(blog·view) 일반 앵커로 보충한다.
    fallback = sorted(a for a in anchors_from(RE_ANY_ANCHOR) if not RE_SKIP_HOST.search(a[1]))
    anchors = marked if len(marked) >= len(titles) else sorted(set(marked + fallback))

    items: list[dict] = []
    seen: set[str] = set()
    for index, (position, title) in enumerate(titles):
        previous = titles[index - 1][0] if index else -1
        url = next((u for p, u in reversed(anchors) if p < position), "")
        if not title or not url or RE_SKIP_HOST.search(url) or url in seen:
            continue
        seen.add(url)
        press = next((v for p, v in reversed(presses) if p < position), "")
        date_label = next(
            (v for p, v in reversed(subtexts) if previous < p < position and RE_DATE_LABEL.match(v)),
            "",
        ) or next((v for p, v in reversed(subtexts) if p < position and RE_DATE_LABEL.match(v)), "")
        desc = next((v for p, v in descs if p > position), "")
        items.append(
            {
                "title": title,
                "url": url,
                "press": press,
                "date_label": date_label,
                "desc": desc[:300],
            }
        )
    return items


def run(binary: str, args: list[str], timeout: int = 90) -> subprocess.CompletedProcess:
    """agent-browser 한 번 호출.

    ⚠️ `capture_output=True`(파이프)를 쓰면 안 된다. agent-browser는 브라우저 세션을
    유지하는 데몬을 뒤에 남기는데, 그 데몬이 파이프의 쓰기 핸들을 상속받아 놓지 않는다.
    CLI 본체가 끝나도 EOF가 오지 않아 communicate()가 무한 대기한다
    (2026-08-14 Windows 실측: 45초 타임아웃 지정에도 180초+ 블록).
    임시파일로 리디렉트하면 파이프가 없으므로 CLI 종료와 함께 즉시 돌아온다.
    """
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        proc = subprocess.run(
            [binary, "--session", SESSION, *args],
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            timeout=timeout,
        )
        out.seek(0)
        err.seek(0)
        return subprocess.CompletedProcess(
            proc.args, proc.returncode,
            out.read().decode("utf-8", "replace"),
            err.read().decode("utf-8", "replace"),
        )


def scrape_with_browser(binary: str, url: str, snippet_b64: str) -> list[dict]:
    opened = run(binary, ["open", url])
    if opened.returncode != 0:
        log(f"[WARN] open 실패: {opened.stderr.strip()[:200]}")
        return []
    run(binary, ["wait", "--load", "networkidle"], timeout=30)
    result = run(binary, ["eval", "-b", snippet_b64])
    if result.returncode != 0:
        log(f"[WARN] eval 실패: {result.stderr.strip()[:200]}")
        return []
    try:
        items = json.loads(result.stdout)
    except json.JSONDecodeError:
        log(f"[WARN] JSON 파싱 실패: {result.stdout.strip()[:200]}")
        return []
    return items if isinstance(items, list) else []


class Collector:
    """키워드 목록을 돌며 항목을 모으고 URL 기준으로 중복을 제거한다."""

    def __init__(self, where: str, date_from: str | None, date_to: str | None, pages: int) -> None:
        self.where = where
        self.date_from = date_from
        self.date_to = date_to
        self.pages = pages
        self.items: list[dict] = []
        self.seen: set[str] = set()

    def add(self, keyword: str, harvested: list[dict]) -> int:
        fresh = 0
        for item in harvested:
            url = item.get("url", "")
            if not url or url in self.seen:
                continue
            self.seen.add(url)
            item["query"] = keyword
            self.items.append(item)
            fresh += 1
        return fresh

    def urls_for(self, keyword: str) -> list[str]:
        return [
            build_url(keyword, self.where, self.date_from, self.date_to, start=page * 10 + 1)
            for page in range(self.pages)
        ]


def collect_with_requests(collector: Collector, keywords: list[str]) -> list[str]:
    """requests 코어. HTTP 오류가 난 키워드 목록을 돌려준다."""
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "ko-KR,ko;q=0.9"})
    failed: list[str] = []
    for keyword in keywords:
        fresh = 0
        for url in collector.urls_for(keyword):
            # 키워드 8개 × 3페이지처럼 연속 요청이 길어지면 간헐적으로 403이 온다
            # (2026-09-01 실측: 24연속 요청 중 1건). 일시적 차단이라 한 번 쉬고
            # 재시도하면 대부분 풀린다.
            response = None
            for attempt in range(2):
                try:
                    response = session.get(url, timeout=25)
                    response.raise_for_status()
                    break
                except requests.RequestException as exc:
                    if attempt == 0:
                        log(f"[WARN] {keyword} 요청 실패({type(exc).__name__}) → 3초 후 재시도")
                        time.sleep(3.0)
                    else:
                        log(f"[WARN] {keyword} 재시도도 실패: {type(exc).__name__} {str(exc)[:120]}")
                        response = None
            if response is None:
                failed.append(keyword)
                break
            fresh += collector.add(keyword, parse_serp(response.text))
            time.sleep(REQUEST_INTERVAL)
        log(f"[INFO] {keyword} → {fresh}건")
    return failed


def collect_with_browser(collector: Collector, keywords: list[str], keep_session: bool) -> bool:
    """agent-browser 폴백. 구동 불가면 False."""
    binary = find_agent_browser()
    if not binary:
        log("[WARN] agent-browser 없음 — 폴백 불가. `pnpm add -g agent-browser`로 설치하면 안전망이 생깁니다.")
        return False
    if not SNIPPET_JS.exists():
        log(f"[WARN] {SNIPPET_JS} 없음 — 폴백 불가")
        return False
    snippet_b64 = base64.b64encode(SNIPPET_JS.read_bytes()).decode("ascii")
    log(f"[INFO] agent-browser 폴백: {binary}")
    try:
        for keyword in keywords:
            fresh = 0
            for url in collector.urls_for(keyword):
                fresh += collector.add(keyword, scrape_with_browser(binary, url, snippet_b64))
            log(f"[INFO] {keyword} → {fresh}건 (browser)")
    finally:
        if not keep_session:
            run(binary, ["close"], timeout=30)
    return True


def render_table(items: list[dict]) -> str:
    """스니펫 훑기용 표. desc까지 보여야 어떤 기사를 열지 판단할 수 있다."""
    lines = []
    for index, item in enumerate(items, 1):
        head = f"{index:3}. [{item.get('date_label') or '-'}] {item.get('press') or '-'} | {item['title']}"
        lines.append(head)
        lines.append(f"     {item['url']}")
        if item.get("desc"):
            lines.append(f"     {item['desc']}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="네이버 검색 SERP 수집")
    parser.add_argument("--query", action="append", required=True, help="검색 키워드(반복 가능)")
    parser.add_argument("--where", default="news", choices=("news", "blog", "view"),
                        help="검색 버티컬. news가 검증된 경로(기본), blog·view는 best-effort")
    parser.add_argument("--from", dest="date_from", help="게시일 시작 YYYYMMDD (news 전용)")
    parser.add_argument("--to", dest="date_to", help="게시일 끝 YYYYMMDD (news 전용)")
    parser.add_argument("--pages", type=int, default=2, help="키워드당 SERP 페이지 수 (기본 2 = 20건)")
    parser.add_argument("--format", choices=("table", "json"), default="table",
                        help="table=사람이 훑는 용(기본), json=후속 처리용")
    parser.add_argument("--out", help="결과를 파일로 저장(지정 시 stdout에는 요약만)")
    parser.add_argument("--engine", choices=("auto", "requests", "browser"), default="auto",
                        help="auto=requests 우선·실패 시 browser 폴백(기본)")
    parser.add_argument("--keep-session", action="store_true", help="수집 후 브라우저를 닫지 않는다")
    args = parser.parse_args()

    if bool(args.date_from) != bool(args.date_to):
        log("[FAIL] --from 과 --to 는 함께 지정해야 합니다.")
        return 2

    collector = Collector(args.where, args.date_from, args.date_to, args.pages)
    window = f"{args.date_from}~{args.date_to}" if args.date_from else "전체 기간"
    log(f"[INFO] where={args.where} · 게시일 {window} · 키워드 {len(args.query)}개 · {args.pages}페이지")

    if args.engine == "browser":
        if not collect_with_browser(collector, args.query, args.keep_session):
            return 2
    else:
        failed = collect_with_requests(collector, args.query)
        # 전 키워드 0건은 마크업 변경 신호다. 개별 HTTP 실패도 폴백 대상이다.
        retry = args.query if not collector.items else failed
        if args.engine == "auto" and retry:
            reason = "전 키워드 0건" if not collector.items else f"요청 실패 {len(failed)}건"
            log(f"[WARN] requests 경로 미수집({reason}) → agent-browser 폴백 시도")
            collect_with_browser(collector, retry, args.keep_session)

    payload = (json.dumps(collector.items, ensure_ascii=False, indent=2)
               if args.format == "json" else render_table(collector.items))
    if args.out:
        Path(args.out).write_text(payload, encoding="utf-8")
        log(f"[DONE] 고유 {len(collector.items)}건 → {args.out}")
    else:
        print(payload)
        log(f"[DONE] 고유 {len(collector.items)}건 수집")
    return 0 if collector.items else 1


if __name__ == "__main__":
    sys.exit(main())
