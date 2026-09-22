# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""url_rules 단위 테스트. `uv run url_rules_test.py`"""

from __future__ import annotations

import unittest

from url_rules import canonical_url, is_login_walled


class CanonicalUrlTest(unittest.TestCase):
    def test_desktop_naver_blog_becomes_mobile(self) -> None:
        self.assertEqual(
            canonical_url("https://blog.naver.com/spartaclub/223966332768"),
            "https://m.blog.naver.com/spartaclub/223966332768",
        )

    def test_postview_query_form_becomes_mobile_path(self) -> None:
        self.assertEqual(
            canonical_url(
                "https://blog.naver.com/PostView.naver?blogId=spartaclub&logNo=223966332768&from=search"
            ),
            "https://m.blog.naver.com/spartaclub/223966332768",
        )

    def test_mobile_naver_blog_is_left_alone(self) -> None:
        url = "https://m.blog.naver.com/spartaclub/223966332768"
        self.assertEqual(canonical_url(url), url)

    def test_blog_root_without_post_id_is_left_alone(self) -> None:
        url = "https://blog.naver.com/spartaclub"
        self.assertEqual(canonical_url(url), url)

    def test_fragment_is_stripped(self) -> None:
        self.assertEqual(
            canonical_url("https://example.com/a/b#section-3"),
            "https://example.com/a/b",
        )

    def test_unrelated_url_is_untouched(self) -> None:
        url = "https://www.mk.co.kr/news/business/12143452"
        self.assertEqual(canonical_url(url), url)

    def test_http_scheme_is_preserved(self) -> None:
        url = "http://www.khrd.co.kr/m/view.php?idx=5057203"
        self.assertEqual(canonical_url(url), url)


class LoginWalledTest(unittest.TestCase):
    def test_bare_cafe_link_is_login_walled(self) -> None:
        self.assertTrue(is_login_walled("https://cafe.naver.com/steamindiegame/12345"))

    def test_mobile_cafe_is_login_walled_too(self) -> None:
        self.assertTrue(is_login_walled("https://m.cafe.naver.com/steamindiegame/12345"))

    def test_cafe_link_with_search_token_is_readable(self) -> None:
        # SERP 앵커에 붙는 art 토큰이 있으면 로그인 없이 열린다
        # (2026-09-22 실측: 새 세션에서 토큰 URL 직접 열기 → 본문 799자, 로그인 리디렉트 없음).
        self.assertFalse(
            is_login_walled("https://cafe.naver.com/dokchi/13132989?art=ZXh0ZXJuYWwt.eyJhbGciOi.gnqk7Zjt")
        )

    def test_empty_art_value_does_not_count(self) -> None:
        self.assertTrue(is_login_walled("https://cafe.naver.com/dokchi/13132989?art="))

    def test_other_query_params_do_not_unlock(self) -> None:
        self.assertTrue(is_login_walled("https://cafe.naver.com/dokchi/13132989?from=search"))

    def test_plain_news_site_is_not(self) -> None:
        self.assertFalse(is_login_walled("https://www.etnews.com/20260604000056"))


if __name__ == "__main__":
    unittest.main()
