"""N1 E2E（真实 HTTP + 真实鉴权）：空产出走 error 事件、且请求体确实关闭思考。

评审 P1-5 指出原来的 TestClient 用例不达 §9.3 的 E2E 标准，本文件补齐：

    真实 socket(uvicorn) ←httpx→ FastAPI 中间件(校验 X-API-Key) → 路由 → Router
      → 真实 OpenAIClient → **本地假上游**(OpenAI 兼容 HTTP server)

因此覆盖了：鉴权头、真实 HTTP 传输、SSE 解析、以及"线上真正发出去的请求体"。
假上游只做协议层（不调真模型、不花钱、不依赖网络）。
"""

from __future__ import annotations

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
import pytest
import uvicorn

from story_engine.api.main import app

pytestmark = pytest.mark.e2e

API_KEY = "e2e-test-key"

FAKE_OUTLINE = {
    "chapter_number": 1,
    "title": "试炼",
    "summary": "主角进入试炼场",
    "beats": ["入场", "冲突"],
    "key_scenes": ["擂台"],
    "word_estimate": 400,
}


class _UpstreamHandler(BaseHTTPRequestHandler):
    """OpenAI 兼容的假上游：记录请求体，按 mode 返回空流或正常内容。"""

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
            # 复现故障：只有 reasoning_content，没有任何 content token
            for i in range(3):
                self.wfile.write(frame({"reasoning_content": f"思考{i}"}))
                self.wfile.flush()
        else:
            for piece in ["擂台", "之上"]:
                self.wfile.write(frame({"content": piece}))
                self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


class FakeUpstream:
    def __init__(self) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _UpstreamHandler)
        self.server.requests = []  # type: ignore[attr-defined]
        self.server.mode = "empty"  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def base_url(self) -> str:
        port = self.server.server_address[1]
        return f"http://127.0.0.1:{port}/v1"

    @property
    def requests(self) -> list[dict]:
        return self.server.requests  # type: ignore[attr-defined]

    def set_mode(self, mode: str) -> None:
        self.server.mode = mode  # type: ignore[attr-defined]

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()


def _write_config(tmp_path, upstream_base: str):
    import yaml

    path = tmp_path / "config.yaml"
    path.write_text(
        yaml.dump(
            {
                "security": {"api_key": API_KEY},
                "llm": {
                    "default_model": "fake",
                    "models": [
                        {
                            "name": "fake",
                            "provider": "deepseek",  # 走 OpenAIClient + thinking 字段
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


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    """真实 uvicorn(真实 socket) + 假上游 + 临时配置（含 security.api_key）"""
    import story_engine.api.routes.generate as gen_route
    import story_engine.core.config as cfg_mod

    upstream = FakeUpstream()
    cfg_path = _write_config(tmp_path_factory.mktemp("e2e"), upstream.base_url)

    orig_path = cfg_mod.DEFAULT_CONFIG_PATH
    orig_instance = getattr(cfg_mod, "_config_instance", None)
    orig_router = gen_route._router
    cfg_mod.DEFAULT_CONFIG_PATH = cfg_path
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
    base = f"http://127.0.0.1:{port}"

    yield base, upstream

    server.should_exit = True
    thread.join(timeout=10)
    upstream.close()
    cfg_mod.DEFAULT_CONFIG_PATH = orig_path
    cfg_mod._config_instance = orig_instance
    gen_route._router = orig_router


def test_requires_api_key_over_real_http(stack):
    """真实 HTTP + 鉴权：无 X-API-Key 必须 401（否则这套 E2E 没有测到鉴权链路）"""
    base, _upstream = stack

    resp = httpx.post(f"{base}/api/generate/chapter", params={"chapter_number": 1}, timeout=30)

    assert resp.status_code == 401


def test_empty_stream_returns_error_event_and_no_done(stack):
    """空产出：真实 HTTP 下必须 event: error（含原因）且没有 event: done"""
    base, upstream = stack
    upstream.set_mode("empty")

    resp = httpx.post(
        f"{base}/api/generate/chapter",
        params={"chapter_number": 1},
        headers={"X-API-Key": API_KEY},
        timeout=60,
    )

    assert resp.status_code == 200
    body = resp.text
    assert "event: error" in body, body[:800]
    assert "event: done" not in body, body[:800]

    # 事件体是 JSON（中文转义为 \uXXXX），解析后再断言
    payloads = [json.loads(line[6:]) for line in body.splitlines() if line.startswith("data: ")]
    errors = " ".join(str(p.get("error", "")) for p in payloads)
    assert "空产出" in errors, payloads

    # 线上真正发出去的请求体：必须关闭思考（否则 reasoning 会吃掉 max_tokens）
    stream_calls = [r for r in upstream.requests if r["body"].get("stream")]
    assert stream_calls, "假上游没有收到流式请求"
    assert stream_calls[-1]["body"]["thinking"] == {"type": "disabled"}
    assert "reasoning_effort" not in stream_calls[-1]["body"]
    # P1-4：空产出确实在真实链路上重试了 1 次（上游收到 2 次流式请求）
    assert len(stream_calls) == 2, [r["body"].get("stream") for r in upstream.requests]


def test_success_stream_returns_tokens_and_done(stack):
    """对照：有 token 时正常下发并补 done（证明上面的 error 不是"永远失败"）"""
    base, upstream = stack
    upstream.set_mode("ok")

    resp = httpx.post(
        f"{base}/api/generate/chapter",
        params={"chapter_number": 1},
        headers={"X-API-Key": API_KEY},
        timeout=60,
    )

    body = resp.text
    assert "event: error" not in body, body[:800]
    assert "擂台" in body and "之上" in body
    assert "event: done" in body
