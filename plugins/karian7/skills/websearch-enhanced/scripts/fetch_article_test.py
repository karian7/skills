# /// script
# requires-python = ">=3.11"
# dependencies = ["requests", "beautifulsoup4", "lxml"]
# ///
"""fetch_article 순수 함수 단위 테스트. `uv run fetch_article_test.py`"""

from __future__ import annotations

import unittest

from fetch_article import body_chars, needs_browser, should_replace


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


class RenderRequiredHostTest(unittest.TestCase):
    """본문이 iframe 안에 있는 호스트는 정적 글자 수가 많아도 껍데기다."""

    CAFE = "https://cafe.naver.com/dokchi/13132989?art=eyJhbGciOi.payload.sig"

    def test_fat_shell_on_render_required_host_still_needs_browser(self) -> None:
        # 카페 데스크톱은 게시글 없이 8802자를 낸다(2026-09-22 실측). 임계값으로는 못 잡는다.
        self.assertTrue(needs_browser(rendered(8802), url=self.CAFE))

    def test_same_output_without_url_is_treated_as_success(self) -> None:
        self.assertFalse(needs_browser(rendered(8802)))

    def test_ordinary_host_keeps_threshold_rule(self) -> None:
        url = "https://www.etnews.com/20260604000056"
        self.assertFalse(needs_browser(rendered(8802), url=url))
        self.assertTrue(needs_browser(rendered(12), url=url))

    def test_network_error_is_never_retried_even_on_that_host(self) -> None:
        self.assertFalse(needs_browser("[ERR] ConnectionError: boom", url=self.CAFE))

    def test_cafe_without_token_is_not_worth_a_browser(self) -> None:
        # 토큰 없는 카페는 브라우저로도 로그인 페이지만 나온다(실측: 1582자 로그인 폼).
        # 띄워봐야 시간만 쓰고 로그인 화면을 본문으로 착각하게 만든다.
        self.assertFalse(needs_browser(rendered(8802), url="https://cafe.naver.com/dokchi/13132989"))


class ShouldReplaceTest(unittest.TestCase):
    CAFE = "https://cafe.naver.com/dokchi/13132989?art=eyJhbGciOi.payload.sig"
    NEWS = "https://www.etnews.com/20260604000056"

    def test_longer_browser_result_wins(self) -> None:
        self.assertTrue(should_replace(before=4, after=1019, url=self.NEWS))

    def test_shorter_browser_result_loses_on_ordinary_host(self) -> None:
        self.assertFalse(should_replace(before=3000, after=800, url=self.NEWS))

    def test_shorter_browser_result_wins_on_render_required_host(self) -> None:
        # 카페는 껍데기 8802자 > 본문 799자라 길이로는 영영 못 이긴다.
        self.assertTrue(should_replace(before=8802, after=799, url=self.CAFE))

    def test_browser_failure_never_replaces(self) -> None:
        self.assertFalse(should_replace(before=8802, after=None, url=self.CAFE))

    def test_empty_browser_result_never_replaces(self) -> None:
        self.assertFalse(should_replace(before=8802, after=0, url=self.CAFE))


if __name__ == "__main__":
    unittest.main()
