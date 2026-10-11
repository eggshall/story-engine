"""E2E 共用的"假上游"+ 真实 HTTP 栈工具。

`tests/e2e/*` 的用例要覆盖**跨进程链路**，但不应该依赖外网/花钱/看运气：

    真实 socket(uvicorn) ←httpx→ FastAPI 中间件(校验 X-API-Key) → 路由 → Router
      → 真实 OpenAIClient → 本地假上游(OpenAI 兼容 HTTP server)

本模块提供三样东西：

- `FakeUpstream`：OpenAI 兼容的假模型服务，返回大纲 JSON（非流式）与
  可切换的流式分片，并记录每个请求的**完整请求体**（用于断言"线上真正
  发出去的是什么"，而不是只看单测里的 mock）。
- `write_config`：写一份临时 config.yaml（含 `security.api_key` 与指向假
  上游的模型），不依赖项目真实配置。
- `real_http_stack`：起真实 uvicorn（随机端口）并把 `core.config` 的
  `DEFAULT_CONFIG_PATH` / 全局 router 换成临时配置，退出时还原。

注意：假上游只做协议层，不含任何模型语义；因此用例可以断言"协议与契约"，
不能断言"模型质量"。
"""

from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, Iterator, List, Tuple

import uvicorn

FAKE_OUTLINE: Dict[str, Any] = {
    "chapter_number": 1,
    "title": "试炼",
    "summary": "主角进入试炼场",
    "beats": ["入场", "冲突"],
    "key_scenes": ["擂台"],
    "word_estimate": 400,
}

# 流式正常产出的分片（拼接后 = "擂台之上"）
OK_TOKENS: List[str] = ["擂台", "之上"]

# 流式"空产出"：只有 reasoning_content，没有任何 content（复现故障现场）
EMPTY_REASONING_TOKENS: List[str] = ["思考0", "思考1", "思考2"]


class _UpstreamHandler(BaseHTTPRequestHandler):
    """OpenAI 兼容：非流式返回大纲 JSON，流式按 mode 返回分片。"""

    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # 静音
        pass

    def do_POST(self):  # noqa: N802
        server = self.server
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            body = {}
        server.requests.append({"path": self.path, "body": body, "raw": raw})  # type: ignore[attr-defined]
        if getattr(server, "verbose", False):
            print(
                f"[fake-upstream] POST {self.path} stream={bool(body.get('stream'))} mode={server.mode}",  # type: ignore[attr-defined]
                flush=True,
            )

        if body.get("stream"):
            self._stream(server.mode)  # type: ignore[attr-defined]
        else:
            self._json_outline()

    def _json_outline(self) -> None:
        payload = json.dumps(
            {
                "model": "fake-model",
                "choices": [
                    {
                        "message": {
                            "content": f"```json\n{json.dumps(FAKE_OUTLINE, ensure_ascii=False)}\n```"
                        }
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _stream(self, mode: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()

        def frame(delta: dict) -> bytes:
            return f"data: {json.dumps({'choices': [{'delta': delta}]}, ensure_ascii=False)}\n\n".encode()

        if mode == "empty":
            for i, think in enumerate(EMPTY_REASONING_TOKENS):
                self.wfile.write(frame({"reasoning_content": f"{think}{i}"}))
                self.wfile.flush()
        else:
            for piece in OK_TOKENS:
                self.wfile.write(frame({"content": piece}))
                self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class FakeUpstream:
    """本地假上游服务（可切换 empty / ok 模式）。

    `port=0` 时由系统分配（测试用）；开发栈脚本传固定端口，好让临时配置里的
    `base_url` 提前确定。
    """

    def __init__(self, port: int = 0, verbose: bool = False) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", port), _UpstreamHandler)
        self.server.requests = []  # type: ignore[attr-defined]
        self.server.mode = "empty"  # type: ignore[attr-defined]
        self.server.verbose = verbose  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    @property
    def base_url(self) -> str:
        port = self.server.server_address[1]
        return f"http://127.0.0.1:{port}/v1"

    @property
    def requests(self) -> List[dict]:
        return self.server.requests  # type: ignore[attr-defined]

    def set_mode(self, mode: str) -> None:
        self.server.mode = mode  # type: ignore[attr-defined]

    def stream_requests(self) -> List[dict]:
        """只要流式请求（生成正文的那次），用于断言重试次数与请求体。"""
        return [r for r in self.requests if r["body"].get("stream")]

    def clear(self) -> None:
        self.requests.clear()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def write_config(
    tmp_path: Path,
    upstream_base: str,
    api_key: str,
    model_name: str = "fake",
) -> Path:
    """写临时 config.yaml：鉴权 key + 一个指向假上游的模型。

    provider 用 `deepseek` 是为了走 `OpenAIClient`（与线上远程模型同一条代码路径，
    包括 thinking 字段与流式解析）。
    """
    import yaml

    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "security": {"api_key": api_key},
                "llm": {
                    "default_model": model_name,
                    "models": [
                        {
                            "name": model_name,
                            "provider": "deepseek",
                            "model_id": "fake-model",
                            "base_url": upstream_base,
                            "api_key": "upstream-key",
                            "enabled": True,
                        }
                    ],
                },
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return path


@contextmanager
def real_http_stack(config_path: Path) -> Iterator[str]:
    """起真实 uvicorn（随机端口）并把全局配置指向 `config_path`，yield base_url。

    - 真实 socket + 真实 ASGI 栈（不是 TestClient 进程内调用）
    - 退出时还原 `DEFAULT_CONFIG_PATH`、配置单例与全局 router
    """
    import story_engine.api.routes.generate as gen_route
    import story_engine.core.config as cfg_mod
    from story_engine.api.main import app

    orig_path = cfg_mod.DEFAULT_CONFIG_PATH
    orig_instance = getattr(cfg_mod, "_config_instance", None)
    orig_router = gen_route._router
    cfg_mod.DEFAULT_CONFIG_PATH = config_path
    cfg_mod._config_instance = None
    gen_route._router = None

    uv_config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
    server = uvicorn.Server(uv_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    for _ in range(200):
        if server.started and server.servers:
            break
        time.sleep(0.05)
    else:  # pragma: no cover
        raise RuntimeError("uvicorn 未能在 10s 内启动")

    port = server.servers[0].sockets[0].getsockname()[1]
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        cfg_mod.DEFAULT_CONFIG_PATH = orig_path
        cfg_mod._config_instance = orig_instance
        gen_route._router = orig_router


def parse_sse_events(body: str) -> List[Tuple[str, Any]]:
    """把 SSE 响应体解析成 [(event, payload), ...]（payload 是 JSON 对象）。"""
    events: List[Tuple[str, Any]] = []
    current = ""
    for line in body.splitlines():
        if line.startswith("event: "):
            current = line[7:].strip()
        elif line.startswith("data: "):
            raw = line[6:].strip()
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = {"_raw": raw}
            events.append((current, payload))
    return events
