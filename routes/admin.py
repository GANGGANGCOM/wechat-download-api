from fastapi import APIRouter
from utils.auth_manager import auth_manager

router = APIRouter()

@router.get("/status")
async def get_status():
    """返回当前登录状态，格式与 admin.html 前端期望一致"""
    creds = auth_manager.get_credentials()
    is_logged_in = bool(creds and creds.get("token") and creds.get("cookie"))
    if is_logged_in:
        import time
        expire_time = creds.get("expire_time", 0)
        is_expired = expire_time > 0 and time.time() > expire_time
        return {
            "authenticated": True,
            "nickname": creds.get("nickname", ""),
            "fakeid": creds.get("fakeid", ""),
            "isExpired": is_expired,
            "status": "凭证已过期，请重新登录" if is_expired else "正常"
        }
    return {
        "authenticated": False,
        "status": "未登录"
    }

@router.post("/logout")
async def logout():
    """清除存储的微信凭证"""
    auth_manager.credentials = {
        "token": "", "cookie": "", "fakeid": "",
        "nickname": "", "expire_time": 0
    }
    try:
        if auth_manager.credentials_file.exists():
            auth_manager.credentials_file.unlink()
    except Exception:
        pass
    return {"status": "ok", "message": "已退出登录"}
