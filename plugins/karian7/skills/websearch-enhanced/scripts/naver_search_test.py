# /// script
# requires-python = ">=3.11"
# dependencies = ["requests"]
# ///
"""naver_search 순수 함수 단위 테스트. `uv run naver_search_test.py`"""

from __future__ import annotations

import unittest

from naver_search import is_skippable, session_name, snippet_path


class SessionNameTest(unittest.TestCase):
    def test_explicit_name_wins(self) -> None:
        self.assertEqual(session_name("my-own", claude_session="abc"), "my-own")

    def test_derives_from_claude_session(self) -> None:
        self.assertEqual(session_name(None, claude_session="abc123"), "naver-search-abc123")

    def test_two_claude_sessions_do_not_collide(self) -> None:
        self.assertNotEqual(
            session_name(None, claude_session="aaa"),
            session_name(None, claude_session="bbb"),
        )

    def test_without_claude_session_falls_back_to_process(self) -> None:
        name = session_name(None, claude_session=None, pid=4242)
        self.assertEqual(name, "naver-search-pid4242")

    def test_blank_claude_session_is_treated_as_missing(self) -> None:
        self.assertEqual(session_name(None, claude_session="", pid=7), "naver-search-pid7")


class SnippetPathTest(unittest.TestCase):
    def test_news_uses_news_extractor(self) -> None:
        self.assertEqual(snippet_path("news").name, "naver_serp.js")

    def test_web_uses_web_extractor(self) -> None:
        self.assertEqual(snippet_path("web").name, "naver_serp_web.js")

    def test_unverified_verticals_reuse_web_extractor(self) -> None:
        # blog·view 는 웹문서 탭과 마크업이 가까워 뉴스 추출기로는 0건이 나온다.
        self.assertEqual(snippet_path("blog").name, "naver_serp_web.js")
        self.assertEqual(snippet_path("view").name, "naver_serp_web.js")

    def test_both_extractors_exist_on_disk(self) -> None:
        self.assertTrue(snippet_path("news").exists())
        self.assertTrue(snippet_path("web").exists())


class SkippableHostTest(unittest.TestCase):
    """네이버 자체 내비게이션만 버리고, 콘텐츠 호스트는 검색 결과로 남긴다."""

    def test_navigation_hosts_are_skipped(self) -> None:
        for url in (
            "https://search.naver.com/search.naver?query=x",
            "https://nid.naver.com/nidlogin.login",
            "https://keep.naver.com/",
            "https://m.notify.naver.com/?from=pcmain",
            "https://help.naver.com/service/5627",
            "https://www.naver.com/more.html",
        ):
            with self.subTest(url=url):
                self.assertTrue(is_skippable(url))

    def test_cafe_result_is_kept(self) -> None:
        # 카페 버티컬의 결과 자체다. 버리면 --where article 이 항상 0건이 된다.
        self.assertFalse(is_skippable("https://cafe.naver.com/dokchi/13132989?art=eyJhbGciOi.p.s"))

    def test_blog_and_post_results_are_kept(self) -> None:
        self.assertFalse(is_skippable("https://blog.naver.com/spartaclub/223966332768"))
        self.assertFalse(is_skippable("https://m.blog.naver.com/spartaclub/223966332768"))
        self.assertFalse(is_skippable("https://post.naver.com/viewer/postView.naver?volumeNo=1"))

    def test_naver_news_article_is_kept(self) -> None:
        self.assertFalse(is_skippable("https://n.news.naver.com/mnews/article/001/0001"))

    def test_shortener_and_shopping_are_skipped(self) -> None:
        self.assertTrue(is_skippable("https://naver.me/abcdefg"))
        self.assertTrue(is_skippable("https://malls.example.com/item"))

    def test_external_site_is_kept(self) -> None:
        self.assertFalse(is_skippable("https://www.etnews.com/20260604000056"))


class ArticleVerticalTest(unittest.TestCase):
    def test_article_vertical_uses_web_extractor(self) -> None:
        self.assertEqual(snippet_path("article").name, "naver_serp_web.js")


if __name__ == "__main__":
    unittest.main()
