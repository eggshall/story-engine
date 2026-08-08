"""URL 安全校验 — 防 SSRF（内网/链路本地/云元数据地址阻断）"""

from __future__ import annotations

import ipaddress
import socket
from ipaddress import IPv4Address, IPv6Address
from typing import Union
from urllib.parse import urlparse


def _parse_host(host: str) -> str:
    """去掉 IPv6 方括号与末尾点。"""
    host = host.strip().rstrip(".")
    if host.startswith("[") and host.endswith("]"):
        return host[1:-1]
    return host


def is_loopback_host(host: str) -> bool:
    """是否回环地址/localhost。"""
    h = _parse_host(host).lower()
    if h in ("localhost", "::1", "127.0.0.1", "0:0:0:0:0:0:0:1"):
        return True
    try:
        return ipaddress.ip_address(h).is_loopback
    except ValueError:
        return False


def is_private_host(host: str) -> bool:
    """判断 host 是否为私网/保留/链路本地/组播地址（含 DNS 解析结果）。"""
    h = _parse_host(host)
    try:
        ip = ipaddress.ip_address(h)
        return _is_unsafe_ip(ip)
    except ValueError:
        pass
    # 纯数字形式的整数 IP（如 2130706433）视为可疑
    if h.isdigit():
        return True
    # 域名 → 解析所有记录逐一检查
    try:
        infos = socket.getaddrinfo(h, None)
    except OSError:
        return True  # 解析失败按不安全处理
    return any(_is_unsafe_ip(ipaddress.ip_address(info[4][0])) for info in infos)


def _is_unsafe_ip(ip: Union[IPv4Address, IPv6Address]) -> bool:
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def validate_public_http_url(url: str, allow_loopback: bool = False) -> str:
    """校验 URL 为 http/https 且非内网地址，非法抛 ValueError。

    allow_loopback=True 时允许 http(s)://localhost/127.x（本地模型等场景）。
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError(f"不支持的协议: {parsed.scheme!r}")
    if not parsed.hostname:
        raise ValueError("URL 缺少主机名")
    host = _parse_host(parsed.hostname)
    if allow_loopback and is_loopback_host(host):
        return url
    if not parsed.scheme == "https":
        raise ValueError("非本机 base_url 必须使用 https://")
    if is_private_host(host):
        raise ValueError(f"内网地址不允许: {host}")
    return url
