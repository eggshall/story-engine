"""FastAPI 应用入口"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from story_engine import __version__
from story_engine.api.routes import export, generate, models, novel, research, style, system

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

app = FastAPI(
    title="故事引擎 API",
    description="AI 小说生成系统 — Story Engine",
    version=__version__,
)

# CORS — 允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
