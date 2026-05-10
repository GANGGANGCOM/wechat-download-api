#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Authentication Manager
"""

import os
import time
from pathlib import Path
from typing import Optional, Dict
from dotenv import load_dotenv, set_key

class AuthManager:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(AuthManager, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized: return
        import sys
        # [FIX] 打包环境下使用持久化路径，避免凭证存储在临时解压目录中
        if getattr(sys, 'frozen', False):
            app_data_dir = Path(os.getenv('APPDATA')) / 'GeminiRSS'
            self.base_dir = app_data_dir
        else:
            self.base_dir = Path(__file__).parent.parent
        self.env_path = self.base_dir / ".env"
        self.credentials_file = self.base_dir / "data" / ".credentials.json"
        self.credentials_file.parent.mkdir(parents=True, exist_ok=True)
        self._load_credentials()
        self._initialized = True
    
    def _load_credentials(self):
        if self.credentials_file.exists():
            try:
                import json
                with open(self.credentials_file, 'r', encoding='utf-8') as f:
                    self.credentials = json.load(f)
                return
            except: pass
        
        if self.env_path.exists():
            load_dotenv(self.env_path, override=True)
        
        self.credentials = {
            "token": os.getenv("WECHAT_TOKEN", ""),
            "cookie": os.getenv("WECHAT_COOKIE", ""),
            "fakeid": os.getenv("WECHAT_FAKEID", ""),
            "nickname": os.getenv("WECHAT_NICKNAME", ""),
            "expire_time": int(os.getenv("WECHAT_EXPIRE_TIME") or 0)
        }
    
    def save_credentials(self, token: str, cookie: str, fakeid: str, 
                        nickname: str, expire_time: int) -> bool:
        self.credentials.update({
            "token": token,
            "cookie": cookie,
            "fakeid": fakeid,
            "nickname": nickname,
            "expire_time": expire_time
        })
        
        try:
            import json
            self.credentials_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.credentials_file, 'w', encoding='utf-8') as f:
                json.dump(self.credentials, f, indent=2, ensure_ascii=False)
        except: pass
        
        try:
            if not self.env_path.exists(): self.env_path.touch()
            env_file = str(self.env_path)
            set_key(env_file, "WECHAT_TOKEN", token)
            set_key(env_file, "WECHAT_COOKIE", cookie)
            set_key(env_file, "WECHAT_FAKEID", fakeid)
            set_key(env_file, "WECHAT_NICKNAME", nickname)
            set_key(env_file, "WECHAT_EXPIRE_TIME", str(expire_time))
        except: pass
        return True
    
    def get_credentials(self) -> Optional[Dict]:
        self._load_credentials()
        if not self.credentials.get("token") or not self.credentials.get("cookie"):
            return None
        return self.credentials

auth_manager = AuthManager()
