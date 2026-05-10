#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Login Route
"""

from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import httpx
import time
from utils.auth_manager import auth_manager

router = APIRouter()
MP_BASE_URL = "https://mp.weixin.qq.com"
QR_ENDPOINT = f"{MP_BASE_URL}/cgi-bin/scanloginqrcode"
BIZ_LOGIN_ENDPOINT = f"{MP_BASE_URL}/cgi-bin/bizlogin"

# [FIX] 服务端维护微信 session cookie，不依赖浏览器转发
_wx_cookies = httpx.Cookies()
_wx_headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://mp.weixin.qq.com/",
}

@router.post("/session/{sessionid}")
async def create_session(sessionid: str):
    """创建微信登录 session，获取初始 cookie"""
    global _wx_cookies
    try:
        body = {"userlang": "zh_CN", "login_type": 3, "sessionid": sessionid, "f": "json", "ajax": 1}
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, cookies=_wx_cookies) as client:
            response = await client.post(
                BIZ_LOGIN_ENDPOINT,
                params={"action": "startlogin"},
                data=body,
                headers=_wx_headers
            )
            # 保存微信返回的 cookie
            _wx_cookies.update(response.cookies)
        return response.json()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"create_session error: {e}")
        return {"base_resp": {"ret": 0}}

@router.get("/getqrcode")
async def get_qrcode():
    """获取微信扫码登录二维码图片"""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, cookies=_wx_cookies) as client:
            response = await client.get(
                QR_ENDPOINT,
                params={"action": "getqrcode", "random": int(time.time() * 1000)},
                headers=_wx_headers
            )
            _wx_cookies.update(response.cookies)
        content = response.content
        if len(content) > 0:
            return Response(content=content, media_type="image/png")
        else:
            # 如果 cookie 无效导致返回空，尝试不带 cookie 请求
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
                response = await client.get(
                    QR_ENDPOINT,
                    params={"action": "getqrcode", "random": int(time.time() * 1000)},
                    headers=_wx_headers
                )
                _wx_cookies.update(response.cookies)
            return Response(content=response.content, media_type="image/png")
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"getqrcode error: {e}")
        return Response(content=b"", media_type="image/png", status_code=500)

@router.get("/scan")
async def check_scan_status():
    """检查微信扫码状态"""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True, cookies=_wx_cookies) as client:
            response = await client.get(
                QR_ENDPOINT,
                params={"action": "ask", "token": "", "lang": "zh_CN", "f": "json", "ajax": 1},
                headers=_wx_headers
            )
            _wx_cookies.update(response.cookies)
        return response.json()
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"scan check error: {e}")
        return {"base_resp": {"ret": -1, "err_msg": str(e)}}

@router.get("/info")
async def get_login_info():
    creds = auth_manager.get_credentials()
    if creds: return {"success": True, "data": creds}
    return {"success": False, "error": "Not logged in"}

@router.post("/bizlogin")
async def biz_login():
    """完成微信扫码登录，提取并保存 token 和 cookie"""
    import re
    try:
        body = {"userlang": "zh_CN", "login_type": 3, "f": "json", "ajax": 1}
        
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False, cookies=_wx_cookies) as client:
            response = await client.post(
                BIZ_LOGIN_ENDPOINT,
                params={"action": "login"},
                data=body,
                headers=_wx_headers
            )
            _wx_cookies.update(response.cookies)
        
        result = response.json()
        redirect_url = result.get("redirect_url", "")
        
        # 从重定向 URL 中提取 token
        token_match = re.search(r"token=(\d+)", redirect_url)
        token = token_match.group(1) if token_match else ""
        
        # 将服务端 cookie jar 转换为字符串
        cookie_str = "; ".join([f"{k}={v}" for k, v in _wx_cookies.items()])
        
        if token:
            # 获取用户信息
            nickname = ""
            try:
                async with httpx.AsyncClient(timeout=10.0, cookies=_wx_cookies) as client:
                    info_resp = await client.get(
                        "https://mp.weixin.qq.com/cgi-bin/settingpage",
                        params={"action": "index", "token": token, "lang": "zh_CN", "f": "json"},
                        headers=_wx_headers
                    )
                    info_data = info_resp.json()
                    nickname = info_data.get("nickname", "")
            except Exception:
                pass
            
            expire_time = int(time.time()) + 7200
            auth_manager.save_credentials(
                token=token,
                cookie=cookie_str,
                fakeid="",
                nickname=nickname,
                expire_time=expire_time
            )
            return {"success": True, "data": {"token": token, "nickname": nickname}}
        else:
            return {"success": False, "error": "未能获取 token"}
    except Exception as e:
        import logging
        logging.getLogger(__name__).error(f"bizlogin error: {e}")
        return {"success": False, "error": str(e)}

