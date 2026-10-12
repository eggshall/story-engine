"""数据目录覆盖（`STORY_DATA_DIR`）—— 让浏览器 E2E 不再往**真实** `data/` 里写。

背景（实测）：`data_dir()` 原先硬编码 `项目根/data`，于是 E2E 跑出来的小说会落在作者真实的
作品列表里。表现为列表里多出一本「未命名作品」（1 章「试炼」/ 正文「擂台之上」）——
那正是 **`generate` 端点没收到 `novel_id` 时会落盘的一本临时书**（`api/routes/generate.py`）。

关键点：`NOVELS_ROOT` / `LIBRARY_DIR` / `STYLE_DB_DIR` 等都是**模块级常量、导入期求值**，
所以覆盖必须在**进程启动前**由环境变量给定 —— 命中这一个，全部派生路径一起被隔离。
最后一条用**子进程**验证，因为进程内再设环境变量已经晚了（常量早算完了）。
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from story_engine.core import config as cfg


def test_default_is_project_data_dir():
    """没设覆盖时 = 项目根/data（原有行为不变）。"""
    assert "STORY_DATA_DIR" not in os.environ
    assert cfg.data_dir() == cfg.project_root() / "data"


def test_env_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("STORY_DATA_DIR", str(tmp_path / "e2e-data"))
    assert cfg.data_dir() == tmp_path / "e2e-data"


def test_env_override_expands_user(monkeypatch):
    monkeypatch.setenv("STORY_DATA_DIR", "~/story-e2e-data")
    assert cfg.data_dir() == Path("~/story-e2e-data").expanduser()


def test_empty_env_falls_back(monkeypatch):
    """空串按"没设"处理 —— 否则空值会变成 CWD，把数据写到莫名其妙的地方。"""
    monkeypatch.setenv("STORY_DATA_DIR", "")
    assert cfg.data_dir() == cfg.project_root() / "data"


def test_derived_paths_follow_the_override_in_a_fresh_process(tmp_path):
    """**导入期**求值的派生常量必须跟着走（这才是隔离真正生效的证明）。"""
    override = tmp_path / "iso"
    code = (
        "from story_engine.core.config import data_dir;"
        "from story_engine.tools.novel_storage import NOVELS_ROOT;"
        "from story_engine.lore.library import LIBRARY_DIR;"
        "print(data_dir());print(NOVELS_ROOT);print(LIBRARY_DIR)"
    )
    env = {**os.environ, "STORY_DATA_DIR": str(override)}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env, check=True
    ).stdout.splitlines()

    assert out == [str(override), str(override / "novels"), str(override / "library" / "lore")]
