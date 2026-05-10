import httpx
import logging
import json
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

router = APIRouter(prefix="/api/ai", tags=["AI"])
logger = logging.getLogger(__name__)

class AIAnalyzeRequest(BaseModel):
    content: str
    api_key: str
    base_url: str
    model: str
    prompt: Optional[str] = None

@router.post("/analyze")
async def analyze_content(request: AIAnalyzeRequest):
    """
    代理 AI 分析请求，解决前端直接调用可能遇到的 CORS 或 网络连接问题 (Failed to fetch)
    """
    logger.info(f"AI Proxy: Analyzing content with model {request.model}")
    
    # 构造请求头
    headers = {
        "Authorization": f"Bearer {request.api_key}",
        "Content-Type": "application/json"
    }
    
    # 构造请求体
    payload = {
        "model": request.model,
        "messages": [
            {
                "role": "user", 
                "content": request.prompt or f"分析以下内容:\n{request.content}"
            }
        ],
        "temperature": 0.7,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"}
    }
    
    # 清理 base_url
    api_url = f"{request.base_url.rstrip('/')}/v1/chat/completions"
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(api_url, headers=headers, json=payload)
            
            if response.status_code != 200:
                logger.error(f"AI API Error: {response.status_code} - {response.text}")
                try:
                    error_data = response.json()
                    error_msg = error_data.get("message") or error_data.get("error", {}).get("message") or response.text
                except:
                    error_msg = response.text
                return {"success": False, "error": error_msg, "status": response.status_code}
            
            data = response.json()
            return {"success": True, "data": data}
            
    except httpx.ConnectError:
        logger.error("AI Proxy: Connection Error - Could not reach the API server")
        return {"success": False, "error": "无法连接到 AI 服务器 (Connection Error)"}
    except httpx.TimeoutException:
        logger.error("AI Proxy: Timeout Error")
        return {"success": False, "error": "AI 服务器响应超时"}
    except Exception as e:
        logger.error(f"AI Proxy: Unexpected error: {str(e)}")
        return {"success": False, "error": str(e)}
