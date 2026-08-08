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
    "http://10.0.0.5/",
    "http://172.16.0.9/",
    "http://2130706433/",
    "https://localhost:11434/",
    "http://api.example.com/",  # 非 https 公网地址也被拒
])
def test_fetch_page_content_rejects_unsafe_urls(bad):
    assert asyncio.run(fetch_page_content(bad)) == ""


def test_fetch_page_content_accepts_public_https(monkeypatch):
    """公网 https 地址放行，正常抓取内容"""
    import socket

    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0))],
    )

    async def mock_get(client, url, **kwargs):
        from types import SimpleNamespace
        return SimpleNamespace(
            text="<html><body><p>这是一段足够长的正文内容，用于验证网页正文提取流程的正常工作。</p>"
                 "<nav>导航</nav></body></html>",
            raise_for_status=lambda: None,
        )

    monkeypatch.setattr("story_engine.tools.web_search.httpx.AsyncClient.get", mock_get)
    out = asyncio.run(fetch_page_content("https://example.com/article"))
    assert "这是一段足够长的正文内容" in out
    assert "导航" not in out


def test_fetch_page_content_network_error_returns_empty(monkeypatch):
    """网络异常返回空字符串"""
    async def mock_get(client, url, **kwargs):
        raise ConnectionError("boom")

    monkeypatch.setattr("story_engine.tools.web_search.httpx.AsyncClient.get", mock_get)
    assert asyncio.run(fetch_page_content("https://example.com/x")) == ""
