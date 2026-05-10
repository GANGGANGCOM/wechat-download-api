#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WeChat MP API Client
"""

import logging
import json
import httpx
from typing import Optional, List, Dict
from utils.auth_manager import auth_manager

logger = logging.getLogger(__name__)

async def fetch_articles_list(fakeid: str, begin: int = 0, count: int = 10, keyword: str = "") -> Dict:
    """Fetch article list from WeChat MP platform"""
    creds = auth_manager.get_credentials()
    if not creds:
        return {"success": False, "error": "Not logged in"}
    
    token = creds.get("token", "")
    cookie = creds.get("cookie", "")
    
    params = {
        "sub": "search" if keyword else "list",
        "begin": begin,
        "count": count,
        "query": keyword or "",
        "fakeid": fakeid,
        "type": "101_1",
        "free_publish_type": 1,
        "sub_action": "list_ex",
        "token": token,
        "lang": "zh_CN",
        "f": "json",
        "ajax": 1,
    }
    
    url = "https://mp.weixin.qq.com/cgi-bin/appmsgpublish"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Referer": "https://mp.weixin.qq.com/",
        "Cookie": cookie
    }
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.get(url, params=params, headers=headers)
        if response.status_code != 200:
            return {"success": False, "error": f"HTTP {response.status_code}"}
        
        try:
            result = response.json()
        except:
            return {"success": False, "error": "Invalid JSON response from WeChat"}

    base_resp = result.get("base_resp", {})
    ret = base_resp.get("ret")
    if ret != 0:
        return {"success": False, "error": f"WeChat error {ret}: {base_resp.get('err_msg')}"}
    
    publish_page = result.get("publish_page")
    if isinstance(publish_page, str):
        publish_page = json.loads(publish_page)
    
    publish_list = publish_page.get("publish_list", [])
    articles = []
    
    for item in publish_list:
        info = item.get("publish_info")
        if isinstance(info, str): info = json.loads(info)
        appmsgex = info.get("appmsgex", [])
        for art in appmsgex:
            articles.append({
                "aid": str(art.get("aid", "")),
                "title": art.get("title", "No Title"),
                "link": art.get("link", ""),
                "update_time": art.get("update_time", 0),
                "create_time": art.get("create_time", 0),
                "digest": art.get("digest", ""),
                "cover": art.get("cover", ""),
                "author": art.get("author", "")
            })
            
    return {
        "success": True,
        "articles": articles,
        "total": publish_page.get("total_count", 0)
    }
