#!/usr/bin/env python
"""开发栈用的假上游（OpenAI 兼容，本地进程，不调真模型 / 不花钱）。

与 `tests/e2e/fake_upstream.py` 共用同一份协议实现 —— 保证"单测/E2E 里的假上游"
与"浏览器 E2E 开发栈里的假上游"行为一致，避免两套 stub 各自漂移。

用法:
    .venv/bin/python scripts/fake_upstream_server.py --port 8899
    # 前台常驻；Ctrl-C 结束。日志打印收到的请求路径（不含密钥）。
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

# 复用 tests/e2e 的假上游实现（脚本在仓库内运行，root 可推断）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tests.e2e.fake_upstream import FakeUpstream  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="本地假上游（OpenAI 兼容）")
    parser.add_argument("--port", type=int, default=8899, help="监听端口（默认 8899）")
    parser.add_argument("--mode", default="ok", choices=["ok", "empty"], help="流式响应模式")
    args = parser.parse_args()

    upstream = FakeUpstream(port=args.port, verbose=True)
    upstream.set_mode(args.mode)
    print(f"fake upstream 已启动: {upstream.base_url} (mode={args.mode})", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        upstream.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
