#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS 存储器 - 使用 SQLite 存储订阅和文章
"""

import sqlite3
import json
import logging
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional
import os
import sys

logger = logging.getLogger(__name__)

class RSSStore:
    def __init__(self, db_path: str = None):
        if db_path:
            self.db_path = Path(db_path)
        else:
            # [NEW] 智能识别存储路径
            # 如果是 PyInstaller 打包后的环境
            if getattr(sys, 'frozen', False):
                # 存放在用户数据目录下 (C:\Users\用户名\AppData\Roaming\GeminiRSS)
                app_data_dir = Path(os.getenv('APPDATA')) / 'GeminiRSS'
                self.db_path = app_data_dir / 'data' / 'rss.db'
            else:
                # 开发环境下保持现状
                self.db_path = Path("data/rss.db")
                
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_db()

    def get_connection(self):
        return sqlite3.connect(self.db_path)

    def init_db(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 订阅表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS subscriptions (
                    fakeid TEXT PRIMARY KEY,
                    nickname TEXT,
                    alias TEXT,
                    avatar TEXT,
                    last_update_time INTEGER,
                    status INTEGER DEFAULT 1
                )
            ''')
            # 文章表
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS articles (
                    aid TEXT PRIMARY KEY,
                    fakeid TEXT,
                    title TEXT,
                    link TEXT,
                    digest TEXT,
                    cover TEXT,
                    author TEXT,
                    create_time INTEGER,
                    update_time INTEGER,
                    content_html TEXT,
                    content_text TEXT,
                    FOREIGN KEY (fakeid) REFERENCES subscriptions(fakeid)
                )
            ''')
            conn.commit()

    def add_subscription(self, fakeid: str, nickname: str, avatar: str = ""):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO subscriptions (fakeid, nickname, avatar, last_update_time)
                VALUES (?, ?, ?, ?)
            ''', (fakeid, nickname, avatar, int(datetime.now().timestamp())))
            conn.commit()

    def get_subscriptions(self) -> List[Dict]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM subscriptions')
            return [dict(row) for row in cursor.fetchall()]

    def save_articles(self, fakeid: str, articles: List[Dict]):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            for art in articles:
                cursor.execute('''
                    INSERT OR IGNORE INTO articles 
                    (aid, fakeid, title, link, digest, cover, author, create_time, update_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (
                    art.get('aid'), fakeid, art.get('title'), art.get('link'),
                    art.get('digest'), art.get('cover'), art.get('author'),
                    art.get('create_time'), art.get('update_time')
                ))
            conn.commit()

    def get_articles(self, fakeid: str, limit: int = 20) -> List[Dict]:
        with self.get_connection() as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM articles WHERE fakeid = ? 
                ORDER BY update_time DESC LIMIT ?
            ''', (fakeid, limit))
            return [dict(row) for row in cursor.fetchall()]

    def update_article_content(self, aid: str, html: str, text: str):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE articles SET content_html = ?, content_text = ? WHERE aid = ?
            ''', (html, text, aid))
            conn.commit()

    def remove_subscription(self, fakeid: str):
        """彻底删除订阅及其关联文章"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # 1. 删除文章
            cursor.execute('DELETE FROM articles WHERE fakeid = ?', (fakeid,))
            # 2. 删除订阅
            cursor.execute('DELETE FROM subscriptions WHERE fakeid = ?', (fakeid,))
            conn.commit()
            logger.info(f"Successfully removed subscription and articles for {fakeid}")

rss_store = RSSStore()

def init_db():
    rss_store.init_db()
