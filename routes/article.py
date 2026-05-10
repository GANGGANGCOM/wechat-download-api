#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Article Content Route
"""

import logging
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from utils.article_fetcher import fetch_article_content
from utils.content_processor import process_article_content
from utils.auth_manager import auth_manager

logger = logging.getLogger(__name__)
router = APIRouter()

class ArticleRequest(BaseModel):
    url: str

class ArticleResponse(BaseModel):
    success: bool
    title: Optional[str] = ""
    content: Optional[str] = ""
    plain_content: Optional[str] = ""
    author: Optional[str] = ""
    publish_time: Optional[int] = 0
    images: Optional[list] = []
    error: Optional[str] = None

@router.post("/article", response_model=ArticleResponse)
async def get_article_detail(req: ArticleRequest, request: Request):
    """
    Get detailed article content including images and plain text
    """
    try:
        url = req.url
        # 1. Check if we already have it in the database
        import re
        import sqlite3
        from urllib.parse import urlparse, parse_qs
        from utils.rss_store import rss_store
        
        def extract_params(url_str):
            parsed = urlparse(url_str)
            return {k: v[0] for k, v in parse_qs(parsed.query).items()}
        
        # We'll search by link as a fallback
        conn = rss_store.get_connection()
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM articles WHERE link = ?", (url,)).fetchone()
        
        if row and row['content_html']:
            content = row['content_html']
            # [FIX] 升级到 V8 标记，彻底修复正文截断和 AI 分析失效问题
            if len(content) > 100 and 'wechat-backend-mark-v8' in content:
                logger.info(f"Using valid V8 cached content: {url[:60]}")
                return ArticleResponse(
                    success=True,
                    title=row['title'],
                    content=content,
                    plain_content=row['content_text'],
                    author=row['author'],
                    publish_time=row['create_time'] * 1000 if row['create_time'] else 0,
                    images=[]  # 缓存版暂时不返回图片列表(通常正文已包含代理后的img标签)
                )
            else:
                logger.info(f"Cache is invalid or old, forcing re-fetch: {url[:60]}")

        # 2. Not in cache, fetch it
        logger.info(f"Fetching article detail from web: {url[:60]}...")
        
        # Get credentials if available
        creds = auth_manager.get_credentials()
        token = creds.get("token") if creds else None
        cookie = creds.get("cookie") if creds else None
        
        # Fetch HTML
        html = await fetch_article_content(url, wechat_token=token, wechat_cookie=cookie)
        
        if not html:
            return ArticleResponse(success=False, error="Failed to fetch article content")
            
        # Determine proxy base URL for images
        base_url = f"{request.url.scheme}://{request.url.netloc}"
        
        # Process content
        processed = process_article_content(html, proxy_base_url=base_url)
        
        # Extract metadata
        title_match = re.search(r'var msg_title = ["\']([^"\']+)["\']', html)
        title = title_match.group(1) if title_match else "No Title"
        # [FIX] 如果是短内容（无独立标题的动态），msg_title 会包含全文，导致前端标题排版崩溃，因此强制截断
        if len(title) > 60:
            title = title[:50] + "..."
        
        author_match = re.search(r'var nickname = ["\']([^"\']+)["\']', html)
        author = author_match.group(1) if author_match else "Unknown"
        
        time_match = re.search(r'var ct = ["\']([^"\']+)["\']', html)
        publish_time_raw = int(time_match.group(1)) if time_match else 0
        
        # 3. Save to database if we can identify it
        try:
            # Try to find the article in DB to update it
            row = conn.execute("SELECT aid FROM articles WHERE link = ?", (url,)).fetchone()
            if row:
                rss_store.update_article_content(row['aid'], processed.get('content', ''), processed.get('plain_content', ''))
                logger.info(f"Updated cache for article {row['aid']}")
        except Exception as save_err:
            logger.warning(f"Failed to update cache: {save_err}")
        # 构造响应
        result = ArticleResponse(
            success=True,
            title=title,
            content=processed.get('content', ''),
            plain_content=processed.get('plain_content', ''),
            author=author,
            publish_time=publish_time_raw * 1000 if publish_time_raw else 0,
            images=processed.get('images', [])
        )
        
        logger.info(f"Article processed successfully: title={title[:30]}, content_len={len(result.content)}")
        if not result.content:
            logger.warning(f"Article content is EMPTY for url: {url}")
            
        return result
        
    except Exception as e:
        import traceback
        logger.error(f"Error in get_article_detail: {str(e)}")
        logger.error(traceback.format_exc())
        return ArticleResponse(success=False, error=str(e))
