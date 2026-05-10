from fastapi import APIRouter, Response, Query
import httpx
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/image")
@router.get("/image/proxy")
@router.get("/proxy")
async def proxy_image(url: str = Query(...)):
    """
    代理微信图片，绕过防盗链限制
    支持重定向和超时处理
    """
    try:
        # 使用更大的超时时间和跟随重定向
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=False) as client:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://mp.weixin.qq.com/",
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
            }
            resp = await client.get(url, headers=headers)
            
            if resp.status_code != 200:
                logger.warning(f"Image proxy failed: status {resp.status_code} for {url[:100]}")
                return Response(status_code=resp.status_code)
                
            # 获取 content-type，如果没有则根据 URL 或内容猜测
            content_type = resp.headers.get("content-type", "image/jpeg")
            
            return Response(
                content=resp.content, 
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"} # 缓存一天
            )
    except Exception as e:
        logger.error(f"Image proxy error: {str(e)} for {url[:100]}")
        return Response(status_code=500)
