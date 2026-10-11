"""模型路由器 — 远程/本地自动切换 + 负载分配"""

from __future__ import annotations

import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

from story_engine.llm.api_client import AnthropicClient, OpenAIClient
from story_engine.llm.base import (
    BaseLLM,
    LLMEmptyOutputError,
    LLMRequest,
    LLMResponse,
    LLMStreamError,
)
from story_engine.llm.local_client import LocalLLMClient

_logger = logging.getLogger(__name__)

# 空产出（同一模型）重试次数上限：首次 + 重试 1 次（PLAN §1.2）
_MAX_EMPTY_ATTEMPTS = 2


async def _guard_nonempty_stream(
    gen: AsyncGenerator[str, None], model: str
) -> AsyncGenerator[str, None]:
    """provider 无关的空产出守卫（评审 P1-3）。

    远程客户端有自己的守卫，本地客户端没有；统一在 router 兜住，避免"默认模型"
    路径仍然静默返回空正文。首个非空白 token 出现前先缓冲空白，保证重试不会
    重复下发内容。
    """
    pending: List[str] = []
    chars = 0
    async for chunk in gen:
        if chars == 0:
            pending.append(chunk)
            chars += len(chunk.strip())
            if chars > 0:
                for item in pending:
                    yield item
                pending = []
        else:
            yield chunk
    if chars == 0:
        raise LLMEmptyOutputError(f"模型 {model} 返回空产出（流式零 token）")


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

    async def _chat_with_retry(self, name: str, request: LLMRequest) -> LLMResponse:
        """单模型非流式调用：空产出时在该模型上重试 1 次（评审 P1-4）。

        - 客户端自报（`empty_output=True`）
        - 兜底：`success=True` 但 content 全空白（本地客户端无自己的守卫，评审 P1-3）
        """
        client = self._clients[name]

        async def _call(attempt: int) -> LLMResponse:
            result = await client.chat(request)
            if result.success and not (result.content or "").strip():
                return LLMResponse(
                    success=False,
                    provider=result.provider,
                    model=result.model,
                    usage=result.usage,
                    empty_output=True,
                    error="模型返回空产出（content 为空）"
                    + ("，已重试 1 次" if attempt > 1 else ""),
                )
            return result

        result = await _call(1)
        if not result.empty_output:
            return result

        _logger.warning("模型 %s 返回空产出，重试 1 次：%s", name, (result.error or "")[:120])
        return await _call(2)

    async def chat(
        self,
        request: LLMRequest,
        model_name: Optional[str] = None,
        fallback: bool = True,
    ) -> LLMResponse:
        """发送请求到指定模型，失败时可 fallback 到下一个可用模型。

        空产出先在同一模型上重试 1 次（多为思考模式耗尽 max_tokens 的瞬时问题），
        再次空产出才 fallback（PLAN §1.2）。

        返回聚合诊断信息：全部失败时 error 包含各模型原始错误（去敏，不含
        API Key）；仅真实 fallback（指定模型失败后切到另一模型）才加前缀。
        """
        target = self._pick_target(model_name)
        attempted: List[str] = []
        errors: List[str] = []

        if target is not None:
            attempted.append(target)
            result = await self._chat_with_retry(target, request)
            if result.success or not fallback:
                return result
            if result.error:
                errors.append(f"{target}: {result.error}")

        # 真实 fallback：指定了目标但失败后才切换到其他模型
        if fallback:
            for name in self._clients:
                if name in attempted:
                    continue
                attempted.append(name)
                result = await self._chat_with_retry(name, request)
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

        每个模型最多尝试 2 次（空产出重试 1 次，PLAN §1.2）。空产出守卫在 router 层
        统一兜住，本地/远程客户端都受保护（评审 P1-3）。错误以结构化形式抛出
        （`LLMStreamError`），由外层包装为 SSE error 事件，不再把 `[Error: ...]`
        混入正文（见 L5.3 / L8）。
        """
        target = self._pick_target(model_name)
        order: List[str] = []
        if target is not None:
            order.append(target)
        order.extend(name for name in self._clients if name not in order)

        errors: List[str] = []
        for name in order:
            if name == target and not (model_name and model_name != target):
                prefix = ""
            else:
                prefix = f"[Fallback → {name}]\n"

            for attempt in range(1, _MAX_EMPTY_ATTEMPTS + 1):
                try:
                    used = False
                    async for chunk in _guard_nonempty_stream(
                        self._clients[name].chat_stream(request), name
                    ):
                        if prefix and not used:
                            yield prefix
                            used = True
                        yield chunk
                    return  # 正常完成
                except LLMEmptyOutputError as e:
                    if attempt < _MAX_EMPTY_ATTEMPTS:
                        _logger.warning("模型 %s 空产出，重试 1 次：%s", name, e.message)
                        continue
                    errors.append(f"{name}: {e.message}（已重试 1 次）")
                    break
                except LLMStreamError as e:
                    errors.append(f"{name}: {e.message}")
                    break
                except Exception as e:  # noqa: BLE001 - 内部实现可能抛任意异常
                    errors.append(f"{name}: {e}")
                    break

        detail = "；".join(errors) if errors else "未找到可用模型"
        raise LLMStreamError(f"所有模型流式生成失败（{detail}）")

    async def close_all(self) -> None:
        for client in self._clients.values():
            try:
                await client.close()
            except Exception:
                pass
