"""FastAPI 应用入口"""
from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from story_engine import __version__
from story_engine.api.routes import export, generate, models, novel, research, style, system
from story_engine.core.config import get_config

# ── 日志配置 ────────────────────────────────

log_dir = Path(__file__).resolve().parent.parent.parent.parent / "logs"
log_dir.mkdir(exist_ok=True)
log_file = log_dir / "story_engine.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

logger = logging.getLogger("story_engine")
logger.info("=" * 50)
logger.info("故事引擎启动")
logger.info("日志文件: %s", log_file)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """应用生命周期：shutdown 时释放 LLM 连接池（见 L3）"""
    yield
    from story_engine.api.routes.generate import close_router
    try:
        await close_router()
    except Exception:
        logger.warning("关闭 LLM 连接池失败", exc_info=True)


app = FastAPI(
    title="故事引擎 API",
    description="AI 小说生成系统 — Story Engine",
    version=__version__,
    lifespan=lifespan,
)

# 鉴权中间件：配置了 security.api_key 时必须携带 X-API-Key；
# 未配置时仅允许本机回环访问（其余客户端一律 403）。
_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


@app.middleware("http")
async def api_auth_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/api") and path != "/api/health":
        cfg = get_config()
        api_key = (cfg.get("security.api_key") or "").strip()
        if api_key:
            provided = request.headers.get("X-API-Key", "")
            if not secrets.compare_digest(provided, api_key):
                return JSONResponse(status_code=401, content={"detail": "无效的 API Key"})
        else:
            host = request.client.host if request.client else ""
            if host not in _LOOPBACK_HOSTS:
                return JSONResponse(
                    status_code=403,
                    content={"detail": "仅允许本机访问，请在 config.yaml 配置 security.api_key"},
                )
    return await call_next(request)


# CORS — 白名单来自配置 security.cors_origins，默认仅前端开发服务器
# 注意：CORS 中间件须最后注册（最外层），否则 preflight/错误响应不带 CORS 头
_cfg = get_config()
cors_origins = _cfg.get("security.cors_origins") or [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=list(cors_origins),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(models.router)
app.include_router(novel.router)
app.include_router(generate.router)
app.include_router(export.router)
app.include_router(export.IMPORT_ROUTER)
app.include_router(research.router)
app.include_router(system.router)
app.include_router(style.router)


@app.get("/")
async def root():
    return {"service": "故事引擎", "version": __version__, "status": "running"}


@app.get("/api/health")
async def health():
    return {"status": "ok", "version": __version__}


# ── 全局异常处理（L9）───────────────────────────────
# 业务失败统一 HTTPException(4xx)；未捕获异常记日志 + 返回脱敏信息。


class BusinessError(Exception):
    """业务错误：message 会以 HTTPException(400) 返回。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


@app.exception_handler(BusinessError)
async def business_error_handler(_: Request, exc: BusinessError):
    logger.warning("业务错误: %s", exc.message)
    return JSONResponse(status_code=400, content={"detail": exc.message})


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(Exception)
async def unhandled_exception_handler(_: Request, exc: Exception):
    logger.exception("未捕获异常")
    return JSONResponse(
        status_code=500,
        content={"detail": "服务器内部错误"},
    )
