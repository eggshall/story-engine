"""系统信息路由 — 路径探测、环境信息、默认参数设置"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter

from story_engine.api.schemas import ApiResponse, UpdateSettingsRequest
from story_engine.core.config import get_config, reload_config

router = APIRouter(prefix="/api", tags=["system"])


# ── 系统路径探测 ─────────────────────────────


def _detect_windows_user() -> str:
    """从 WSL 的 /mnt/c/Users/ 检测 Windows 用户名"""
    users_dir = Path("/mnt/c/Users")
    if users_dir.exists():
        for d in users_dir.iterdir():
            if d.is_dir() and d.name not in (
                "Default", "Public", "All Users", "Default User", "desktop.ini",
                "__pycache__",
            ):
                return d.name
    return ""


def _list_mounts() -> list:
    """列出 WSL 中的挂载点（Windows 盘符）"""
    mounts = []
    for d in sorted(Path("/mnt").iterdir()):
        if d.is_dir() and len(d.name) == 1 and d.name.isalpha():
            mounts.append({"drive": d.name.upper(), "path": str(d)})
    return mounts


@router.get("/system/paths")
def get_system_paths() -> ApiResponse:
    """获取系统路径建议"""
    windows_user = _detect_windows_user()
    mounts = _list_mounts()

    suggested = []
    if windows_user:
        suggested.append({
            "label": f"桌面 (C:\\Users\\{windows_user}\\Desktop)",
            "path": f"/mnt/c/Users/{windows_user}/Desktop",
        })
        suggested.append({
            "label": f"文档 (C:\\Users\\{windows_user}\\Documents)",
            "path": f"/mnt/c/Users/{windows_user}/Documents",
        })
        suggested.append({
            "label": f"下载 (C:\\Users\\{windows_user}\\Downloads)",
            "path": f"/mnt/c/Users/{windows_user}/Downloads",
        })
    suggested.append({
        "label": "D: 盘根目录",
        "path": "/mnt/d/",
    })
    if "E" in [m["drive"] for m in mounts]:
        suggested.append({
            "label": "E: 盘根目录",
            "path": "/mnt/e/",
        })

    # 仅返回路径建议，不暴露 Windows 用户名 / 挂载点 / HOME 等主机信息
    return ApiResponse(success=True, data={"suggested": suggested})


# ── 默认写作参数 ─────────────────────────────


def _get_writing_settings() -> Dict[str, Any]:
    """从 config 读取默认写作参数"""
    cfg = get_config()
    return {
        "default_model": cfg.get("llm.default_model", "deepseek-v4-pro"),
        "temperature": cfg.get("writing.temperature", 0.7),
        "max_tokens": cfg.get("writing.max_tokens", 4096),
    }


@router.get("/settings")
def get_settings() -> ApiResponse:
    """获取默认写作参数"""
    return ApiResponse(success=True, data=_get_writing_settings())


@router.post("/settings")
def update_settings(req: UpdateSettingsRequest) -> ApiResponse:
    """更新默认写作参数（持久化到 config.yaml）"""
    cfg = get_config()

    if req.default_model is not None:
        cfg.set("llm.default_model", req.default_model)
    if req.temperature is not None:
        cfg.set("writing.temperature", req.temperature)
    if req.max_tokens is not None:
        cfg.set("writing.max_tokens", req.max_tokens)

    cfg.save()
    # 默认模型变更时重建 router（见 L6.3）
    reload_config()
    return ApiResponse(success=True, data=_get_writing_settings())
