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
    def test_naver_cafe_is_login_walled(self) -> None:
        self.assertTrue(is_login_walled("https://cafe.naver.com/steamindiegame/12345"))

    def test_plain_news_site_is_not(self) -> None:
        self.assertFalse(is_login_walled("https://www.etnews.com/20260604000056"))


if __name__ == "__main__":
    unittest.main()
