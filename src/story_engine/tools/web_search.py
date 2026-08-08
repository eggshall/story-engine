"""联网搜索工具 — 多引擎支持的中文互联网信息检索

支持的搜索引擎：
- Bing CN (cn.bing.com) — 主力，结构干净，无需验证
- Bing Intl (www.bing.com) — VPN 开启时使用
"""
from __future__ import annotations

import html
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from urllib.parse import quote_plus

import httpx

from story_engine.utils.url_utils import validate_public_http_url

logger = logging.getLogger("story_engine.search")


@dataclass
class SearchResult:
    title: str
    snippet: str
    url: str
    source: str = ""  # 来源引擎: bing / so / sogou


@dataclass
class SearchResponse:
    query: str
    results: List[SearchResult] = field(default_factory=list)
    summary: str = ""
    engine_used: str = ""
    extracted_pages: List[str] = field(default_factory=list)


# ── HTML 工具 ────────────────────────────────

def _clean_html(raw: str) -> str:
    """清理 HTML 标签和实体"""
    text = re.sub(r'<[^>]+>', ' ', raw)
    text = html.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def _clean_url(raw: str) -> str:
    """去除 URL 两侧的引号与空白字符"""
    raw = raw.strip().strip('"').strip("'")
    return raw


_MOBILE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Linux; Android 13) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Mobile Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}


# ── Bing CN (cn.bing.com) — 主力 ────────────

async def _search_bing(query: str, max_results: int = 8, vpn_mode: bool = False) -> Tuple[List[SearchResult], bool]:
    """Bing 搜索 — VPN 开启时用国际版，否则用 CN 版"""
    base_url = "https://www.bing.com/search?q={}" if vpn_mode else "https://cn.bing.com/search?q={}"
    url = base_url.format(quote_plus(query))
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=10, read=15, write=10, pool=10),
            follow_redirects=True,
        ) as client:
            resp = await client.get(url, headers=_MOBILE_HEADERS)
            resp.raise_for_status()
            html_text = resp.text
    except Exception:
        return [], False

    results: List[SearchResult] = []

    # Bing 的结果在 <li class="b_algo">
    # 使用 findall 而不是 split 来正确定位结果块
    blocks = re.findall(r'<li[^>]*class="[^"]*b_algo[^"]*"[^>]*>(.*?)</li>', html_text, re.DOTALL | re.IGNORECASE)
    if not blocks:
        return [], True

    for raw_block in blocks:
        if len(results) >= max_results:
            break

        # 跳过含 CSS link 的假块（Bing 在 <head> 内嵌了带有 b_algo 的 CSS）
        if '<link' in raw_block[:200] and '<h2' not in raw_block[:200]:
            continue

        # 提取所有非 Bing/非广告的真实链接
        all_links = re.findall(
            r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            raw_block, re.DOTALL,
        )

        # 过滤：排除 bing.com / microsoft.com
        candidates = []
        for href, title_html in all_links:
            if 'bing.com' in href or 'microsoft.com' in href:
                continue
            title = _clean_html(title_html)
            title = re.sub(r'\s+', ' ', title).strip()
            if not title or len(title) < 3:
                continue
            # 面包屑导航特征：标题包含 URL（含 http/https/域名）
            is_breadcrumb = bool(re.search(r'(https?://|\.com|\.cn|\.org)', title, re.I))
            candidates.append((href, title, len(title), is_breadcrumb))

        if not candidates:
            continue

        # 优先选非面包屑的（真实标题），如果没有则选最长的
        real_titles = [c for c in candidates if not c[3]]
        chosen = real_titles[0] if real_titles else candidates[0]
        # 如果有多个真实标题，取最长的
        if real_titles:
            real_titles.sort(key=lambda x: -x[2])
            chosen = real_titles[0]
        else:
            candidates.sort(key=lambda x: -x[2])
            chosen = candidates[0]

        url_raw = chosen[0]
        title = chosen[1]

        # 跳过广告
        if re.search(
            r'class="(?:ad\b|ads\b|advertisement|advert|promotion|sponsored)"|data-ad-|adsbygoogle',
            raw_block, re.I,
        ):
            if len(results) > 0:
                continue

        # 提取摘要 (Bing 用 <p> 标签)
        snippet = ""
        p_match = re.search(r'<p[^>]*class="[^"]*"[^>]*>(.*?)</p>', raw_block, re.DOTALL)
        if p_match:
            snippet = _clean_html(p_match.group(1))
        if not snippet:
            p_match = re.search(r'<p[^>]*>(.*?)</p>', raw_block, re.DOTALL)
            if p_match:
                snippet = _clean_html(p_match.group(1))

        results.append(SearchResult(
            title=title,
            snippet=snippet,
            url=_clean_url(url_raw),
            source="bing",
        ))

    return results, True


