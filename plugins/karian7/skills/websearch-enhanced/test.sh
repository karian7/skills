#!/usr/bin/env zsh
# websearch-enhanced self-eval test
# Usage: zsh test.sh
# Prerequisites: uv, 네트워크(search.naver.com 접근)
# Generated: 2026-09-01

set -uo pipefail

SCRIPT_DIR="${0:A:h}/scripts"
TMP_DIR="$(mktemp -d)"
PASS=0; FAIL=0

pass() { echo "  ✅ $1"; PASS=$((PASS + 1)); }
fail() { echo "  ❌ $1"; FAIL=$((FAIL + 1)); }
cleanup() { [ -d "$TMP_DIR" ] && command rm -rf "$TMP_DIR"; }
trap cleanup EXIT

echo "=== websearch-enhanced self-eval ==="
echo ""

# [Test 1] 뉴스 버티컬 검색이 1건 이상 수집한다
echo "[Test 1] news vertical returns items"
if uv run "$SCRIPT_DIR/naver_search.py" --query "고용노동부" --pages 1 \
    --format json --out "$TMP_DIR/news.json" >/dev/null 2>&1 \
    && [ -s "$TMP_DIR/news.json" ]; then
  pass "news search collected >=1 item"
else
  fail "news search collected >=1 item"
fi

# [Test 2] JSON 출력이 유효하고 필수 필드를 가진다
echo "[Test 2] JSON output has required fields"
if python3 -c "
import json, sys
items = json.load(open('$TMP_DIR/news.json'))
assert isinstance(items, list) and items
assert all(i.get('title') and i.get('url') and 'query' in i for i in items)
" 2>/dev/null; then
  pass "JSON valid with title/url/query fields"
else
  fail "JSON valid with title/url/query fields"
fi

# [Test 3] --from 단독 지정은 거부된다
echo "[Test 3] --from without --to is rejected"
uv run "$SCRIPT_DIR/naver_search.py" --query "x" --from 20260101 >/dev/null 2>&1
if [ $? -eq 2 ]; then
  pass "unpaired --from exits 2"
else
  fail "unpaired --from exits 2"
fi

# [Test 4] 웹문서 버티컬(--where web)이 1건 이상 수집한다
echo "[Test 4] web vertical returns items"
if uv run "$SCRIPT_DIR/naver_search.py" --query "kdt ai캠퍼스" --pages 1 \
    --where web --format json --out "$TMP_DIR/web.json" >/dev/null 2>&1 \
    && [ -s "$TMP_DIR/web.json" ]; then
  pass "web search collected >=1 item"
else
  fail "web search collected >=1 item"
fi

echo ""
echo "=== Result: $PASS passed, $FAIL failed ==="
[ $FAIL -eq 0 ] && exit 0 || exit 1
