#!/usr/bin/env python
"""只读核验：真实 config.yaml 经 Config 加载后，本地模型的 read_timeout 是否保住了。

N3 修的就是"配置里写的 300s 被白名单静默改成全局 120s"。这里连 Config + 路由构建
一起走一遍，只打印与超时/任务相关的**非密钥**字段。
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from story_engine.core.config import DEFAULT_CONFIG_PATH, Config  # noqa: E402


def main() -> int:
    cfg = Config(DEFAULT_CONFIG_PATH)
    models = cfg.get("llm.models", []) or []
    print(f"config: {DEFAULT_CONFIG_PATH}")
    print(f"llm.connect_timeout={cfg.get('llm.connect_timeout')} "
          f"llm.read_timeout={cfg.get('llm.read_timeout')}")
    for m in models:
        print(
            f"  - {m.get('name'):<20} provider={m.get('provider'):<9} "
            f"read_timeout={m.get('read_timeout', '(未设置→用全局)')} "
            f"task={m.get('task', '(未设置)')} thinking={m.get('thinking', '(未设置)')} "
            f"weight={m.get('weight')} enabled={m.get('enabled')}"
        )
    local = [m for m in models if m.get("provider") == "local"]
    if local:
        rt = local[0].get("read_timeout")
        print(f"\n本地模型 read_timeout 实际生效值: {rt}（修复前会被剥离成全局 "
              f"{cfg.get('llm.read_timeout')}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