# ── 网页内容提取 ─────────────────────────────

_CONTENT_EXCLUDE_PATTERNS = re.compile(
    r'<(script|style|nav|footer|header|aside|noscript)[^>]*>.*?</\1>',
    re.DOTALL | re.IGNORECASE,
)


async def fetch_page_content(url: str, max_chars: int = 2000) -> str:
    """抓取网页正文内容，剔除导航/脚本/广告等噪音

    返回纯文本，最多 max_chars 字符。失败返回空字符串。
    """
    # SSRF 防护：仅允许 http/https 公网地址
    try:
        validate_public_http_url(url)
    except ValueError:
        logger.warning("内容提取: 非法 URL 被拒绝: %s", url[:100])
        return ""
    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(connect=5, read=8, write=5, pool=5),
            follow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 Chrome/125.0.0.0 Safari/537.36"
                ),
            },
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            html = resp.text
    except Exception:
        return ""

    # 剔除无意义的块
    html = _CONTENT_EXCLUDE_PATTERNS.sub(' ', html)

    # 提取所有文本
    text = re.sub(r'<[^>]+>', '\n', html)
    text = _clean_html(text)
    # 清理空行和空白
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    # 过滤过短的行（导航/按钮文字）
    lines = [line for line in lines if len(line) > 15]
    content = '\n'.join(lines)

    # 截取
    if len(content) > max_chars:
        content = content[:max_chars] + '\n…[内容截断]'

    return content


# ── VPN 自动检测 ─────────────────────────────

_VPN_CHECK_PORT = 7890
_vpn_cache: tuple[bool, float] | None = None  # (result, timestamp)


async def _is_vpn_active() -> bool:
    """检测 VPN/代理是否开启

    检测顺序：
    1. WSL 内本地 127.0.0.1:7890（原生 Linux 代理）
    2. Windows 宿主机网关 IP:7890（Clash 在 Windows 上运行）

    结果缓存 60 秒。
    """
    global _vpn_cache
    now = __import__('time').time()
    if _vpn_cache and (now - _vpn_cache[1]) < 60:
        return _vpn_cache[0]

    # 候选检测地址
    candidates = ['127.0.0.1']
    try:
        import subprocess
        result = subprocess.run(
            ['ip', 'route'], capture_output=True, text=True, timeout=3,
        )
        for line in result.stdout.splitlines():
            if line.startswith('default'):
                parts = line.split()
                if len(parts) >= 3:
                    candidates.append(parts[2])  # gateway IP
    except Exception:
        pass

    import asyncio
    for host in candidates:
        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, _VPN_CHECK_PORT),
                timeout=1.5,
            )
            writer.close()
            await writer.wait_closed()
            _vpn_cache = (True, now)
            logger.info("VPN检测: 已开启 (%s:%d)", host, _VPN_CHECK_PORT)
            return True
        except Exception:
            continue

    _vpn_cache = (False, now)
    logger.debug("VPN检测: 未开启")
    return False


# ── 主入口 ───────────────────────────────────

# 引擎表（去重，按名称过滤时先排序去重，避免重复请求）
_SEARCH_ENGINES = [
    ("bing", _search_bing),
]


