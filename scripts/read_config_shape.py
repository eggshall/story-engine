#!/usr/bin/env python
"""只读：打印 config.yaml 的**键名结构**，凡是含密钥的键一律用 <hidden> 屏蔽。

给开发/评审看配置形状用，避免把密钥打印到终端或日志里。
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

SECRET_HINTS = ("key", "token", "secret", "password", "cookie")


def mask(k: str, v):
    if any(h in k.lower() for h in SECRET_HINTS):
        return "<hidden>"
    return v


def dump(d, prefix: str = "") -> None:
    if isinstance(d, dict):
        for k, v in d.items():
            if isinstance(v, (dict, list)):
                print(f"{prefix}{k}:")
                dump(v, prefix + "  ")
            else:
                print(f"{prefix}{k}: {mask(str(k), v)}")
    elif isinstance(d, list):
        for i, item in enumerate(d):
            if isinstance(item, (dict, list)):
                print(f"{prefix}[{i}]")
                dump(item, prefix + "  ")
            else:
                print(f"{prefix}[{i}]: {item}")


def main() -> int:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "config/config.yaml")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    print(f"# {path}")
    dump(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
