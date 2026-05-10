import os
import sys
from pathlib import Path

# [FIX] 路径自愈逻辑
if getattr(sys, 'frozen', False):
    base_path = Path(sys._MEIPASS)
    # [FIX] --noconsole 模式下 stdout/stderr 为 None，
    # 会导致 uvicorn 日志初始化时 isatty() 崩溃
    if sys.stdout is None:
        sys.stdout = open(os.devnull, 'w')
    if sys.stderr is None:
        sys.stderr = open(os.devnull, 'w')
else:
    base_path = Path(__file__).parent
    
if str(base_path) not in sys.path:
    sys.path.insert(0, str(base_path))

import uvicorn
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import logging

# 导入实际存在的路由
from routes.rss import router as rss_router
from routes.article import router as article_router
from routes.articles import router as articles_router
from routes.login import router as login_router
from routes.image import router as image_router
from routes.search import router as search_router
from routes.health import router as health_router
from routes.admin import router as admin_router
from routes.ai import router as ai_router
from utils.rss_store import init_db

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Gemini RSS API Service")

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
# NOTE: 路由文件内部已自带完整子路径（如 /health, /rss/subscribe），
# 所以这里统一使用 /api 前缀
app.include_router(rss_router, prefix="/api", tags=["rss"])
app.include_router(article_router, prefix="/api", tags=["article"])
app.include_router(articles_router, prefix="/api/public", tags=["articles"])
app.include_router(login_router, prefix="/api/login", tags=["login"])
app.include_router(image_router, prefix="/api", tags=["image"])
app.include_router(search_router, prefix="/api/public", tags=["search"])
app.include_router(health_router, prefix="/api", tags=["health"])
app.include_router(admin_router, prefix="/api/admin", tags=["admin"])
app.include_router(ai_router, tags=["ai"])

# [FIX] 挂载静态文件服务（admin.html, login.html 等）
# NOTE: 必须放在所有 API 路由之后，使用 html=True 支持直接访问 .html 文件
static_dir = base_path / "static"
if static_dir.exists():
    from fastapi.staticfiles import StaticFiles
    # 挂载到根路径，这样 /admin.html, /login.html 等都能直接访问
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")

@app.on_event("startup")
async def startup_event():
    init_db()
    logger.info("Database initialized")

@app.get("/")
async def root():
    return {"message": "Gemini RSS API Service is running"}

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"message": "Internal Server Error", "detail": str(exc)},
    )

if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    
    # [FIX] 关键修复：直接传递 app 对象，而不是字符串 "app:app"
    # 这样可以避免打包后的环境找不到模块
    uvicorn.run(app, host="0.0.0.0", port=5000)
