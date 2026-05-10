#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Article List API
"""

import logging
import sqlite3
from fastapi import APIRouter, Query
from typing import Optional
from utils.wechat_api import fetch_articles_list

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/articles", summary="Get Article List")
async def get_articles(
    fakeid: str = Query(..., description="FakeID of the target account"),
    begin: int = Query(0, description="Offset", ge=0),
    count: int = Query(10, description="Count", ge=1, le=100),
    keyword: Optional[str] = Query(None, description="Search keyword")
):
    result = await fetch_articles_list(fakeid, begin, count, keyword or "")
    if not result["success"]:
        return {"success": False, "error": result["error"]}
    
    articles = result["articles"]
    
    # Check cache status for these articles
    from utils.rss_store import rss_store
    with rss_store.get_connection() as conn:
        conn.row_factory = sqlite3.Row
        for art in articles:
            aid = art.get("aid")
            if aid:
                row = conn.execute("SELECT content_html, content_text FROM articles WHERE aid = ?", (aid,)).fetchone()
                art["has_content"] = bool(row and row["content_html"])
                # Also return truncated plain text for instant AI analysis
                if row and row["content_text"]:
                    art["content_text"] = row["content_text"][:2000]
                else:
                    art["content_text"] = None
            else:
                art["has_content"] = False
                art["content_text"] = None
                
            if art.get("update_time"): art["update_time"] *= 1000
            if art.get("create_time"): art["create_time"] *= 1000
        
    return {
        "success": True,
        "data": {
            "articles": articles,
            "total": result["total"],
            "begin": begin,
            "count": len(articles),
            "keyword": keyword
        }
    }

@router.get("/articles/search")
async def search_articles(fakeid: str, query: str, begin: int = 0, count: int = 10):
    return await get_articles(fakeid=fakeid, keyword=query, begin=begin, count=count)
