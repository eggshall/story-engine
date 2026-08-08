"""模型路由器 — 远程/本地自动切换 + 负载分配"""

from __future__ import annotations

from typing import Any, AsyncGenerator, Dict, List, Optional

from story_engine.llm.api_client import AnthropicClient, OpenAIClient
from story_engine.llm.base import BaseLLM, LLMRequest, LLMResponse, LLMStreamError
from story_engine.llm.local_client import LocalLLMClient


class ModelRouter:
    """模型路由器 — 根据配置自动创建并调度模型"""

    def __init__(
        self,
        models_config: List[Dict[str, Any]],
        default_model: Optional[str] = None,
    ) -> None:
        self._clients: Dict[str, BaseLLM] = {}
        self._default_model = default_model
        self._init_clients(models_config)

    def _init_clients(self, models_config: List[Dict[str, Any]]) -> None:
        for cfg in models_config:
            if not cfg.get("enabled", True):
                continue
            client = self._create_client(cfg)
            if client:
                self._clients[cfg["name"]] = client

    def _create_client(self, cfg: Dict[str, Any]) -> Optional[BaseLLM]:
        provider = cfg.get("provider", "")
        if provider == "deepseek":
            return OpenAIClient(cfg)
        elif provider == "openai":
            return OpenAIClient(cfg)
        elif provider == "anthropic":
            return AnthropicClient(cfg)
        elif provider == "local":
            return LocalLLMClient(cfg)
        return None

    def get_client(self, name: str) -> Optional[BaseLLM]:
        return self._clients.get(name)

    def list_models(self) -> List[str]:
        return list(self._clients.keys())

    def _pick_target(self, model_name: Optional[str]) -> Optional[str]:
        """选择目标模型：显式指定 > 默认模型 > 第一个启用的模型。"""
        if model_name and model_name in self._clients:
            return model_name
        if self._default_model and self._default_model in self._clients:
            return self._default_model
        return next(iter(self._clients), None)

    async def chat(
        self,
        request: LLMRequest,
        model_name: Optional[str] = None,
        fallback: bool = True,
    ) -> LLMResponse:
        """发送请求到指定模型，失败时可 fallback 到下一个可用模型。

        返回聚合诊断信息：全部失败时 error 包含各模型原始错误（去敏，不含
        API Key）；仅真实 fallback（指定模型失败后切到另一模型）才加前缀。
        """
        target = self._pick_target(model_name)
        attempted: List[str] = []
        errors: List[str] = []

        if target is not None:
            attempted.append(target)
            result = await self._clients[target].chat(request)
            if result.success or not fallback:
                return result
            if result.error:
                errors.append(f"{target}: {result.error}")

        # 真实 fallback：指定了目标但失败后才切换到其他模型
        if fallback:
            for name, client in self._clients.items():
                if name in attempted:
                    continue
                attempted.append(name)
                result = await client.chat(request)
                if result.success:
                    # 仅真实 fallback（显式指定过目标）才加前缀
                    if target is not None and name != target:
                        result.content = f"[Fallback → {name}]\n" + result.content
                    return result
                if result.error:
                    errors.append(f"{name}: {result.error}")

        detail = "；".join(errors) if errors else "未找到可用模型"
        return LLMResponse(success=False, error=f"所有模型均不可用（{detail}）")

    async def chat_stream(
        self,
        request: LLMRequest,
        model_name: Optional[str] = None,
    ) -> AsyncGenerator[str, None]:
        """流式生成：目标模型失败时自动切换（仅真实 fallback 加前缀）。

        错误以结构化形式抛出（`LLMStreamError`），由外层包装为 SSE error 事件，
        不再把 `[Error: ...]` 混入正文（见 L5.3 / L8）。
        """
        target = self._pick_target(model_name)
        attempted: List[str] = []
        errors: List[str] = []

        if target is not None:
            attempted.append(target)
            prefix = f"[Fallback → {target}]\n" if (model_name and model_name != target) else ""
            used = False
            try:
                async for chunk in self._clients[target].chat_stream(request):
                    if prefix and not used:
                        yield prefix
                        used = True
                    yield chunk
                # 正常完成
                return
            except LLMStreamError as e:
                errors.append(f"{target}: {e.message}")
            except Exception as e:  # noqa: BLE001 - 内部实现可能抛任意异常
                errors.append(f"{target}: {e}")

        # 目标失败或不可用 → 尝试其他模型
        for name, client in self._clients.items():
            if name in attempted:
                continue
            attempted.append(name)
            prefix = f"[Fallback → {name}]\n"
            try:
                used = False
                async for chunk in client.chat_stream(request):
                    if not used:
                        yield prefix
                        used = True
                    yield chunk
                return
            except LLMStreamError as e:
                errors.append(f"{name}: {e.message}")
            except Exception as e:  # noqa: BLE001
                errors.append(f"{name}: {e}")

        detail = "；".join(errors) if errors else "未找到可用模型"
        raise LLMStreamError(f"所有模型流式生成失败（{detail}）")

    async def close_all(self) -> None:
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
