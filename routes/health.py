#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Health Check Route
"""

from fastapi import APIRouter
from utils.http_client import ENGINE_NAME
from utils.proxy_pool import proxy_pool
from utils.auth_manager import auth_manager

router = APIRouter()

@router.get("/health", summary="Health Check")
async def health_check():
    creds = auth_manager.get_credentials()
    is_logged_in = bool(creds and creds.get("token") and creds.get("cookie"))
    
    return {
        "status": "healthy",
        "version": "1.0.0",
        "framework": "FastAPI",
        "http_engine": ENGINE_NAME,
        "proxy_pool": proxy_pool.get_status(),
        "login_status": is_logged_in,
        "nickname": creds.get("nickname") if is_logged_in else "",
        "expire_time": creds.get("expire_time") if is_logged_in else None
    }
