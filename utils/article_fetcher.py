#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文章内容获取器 - SOCKS5 代理方案
使用 curl_cffi 模拟真实浏览器 TLS 指纹，支持代理池轮转
"""

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)


async def fetch_article_content(
    article_url: str, 
    timeout: int = 60,
    wechat_token: Optional[str] = None,
    wechat_cookie: Optional[str] = None
) -> Optional[str]:
    """
    获取文章内容
    
    请求策略：
    1. SOCKS5 代理池轮转
    2. 直连兜底
    
    Args:
        article_url: 文章 URL
        timeout: 超时时间（秒）
        wechat_token: 微信 token（用于鉴权）
        wechat_cookie: 微信 Cookie（用于鉴权）
        
    Returns:
        文章 HTML 内容，失败返回 None
    """
    # 使用代理池获取文章
    html = await _fetch_via_proxy(article_url, timeout, wechat_cookie, wechat_token)
    return html


async def _fetch_via_proxy(
    article_url: str, 
    timeout: int,
    wechat_cookie: Optional[str] = None,
    wechat_token: Optional[str] = None,
    max_retries: int = 2
) -> Optional[str]:
    """
    通过 SOCKS5 代理或直连获取文章
    Args:
        article_url: 文章 URL
        timeout: 超时时间
        wechat_cookie: 微信 Cookie
        wechat_token: 微信 Token
        max_retries: 内容验证失败时的最大重试次数（每次会尝试不同代理）
    """
    try:
        from utils.http_client import fetch_page
        
        extra_headers = {"Referer": "https://mp.weixin.qq.com/"}
        is_public_url = "/s/" in article_url or "mp.weixin.qq.com/s?" in article_url
        
        for attempt in range(max_retries + 1):
            try:
                current_headers = extra_headers.copy()
                current_url = article_url
                
                # 策略：前几次尝试直连/代理，最后一次尝试带 Cookie
                if not is_public_url or attempt == max_retries:
                    if wechat_cookie: current_headers["Cookie"] = wechat_cookie
                    if wechat_token:
                        sep = '&' if '?' in current_url else '?'
                        current_url = f"{current_url}{sep}token={wechat_token}"

                html = await fetch_page(current_url, extra_headers=current_headers, timeout=timeout)
                
                from utils.helpers import has_article_content, is_article_unavailable

                # 1. 优先检查是否是永久失效
                if is_article_unavailable(html):
                    logger.warning("[Fetch] 文章已删除或违规 (attempt %d/%d) %s",
                                 attempt + 1, max_retries + 1, article_url[:60])
                    return html

                # 2. 检查是否有有效内容
                if has_article_content(html):
                    logger.info("[Fetch] 成功获取内容 len=%d (attempt %d/%d)",
                               len(html), attempt + 1, max_retries + 1)
                    return html
                
                # 3. 如果没有内容，分析原因（验证码、频率限制等）
                hint = "unknown"
                # 更精确的验证页特征
                if 'id="verify_container"' in html or 'verify.html' in html or 'mp.weixin.qq.com/mp/verify' in html:
                    hint = "wechat_verification_page"
                elif any(x in html for x in ["环境异常", "访问过于频繁", "为了你的帐号安全"]):
                    hint = "wechat_blocked"
                elif "请登录" in html or "login" in html.lower():
                    hint = "login_required"
                
                # 如果页面很大（超过100KB），即使有关键字也可能是误判，尝试返回让 processor 处理
                if len(html) > 100000 and not hint.endswith("_page"):
                    logger.info("[Fetch] 页面较大 (%d bytes)，即使触发关键字也尝试解析", len(html))
                    return html

                logger.warning("[Fetch] 无效响应 (len=%d, hint=%s, attempt %d/%d) %s",
                             len(html), hint, attempt + 1, max_retries + 1, article_url[:60])
                
                if attempt < max_retries:
                    # 动态增加等待时间
                    wait_time = (attempt + 1) * 2 + (0.5 if attempt == 0 else 1.5)
                    await asyncio.sleep(wait_time)
                    continue
                    
            except Exception as e:
                logger.warning("[Fetch] 请求异常: %s (attempt %d/%d)", 
                             str(e)[:100], attempt + 1, max_retries + 1)
                if attempt < max_retries:
                    await asyncio.sleep(1.5)
                    continue
        
        return None
        
    except Exception as e:
        logger.error("[Fetch] fatal error: %s", str(e)[:100])
        return None


async def fetch_articles_batch(
    article_urls: list, 
    max_concurrency: int = 5, 
    timeout: int = 60,
    wechat_token: Optional[str] = None,
    wechat_cookie: Optional[str] = None
) -> dict:
    """
    批量获取文章内容（并发版）
    
    Args:
        article_urls: 文章 URL 列表
        max_concurrency: 最大并发数
        timeout: 单个请求超时时间
        wechat_token: 微信 token（用于鉴权）
        wechat_cookie: 微信 Cookie（用于鉴权）
        
    Returns:
        {url: html} 字典，失败的 URL 对应 None
    """
    semaphore = asyncio.Semaphore(max_concurrency)
    results = {}
    
    async def fetch_one(url):
        async with semaphore:
            html = await fetch_article_content(url, timeout, wechat_token, wechat_cookie)
            results[url] = html
            await asyncio.sleep(1)
    
    logger.info("[Batch] 开始批量获取 %d 篇文章", len(article_urls))
    
    await asyncio.gather(
        *[fetch_one(url) for url in article_urls],
        return_exceptions=True
    )
    
    success_count = sum(1 for html in results.values() if html)
    fail_count = len(results) - success_count
    
    logger.info("[Batch] 完成: 成功=%d, 失败=%d", success_count, fail_count)
    
    return results
