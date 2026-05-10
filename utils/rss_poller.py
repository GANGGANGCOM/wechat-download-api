#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS 轮询器 - 定时更新订阅内容
"""

import asyncio
import logging
from typing import Optional
from utils.wechat_api import fetch_articles_list
from utils.rss_store import rss_store

logger = logging.getLogger(__name__)

class RSSPoller:
    def __init__(self, interval: int = 3600):
        self.interval = interval
        self.is_running = False
        self._task: Optional[asyncio.Task] = None

    async def start(self):
        if self.is_running: return
        self.is_running = True
        self._task = asyncio.create_task(self._run())
        logger.info("RSS Poller started")

    async def stop(self):
        self.is_running = False
        if self._task:
            self._task.cancel()
            try: await self._task
            except asyncio.CancelledError: pass
        logger.info("RSS Poller stopped")

    async def _run(self):
        while self.is_running:
            try:
                await self.poll_all()
            except Exception as e:
                logger.error(f"Error in RSS polling loop: {e}")
            await asyncio.sleep(self.interval)

    async def poll_all(self):
        subs = rss_store.get_subscriptions()
        for sub in subs:
            await self.poll_account(sub['fakeid'])
            await asyncio.sleep(2) # Avoid rate limiting

    async def poll_account(self, fakeid: str):
        """Fetch latest articles for an account and save to store"""
        logger.info(f"Polling articles for {fakeid}...")
        result = await fetch_articles_list(fakeid, count=10)
        if result["success"]:
            # Save to database
            rss_store.save_articles(fakeid, result["articles"])
            logger.info(f"Saved {len(result['articles'])} articles for {fakeid}")
            
            # Start background content fetching for pre-loading
            asyncio.create_task(self._fetch_contents_task(result["articles"]))
            
            return True
        else:
            logger.error(f"Failed to poll {fakeid}: {result['error']}")
            return False

    async def _fetch_contents_task(self, articles: list):
        """Pre-load article contents in the background"""
        from utils.article_fetcher import fetch_article_content
        from utils.content_processor import process_article_content
        from utils.auth_manager import auth_manager
        import re
        
        creds = auth_manager.get_credentials()
        token = creds.get("token") if creds else None
        cookie = creds.get("cookie") if creds else None
        
        for art in articles:
            aid = art.get('aid')
            link = art.get('link')
            
            # Check if already has content
            with rss_store.get_connection() as conn:
                row = conn.execute("SELECT content_html FROM articles WHERE aid = ?", (aid,)).fetchone()
                if row and row[0]: continue # Skip if already has content
            
            try:
                logger.info(f"Pre-loading content for article: {art.get('title')}")
                html = await fetch_article_content(link, wechat_token=token, wechat_cookie=cookie)
                if html:
                    processed = process_article_content(html)
                    rss_store.update_article_content(
                        aid, 
                        processed.get('content', ''), 
                        processed.get('plain_content', '')
                    )
                # Sleep between fetches to avoid rate limit
                await asyncio.sleep(3) 
            except Exception as e:
                logger.error(f"Failed to pre-load {aid}: {e}")

rss_poller = RSSPoller()
