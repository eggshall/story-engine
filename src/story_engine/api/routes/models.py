"""模型管理路由"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx
from fastapi import APIRouter, HTTPException

from story_engine.api.schemas import ApiResponse, ModelConfigRequest
from story_engine.core.config import get_config

router = APIRouter(prefix="/api/models", tags=["models"])


def _mask_api_key(key: str) -> str:
    """掩码 API Key：只保留后 4 位"""
    if not key or len(key) <= 4:
        return key
    return "****" + key[-4:]


def _model_to_dict(m: Dict[str, Any]) -> Dict[str, Any]:
    """将配置中的模型条目转为返回用的 dict（含掩码）"""
    return {
        "name": m.get("name", ""),
        "provider": m.get("provider", ""),
        "model_id": m.get("model_id", ""),
        "base_url": m.get("base_url", ""),
        "api_key": _mask_api_key(m.get("api_key", "")),
        "enabled": m.get("enabled", False),
        "temperature": m.get("temperature", 0.7),
        "max_tokens": m.get("max_tokens", 4096),
    }


def _find_model(name: str) -> Optional[Dict[str, Any]]:
    """按名称查找模型配置"""
    cfg = get_config()
    models: List[Dict[str, Any]] = cfg.get("llm.models", [])
    for m in models:
        if m.get("name") == name:
            return m
    return None


@router.get("/")
async def list_models() -> ApiResponse:
    """列出所有可用模型"""
    cfg = get_config()
    models: List[Dict[str, Any]] = cfg.get("llm.models", [])
    result = [_model_to_dict(m) for m in models]
    return ApiResponse(success=True, data=result)


@router.get("/default")
async def get_default_model() -> ApiResponse:
    """获取默认模型名称"""
    cfg = get_config()
    default = cfg.get("llm.default_model", "")
    return ApiResponse(success=True, data={"default_model": default})


@router.patch("/{name}")
async def update_model(name: str, req: ModelConfigRequest) -> ApiResponse:
    """更新模型配置（部分更新）"""
    model = _find_model(name)
    if model is None:
        raise HTTPException(status_code=404, detail=f"模型 '{name}' 不存在")

    # 部分更新：只更新请求中提供的字段
    if req.enabled is not None:
        model["enabled"] = req.enabled
    if req.api_key is not None:
        model["api_key"] = req.api_key
    if req.base_url is not None:
        model["base_url"] = req.base_url
    if req.temperature is not None:
        model["temperature"] = req.temperature
    if req.max_tokens is not None:
        model["max_tokens"] = req.max_tokens

    cfg = get_config()
    cfg.save()

    return ApiResponse(success=True, data=_model_to_dict(model))


@router.post("/{name}/test")
async def test_model_connection(name: str) -> ApiResponse:
    """测试模型连接"""
    model = _find_model(name)
    if model is None:
        raise HTTPException(status_code=404, detail=f"模型 '{name}' 不存在")

    base_url = model.get("base_url", "")
    if not base_url:
        return ApiResponse(
            success=True,
            data={"status": "error", "message": "未配置 Base URL"},
        )

    # 根据 provider 选择探测端点
    provider = model.get("provider", "")
    if provider == "ollama" or "11434" in base_url:
        probe_url = base_url.rstrip("/") + "/api/tags"
    elif provider == "anthropic":
        probe_url = base_url.rstrip("/") + "/v1/models"
    else:
        # OpenAI-compatible
        probe_url = base_url.rstrip("/") + "/models"

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(probe_url)
            if resp.status_code < 500:
                return ApiResponse(
                    success=True,
                    data={"status": "ok", "message": f"连接成功 (HTTP {resp.status_code})"},
                )
            else:
                return ApiResponse(
                    success=True,
                    data={"status": "error", "message": f"服务端错误 (HTTP {resp.status_code})"},
                )
    except Exception as e:
        return ApiResponse(
            success=True,
            data={"status": "error", "message": f"连接失败: {str(e)}"},
        )
