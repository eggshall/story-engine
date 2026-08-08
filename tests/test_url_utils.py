"""测试：url_utils — SSRF 防护校验 (S6)"""
from __future__ import annotations

import socket

import pytest

from story_engine.utils.url_utils import (
    is_loopback_host,
    is_private_host,
    validate_public_http_url,
)


class TestIsLoopbackHost:
    @pytest.mark.parametrize("host", [
        "localhost", "127.0.0.1", "::1", "0:0:0:0:0:0:0:1", "[::1]", "127.0.0.1.",
    ])
    def test_loopback_recognized(self, host):
        assert is_loopback_host(host) is True

    @pytest.mark.parametrize("host", ["example.com", "1.1.1.1", "192.168.1.1", ""])
    def test_non_loopback(self, host):
        assert is_loopback_host(host) is False


class TestIsPrivateHost:
    @pytest.mark.parametrize("host", [
        "10.0.0.1", "192.168.1.1", "172.16.0.9", "169.254.169.254",
        "127.0.0.1", "::1", "0.0.0.0", "224.0.0.1", "240.0.0.1",
    ])
    def test_private_ip(self, host):
        assert is_private_host(host) is True

    def test_integer_ip_treated_unsafe(self):
        assert is_private_host("2130706433") is True

    def test_public_ip(self):
        assert is_private_host("1.1.1.1") is False
        assert is_private_host("8.8.8.8") is False

    def test_public_domain(self, monkeypatch):
        monkeypatch.setattr(
            socket, "getaddrinfo",
            lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0))],
        )
        assert is_private_host("api.example.com") is False

    def test_private_domain_via_dns(self, monkeypatch):
        monkeypatch.setattr(
            socket, "getaddrinfo",
            lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0))],
        )
        assert is_private_host("internal.example.com") is True

    def test_unresolvable_domain_treated_unsafe(self, monkeypatch):
        def boom(*a, **k):
            raise OSError("no such host")
        monkeypatch.setattr(socket, "getaddrinfo", boom)
        assert is_private_host("no-such-host.invalid") is True


class TestValidatePublicHttpUrl:
    def test_public_https_ok(self, monkeypatch):
        monkeypatch.setattr(
            socket, "getaddrinfo",
            lambda *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("1.1.1.1", 0))],
        )
        assert validate_public_http_url("https://api.example.com/v1") == "https://api.example.com/v1"

    def test_rejects_bad_scheme(self):
        for bad in ("file:///etc/passwd", "ftp://example.com/f", "javascript:alert(1)"):
            with pytest.raises(ValueError):
                validate_public_http_url(bad)

    def test_rejects_missing_host(self):
        with pytest.raises(ValueError):
            validate_public_http_url("https://")

    def test_rejects_non_https_public(self):
        with pytest.raises(ValueError):
            validate_public_http_url("http://api.example.com/v1")

    def test_rejects_private_ip_https(self):
        with pytest.raises(ValueError):
            validate_public_http_url("https://10.0.0.5/api")
        with pytest.raises(ValueError):
            validate_public_http_url("https://169.254.169.254/latest/meta-data")

    def test_loopback_rejected_by_default(self):
        with pytest.raises(ValueError):
            validate_public_http_url("https://localhost:11434")

    def test_loopback_allowed_when_flag(self):
        assert validate_public_http_url("https://localhost:11434", allow_loopback=True) == "https://localhost:11434"
        assert validate_public_http_url("http://127.0.0.1:11434", allow_loopback=True) == "http://127.0.0.1:11434"
