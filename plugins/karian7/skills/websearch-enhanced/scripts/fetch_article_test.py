# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "beautifulsoup4", "lxml"]
# ///
"""fetch_article 순수 함수 단위 테스트. `uv run fetch_article_test.py`"""

from __future__ import annotations

import unittest

from fetch_article import body_chars, needs_browser


def rendered(chars: int, selector: str = "fallback:body") -> str:
    return f"TITLE: t\nSELECTOR: {selector}\nCHARS: {chars}\n{'-' * 80}\nbody"


class BodyCharsTest(unittest.TestCase):
    def test_reads_chars_header(self) -> None:
        self.assertEqual(body_chars(rendered(3334)), 3334)

    def test_zero_is_zero_not_none(self) -> None:
        self.assertEqual(body_chars(rendered(0)), 0)

    def test_error_output_has_no_char_count(self) -> None:
        self.assertIsNone(body_chars("[ERR] ConnectionError: boom"))


class NeedsBrowserTest(unittest.TestCase):
    def test_empty_body_needs_browser(self) -> None:
        self.assertTrue(needs_browser(rendered(0)))

    def test_thin_body_needs_browser(self) -> None:
        self.assertTrue(needs_browser(rendered(120)))

    def test_full_body_does_not(self) -> None:
        self.assertFalse(needs_browser(rendered(3334)))

    def test_network_error_is_not_retried_in_browser(self) -> None:
        # 연결 자체가 실패한 건은 브라우저로 바꿔도 같은 결과다.
        self.assertFalse(needs_browser("[ERR] ConnectionError: boom"))

    def test_matched_selector_with_short_text_is_accepted(self) -> None:
        # 컨테이너를 찾았는데 짧으면 그게 본문이다(단신 기사).
        self.assertFalse(needs_browser(rendered(120, selector="#dic_area")))


if __name__ == "__main__":
    unittest.main()