async def search_web(
    query: str,
    max_results: int = 8,
    engines: Optional[List[str]] = None,
    site: str = "",
    extract_content: bool = False,
    max_extract: int = 2,
) -> SearchResponse:
    """搜索互联网，返回结构化结果

    参数:
        query: 搜索关键词
        max_results: 最大返回结果数
        engines: 使用的搜索引擎列表（覆盖自动检测）
        site: 限定站点，如 "zhihu.com" → 自动添加 site:zhihu.com

    VPN 自动检测：
        - 检测到 127.0.0.1:7890 开启 → 国际版 Bing
        - 未检测到 → Bing CN
        - 传 engines 参数时跳过检测，使用指定的引擎
    """
    # 确定引擎列表：去重 + 拼接前过滤
    if engines is None:
        vpn_on = await _is_vpn_active()
        engine_list = list(_SEARCH_ENGINES)
    else:
        vpn_on = False
        wanted = set(engines)
        engine_list = [
            (name, fn) for name, fn in _SEARCH_ENGINES
            if name in wanted
        ]

    # 如果指定了站点，追加到查询
    full_query = f"site:{site} {query}" if site else query

    all_results: List[SearchResult] = []
    seen_urls: set[str] = set()
    engine_used = ""

    for name, fn in engine_list:
        if name == "bing":
            results, ok = await fn(full_query, max_results=max_results * 2, vpn_mode=vpn_on)
        else:
            results, ok = await fn(full_query, max_results=max_results * 2)
        if not ok:
            continue
        engine_used = name if not engine_used else f"{engine_used}+{name}"
        for r in results:
            key = r.url.split("?")[0]  # 去 query 参数去重
            if key not in seen_urls:
                seen_urls.add(key)
                all_results.append(r)
        if len(all_results) >= max_results:
            break

    # 截取并排序
    final = all_results[:max_results]

    # 构建摘要
    summary = _build_summary(full_query, final)

    # ── 网页内容提取 ──
    extracted_pages: List[str] = []
    if extract_content and final:
        to_fetch = final[:max_extract]
        for r in to_fetch:
            content = await fetch_page_content(r.url)
            if content:
                extracted_pages.append(
                    f"【{r.title}】({r.url})\n{content}\n"
                )
                logger.info("内容提取: %s (%d chars)", r.title[:40], len(content))
            else:
                logger.debug("内容提取失败: %s", r.url)

    # ── 日志：搜索关键信息 ──
    logger.info(
        "搜索 | query=%s engine=%s results=%d",
        query, engine_used or "none", len(final),
    )
    if final:
        logger.info(
            "搜索结果 | 1.%s  2.%s  3.%s",
            final[0].title[:40] if len(final) > 0 else "",
            final[1].title[:40] if len(final) > 1 else "",
            final[2].title[:40] if len(final) > 2 else "",
        )
    else:
        logger.warning("搜索无结果 | query=%s engine=%s", query, engine_used or "none")

    return SearchResponse(
        query=full_query,
        results=final,
        summary=summary,
        engine_used=engine_used,
        extracted_pages=extracted_pages,
    )


def _build_summary(query: str, results: List[SearchResult]) -> str:
    """将搜索结果格式化为模型可读的上下文"""
    if not results:
        return f"搜索「{query}」未找到相关结果"

    lines = [f"以下是关于「{query}」的联网搜索结果（来自 {results[0].source if results else '网络'}）：\n"]
    for i, r in enumerate(results, 1):
        lines.append(f"{i}. {r.title}")
        if r.snippet:
            lines.append(f"   {r.snippet[:200]}")
        lines.append("")
    return "\n".join(lines)


def format_search_context(response: SearchResponse) -> str:
    """将搜索结果格式化为注入模型的上下文"""
    if not response.results:
        return ""
    parts = [
        "[联网搜索结果]",
        f"用户查询: {response.query}\n",
        response.summary,
    ]
    # 添加网页全文提取
    if response.extracted_pages:
        parts.append("--- 以下为搜索到的网页正文内容 ---\n")
        parts.extend(response.extracted_pages)
    parts.append(
        "请基于以上搜索结果回答用户的问题。引用来源时标注序号。"
        "如果搜索结果不足以回答，请如实说明。"
    )
    return "\n".join(parts)
