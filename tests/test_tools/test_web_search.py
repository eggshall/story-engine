"""测试：web_search fetch_page_content SSRF 防护"""

import asyncio

import pytest

from story_engine.tools.web_search import fetch_page_content


@pytest.mark.parametrize("bad", [
    "http://169.254.169.254/latest/meta-data",
    "file:///etc/passwd",
    "http://127.0.0.1:8080",
    "ftp://example.com/file",
    "http://192.168.1.1/",
    "http://[::1]:8080",
])
def test_fetch_page_content_rejects_unsafe_urls(bad):
    assert asyncio.run(fetch_page_content(bad)) == ""
