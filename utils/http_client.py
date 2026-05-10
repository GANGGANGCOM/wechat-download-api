#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
HTTP Client Wrapper
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Dict

logger = logging.getLogger(__name__)

try:
    from curl_cffi.requests import Session as CurlSession
    HAS_CURL_CFFI = True
except ImportError:
    HAS_CURL_CFFI = False

ENGINE_NAME = "curl_cffi (Chrome TLS)" if HAS_CURL_CFFI else "httpx (fallback)"

BROWSER_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

MAX_PROXY_RETRIES = 3
_executor = ThreadPoolExecutor(max_workers=4)

async def fetch_page(url: str, extra_headers: Optional[Dict] = None, timeout: int = 30) -> str:
    from utils.proxy_pool import proxy_pool
    headers = {**BROWSER_HEADERS}
    if extra_headers: headers.update(extra_headers)
    
    tried_proxies = []
    for _ in range(min(MAX_PROXY_RETRIES, proxy_pool.count or 0)):
        proxy = proxy_pool.next()
        if proxy is None or proxy in tried_proxies: break
        tried_proxies.append(proxy)
        try:
            result = await _do_fetch(url, headers, timeout, proxy)
            proxy_pool.mark_ok(proxy)
            return result
        except:
            proxy_pool.mark_failed(proxy)
    
    return await _do_fetch(url, headers, timeout, None)

async def _do_fetch(url: str, headers: Dict, timeout: int, proxy: Optional[str]) -> str:
    if HAS_CURL_CFFI:
        return await _fetch_curl_cffi(url, headers, timeout, proxy)
    return await _fetch_httpx(url, headers, timeout, proxy)

async def _fetch_curl_cffi(url: str, headers: Dict, timeout: int, proxy: Optional[str]) -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _fetch_curl_cffi_sync, url, headers, timeout, proxy)

def _fetch_curl_cffi_sync(url: str, headers: Dict, timeout: int, proxy: Optional[str]) -> str:
    kwargs = {"timeout": timeout, "allow_redirects": True, "verify": False}
    if proxy: kwargs["proxy"] = proxy
    with CurlSession(impersonate="chrome120") as session:
        resp = session.get(url, headers=headers, **kwargs)
        resp.raise_for_status()
        return resp.text

async def _fetch_httpx(url: str, headers: Dict, timeout: int, proxy: Optional[str]) -> str:
    import httpx
    proxies = proxy if proxy else {}
    async with httpx.AsyncClient(timeout=float(timeout), follow_redirects=True, proxies=proxies) as client:
        resp = await client.get(url, headers=headers)
        resp.raise_for_status()
        # WeChat content is usually UTF-8, but httpx might fallback to ISO-8859-1 if not specified
        if not resp.encoding or resp.encoding == 'ISO-8859-1':
            resp.encoding = 'utf-8'
        return resp.text
