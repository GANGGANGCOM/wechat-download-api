#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS Subscription and Feed Generation
"""

import logging
import asyncio
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel
from typing import Optional, List
from utils.rss_store import rss_store
from datetime import datetime

logger = logging.getLogger(__name__)
router = APIRouter()

class SubscribeRequest(BaseModel):
    fakeid: str
    nickname: str
    alias: Optional[str] = ""
    head_img: Optional[str] = ""

class UnsubscribeRequest(BaseModel):
    fakeid: str

@router.get("/rss/subscriptions")
async def get_subscriptions():
    """List all tracked subscriptions"""
    try:
        subs = rss_store.get_subscriptions()
        for sub in subs:
            if sub.get('last_update_time'):
                sub['last_update_time'] *= 1000
        return {"success": True, "data": subs}
    except Exception as e:
        logger.error(f"Error getting subscriptions: {str(e)}")
        return {"success": False, "error": str(e)}

@router.post("/rss/subscribe")
async def subscribe(req: SubscribeRequest):
    """Add a new account to the tracking list"""
    try:
        rss_store.add_subscription(
            fakeid=req.fakeid,
            nickname=req.nickname,
            avatar=req.head_img
        )
        # Trigger an initial sync
        from utils.rss_poller import rss_poller
        asyncio.create_task(rss_poller.poll_account(req.fakeid))
        
        return {"success": True, "message": f"Subscribed to {req.nickname}"}
    except Exception as e:
        logger.error(f"Error subscribing: {str(e)}")
        return {"success": False, "error": str(e)}

@router.post("/rss/unsubscribe")
async def unsubscribe(req: UnsubscribeRequest):
    """Remove an account from the tracking list"""
    try:
        rss_store.remove_subscription(req.fakeid)
        return {"success": True, "message": f"Unsubscribed from {req.fakeid}"}
    except Exception as e:
        logger.error(f"Error unsubscribing: {str(e)}")
        return {"success": False, "error": str(e)}

@router.post("/rss/sync/{fakeid}")
async def sync_account(fakeid: str):
    """Manually trigger a sync for an account"""
    from utils.rss_poller import rss_poller
    success = await rss_poller.poll_account(fakeid)
    if success:
        return {"success": True, "message": "Sync completed"}
    else:
        return {"success": False, "error": "Sync failed"}

@router.get("/rss/{fakeid}")
async def get_feed(fakeid: str):
    """Generate an RSS XML feed for a specific account"""
    try:
        # Get articles from store
        articles = rss_store.get_articles(fakeid, limit=20)
        
        # Simple RSS XML generation
        xml = ['<?xml version="1.0" encoding="UTF-8"?>']
        xml.append('<rss version="2.0">')
        xml.append('  <channel>')
        xml.append(f'    <title>WeChat RSS: {fakeid}</title>')
        xml.append(f'    <link>https://mp.weixin.qq.com/</link>')
        xml.append(f'    <description>WeChat Official Account Feed</description>')
        
        for art in articles:
            xml.append('    <item>')
            xml.append(f'      <title><![CDATA[{art["title"]}]]></title>')
            xml.append(f'      <link>{art["link"]}</link>')
            xml.append(f'      <description><![CDATA[{art["digest"]}]]></description>')
            xml.append(f'      <pubDate>{datetime.fromtimestamp(art["create_time"]).strftime("%a, %d %b %Y %H:%M:%S GMT")}</pubDate>')
            xml.append(f'      <guid>{art["aid"]}</guid>')
            xml.append('    </item>')
            
        xml.append('  </channel>')
        xml.append('</rss>')
        
        return Response(content="\n".join(xml), media_type="application/xml")
    except Exception as e:
        logger.error(f"Error generating feed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
