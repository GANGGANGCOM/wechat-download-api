#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Search Route
"""

import os
import time
import httpx
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel
from typing import Optional, List
from utils.auth_manager import auth_manager
from utils.image_proxy import proxy_image_url

router = APIRouter()

def get_base_url(request: Request) -> str:
    site_url = os.getenv("SITE_URL", "").strip()
    if site_url:
        return site_url.rstrip("/")
    proto = request.headers.get("X-Forwarded-Proto", "http")
    host = request.headers.get("X-Forwarded-Host") or request.headers.get("Host", "localhost:5000")
    return f"{proto}://{host}"

class SearchResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None

@router.get("/searchbiz", response_model=SearchResponse)
async def search_accounts(query: str, request: Request = None):
    credentials = auth_manager.get_credentials()
    if not credentials:
        return SearchResponse(success=False, error="Not logged in")
    
    token = credentials.get("token")
    cookie = credentials.get("cookie")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://mp.weixin.qq.com/cgi-bin/searchbiz",
                params={
                    "action": "search_biz",
                    "token": token,
                    "lang": "zh_CN",
                    "f": "json",
                    "ajax": 1,
                    "random": time.time(),
                    "query": query,
                    "begin": 0,
                    "count": 5
                },
                headers={
                    "Cookie": cookie,
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                }
            )
            
            result = response.json()
            if result.get("base_resp", {}).get("ret") == 0:
                accounts = result.get("list", [])
                base_url = get_base_url(request) if request else ""
                formatted_accounts = []
                for acc in accounts:
                    round_head_img = proxy_image_url(acc.get("round_head_img", ""), base_url)
                    formatted_accounts.append({
                        "fakeid": acc.get("fakeid", ""),
                        "nickname": acc.get("nickname", ""),
                        "alias": acc.get("alias", ""),
                        "round_head_img": round_head_img,
                        "service_type": acc.get("service_type", 0)
                    })
                return SearchResponse(success=True, data={"list": formatted_accounts, "total": len(formatted_accounts)})
            else:
                return SearchResponse(success=False, error=result.get("base_resp", {}).get("err_msg", "Search failed"))
    except Exception as e:
        print(f"Search failed: {str(e)}")
        return SearchResponse(success=False, error=str(e))
