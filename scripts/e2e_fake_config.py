#!/usr/bin/env python
"""为浏览器 E2E 生成一份"指向假上游"的临时 config.yaml。

为什么需要它：项目真实 `config/config.yaml` 里的模型指向线上 DeepSeek，
用它跑浏览器 E2E 会真实花钱、且输出不确定（正文不可断言）。本脚本生成一份
**只改模型指向**的临时配置：

- 原样保留 `security.api_key`（浏览器鉴权链路仍是真实的，但不打印内容）
- 把 `llm.models` 换成单个指向本地假上游的模型（provider=deepseek，走
  OpenAIClient 同一条代码路径）
- `llm.default_model` 指向该模型

用法（由 `scripts/e2e_dev_stack.sh --fake` 调用）:
    .venv/bin/python scripts/e2e_fake_config.py --fake-port 8899 --out /tmp/e2e_fake_config.yaml
输出：临时配置路径（只打印路径与模型名，不打印任何密钥）。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
REAL_CONFIG = ROOT / "config" / "config.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description="生成指向假上游的临时配置")
    parser.add_argument("--fake-port", type=int, required=True)
    parser.add_argument("--out", default="/tmp/e2e_fake_config.yaml")
    parser.add_argument("--model-name", default="e2e-fake")
    args = parser.parse_args()

    data = {}
    if REAL_CONFIG.exists():
        data = yaml.safe_load(REAL_CONFIG.read_text(encoding="utf-8")) or {}

    llm = data.setdefault("llm", {})
    llm["default_model"] = args.model_name
    llm["models"] = [
        {
            "name": args.model_name,
            "provider": "deepseek",  # 走 OpenAIClient（与线上远程模型同一实现）
            "model_id": "fake-model",
            "base_url": f"http://127.0.0.1:{args.fake_port}/v1",
            "api_key": "fake-upstream-key",
            "enabled": True,
            "temperature": 0.7,
            "max_tokens": 1024,
        }
    ]

    out = Path(args.out)
    # 0600：这份配置里含有真实 security.api_key（沿用项目配置），不能让同机其他用户/进程读到。
    # 用 os.open 一步到位创建（先 chmod 再写会有竞态窗口）。
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(out, flags, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(
            "# 自动生成：浏览器 E2E 用（模型指向本地假上游，鉴权 key 沿用真实配置）\n"
            + yaml.dump(data, allow_unicode=True, sort_keys=False)
        )
    # O_CREAT 的 mode 只对"新建"生效；若路径已存在且权限偏松（例如上一次用 0644 跑出来的），
    # 这里显式收紧一次，保证任何情况下都是 0600（评审 P1-3）。
    os.chmod(out, 0o600)
    has_key = bool((data.get("security") or {}).get("api_key"))
    # 只把路径打到 stdout（供脚本 $(...) 取值），其余信息走 stderr
    print(
        f"临时配置: {out} (0600) | default_model={args.model_name} | "
        f"security.api_key={'已沿用' if has_key else '缺失'}",
        file=sys.stderr,
    )
    print(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
