# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""수집한 문서 × 확인할 사실 → 커버리지 매트릭스. 조사를 끝내기 전의 마지막 게이트.

같은 사건을 다룬 기사 여러 건을 모아도, 어떤 사실은 특정 매체 한 곳에만 있다.
그 한 곳을 안 열었으면 조사에서 통째로 빠지는데, 빠졌다는 사실 자체를 알 수 없다.
이 스크립트는 확인하려는 사실을 키워드로 주면 어느 문서에 몇 번 나오는지 세어
세 가지로 분류한다.

    MISSING  전 문서 0회 → 아직 도달하지 못한 사실. 검색으로 돌아가야 한다.
    SINGLE   한 문서에만 → 교차 확인 불가. 그 원문을 직접 읽고 쓸지 판단한다.
    CROSS    두 문서 이상 → 교차 확인됨.

2026-09-01 실측 근거: 크래프톤 코파 프로브 조사에서 3축 평가 체계(기술/의도/인지
관리)는 데일리안·머니투데이 2개 매체에만 있었고, 다른 매체 기사만 읽은 경로에서는
키워드 0회 — 어떤 요약기를 써도 나올 수 없는 미도달이었다.

사용:
    uv run coverage.py --docs a.txt b.txt --terms "메타 하네스,3축,원티드"
    uv run coverage.py --docs-dir ./articles --terms-file terms.txt
    uv run coverage.py --docs *.txt --terms "..." --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

for _stream in (sys.stdout, sys.stderr):
    _reconfigure = getattr(_stream, "reconfigure", None)
    if _reconfigure:
        _reconfigure(encoding="utf-8", errors="replace")

# 띄어쓰기·하이픈·가운뎃점만 다른 표기를 같은 것으로 본다. 한국 매체는 같은 대상을
# '코파 프로브' / '코파-프로브' / '코파프로브'로 제각기 쓴다.
LOOSE_NOISE = re.compile(r"[\s\-–—·ㆍ・]+")


def normalize(text: str, *, loose: bool, ignore_case: bool) -> str:
    """macOS는 한글을 NFD로 저장한다. 정규화 없이 세면 매칭이 통째로 틀린다."""
    text = unicodedata.normalize("NFC", text)
    if ignore_case:
        text = text.lower()
    if loose:
        text = LOOSE_NOISE.sub("", text)
    return text


def display_width(text: str) -> int:
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def pad(text: str, width: int) -> str:
    return text + " " * max(0, width - display_width(text))


def collect_documents(args: argparse.Namespace) -> list[Path]:
    paths: list[Path] = [Path(p) for p in (args.docs or [])]
    if args.docs_dir:
        directory = Path(args.docs_dir)
        paths += sorted(p for p in directory.iterdir() if p.suffix in (".txt", ".md", ".html"))
    return [p for p in paths if p.is_file()]


def collect_terms(args: argparse.Namespace) -> list[str]:
    terms: list[str] = []
    if args.terms:
        terms += [t.strip() for t in args.terms.split(",")]
    if args.terms_file:
        terms += [line.strip() for line in Path(args.terms_file).read_text(encoding="utf-8").splitlines()]
    return [t for t in terms if t and not t.startswith("#")]


def main() -> int:
    parser = argparse.ArgumentParser(description="문서 × 사실 커버리지 매트릭스")
    parser.add_argument("--docs", nargs="*", help="문서 파일 (여러 개, glob 확장 가능)")
    parser.add_argument("--docs-dir", help="디렉토리 안의 .txt/.md/.html 전부")
    parser.add_argument("--terms", help="확인할 사실 키워드, 쉼표 구분")
    parser.add_argument("--terms-file", help="키워드 파일 (한 줄에 하나, # 주석 허용)")
    parser.add_argument("--strict", action="store_true", help="띄어쓰기·하이픈 차이를 구별한다")
    parser.add_argument("--case-sensitive", action="store_true", help="대소문자를 구별한다")
    parser.add_argument("--json", action="store_true", help="JSON으로 출력")
    args = parser.parse_args()

    documents = collect_documents(args)
    terms = collect_terms(args)
    if not documents:
        print("[ERR] 문서가 없다. --docs 또는 --docs-dir 확인.", file=sys.stderr)
        return 2
    if not terms:
        print("[ERR] 키워드가 없다. --terms 또는 --terms-file 확인.", file=sys.stderr)
        return 2

    loose, ignore_case = not args.strict, not args.case_sensitive
    bodies = [
        normalize(p.read_text(encoding="utf-8", errors="ignore"), loose=loose, ignore_case=ignore_case)
        for p in documents
    ]
    labels = [f"D{i}" for i in range(1, len(documents) + 1)]

    rows: list[dict[str, object]] = []
    for term in terms:
        needle = normalize(term, loose=loose, ignore_case=ignore_case)
        counts = [body.count(needle) for body in bodies]
        hits = sum(1 for c in counts if c)
        status = "MISSING" if hits == 0 else ("SINGLE" if hits == 1 else f"CROSS({hits})")
        sources = [labels[i] for i, c in enumerate(counts) if c]
        rows.append({"term": term, "counts": counts, "status": status, "sources": sources})

    if args.json:
        payload = {
            "documents": [{"label": l, "path": str(p)} for l, p in zip(labels, documents)],
            "rows": rows,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0

    term_width = max(display_width(str(r["term"])) for r in rows)
    term_width = max(term_width, display_width("사실"))
    header = pad("사실", term_width) + "  " + "  ".join(f"{l:>3}" for l in labels) + "   상태"
    print(header)
    print("-" * display_width(header))
    for row in rows:
        cells = "  ".join(f"{c:>3}" for c in row["counts"])
        print(f"{pad(str(row['term']), term_width)}  {cells}   {row['status']}")

    print("\n문서:")
    for label, path in zip(labels, documents):
        print(f"  {label}  {unicodedata.normalize('NFC', str(path))}")

    missing = [str(r["term"]) for r in rows if r["status"] == "MISSING"]
    single = [str(r["term"]) for r in rows if r["status"] == "SINGLE"]
    print()
    if missing:
        print(f"⚠ MISSING {len(missing)}건 — 아직 도달 못 한 사실. 검색 단계로 돌아가라:")
        print("   " + ", ".join(missing))
    if single:
        print(f"· SINGLE {len(single)}건 — 단일 출처. 그 원문을 직접 읽고 채택 여부를 판단하라:")
        print("   " + ", ".join(single))
    if not missing and not single:
        print("✓ 전 항목 교차 확인됨.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
