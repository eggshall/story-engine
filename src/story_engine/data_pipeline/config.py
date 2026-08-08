"""P6 数据管线 — 路径配置。

所有采集数据统一存于 D:/文章数据 (WSL 挂载 /mnt/d/文章数据)。
可通过环境变量 STORY_ENGINE_DATA_ROOT 覆盖（L17.3）。
"""
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger("story_engine.pipeline.config")

# D 盘数据根目录：优先环境变量注入，否则默认 WSL 挂载路径（L17.3）
_DATA_ROOT_ENV = "STORY_ENGINE_DATA_ROOT"

_DEFAULT_DATA_ROOT = Path("/mnt/d/文章数据")


def _resolve_data_root() -> Path:
    """解析数据根目录：环境变量注入优先，失败给清晰提示后回退默认。

    L17.3: 环境变量为绝对路径时直接采用；非绝对路径视为配置注入失败，
    同时在日志与 stderr 输出可操作的提示（CLI 场景 logger 可能未配置 handler）。
    """
    env = os.environ.get(_DATA_ROOT_ENV, "").strip()
    if env:
        root = Path(env)
        if root.is_absolute():
            return root
        message = (
            f"环境变量 {_DATA_ROOT_ENV} 必须是绝对路径（收到 {env!r}），"
            f"已忽略该值并回退到默认数据根目录 {_DEFAULT_DATA_ROOT}"
        )
        logger.warning(message)
        print(f"⚠ {message}", file=sys.stderr)
    return _DEFAULT_DATA_ROOT


DATA_ROOT = _resolve_data_root()

# 子目录
RAW_DIR = DATA_ROOT / "raw"          # 原始下载文件
CORPUS_DIR = DATA_ROOT / "corpus"    # 清洗后语料（按 题材/作者/作品.txt 组织）
IMPORTS_DIR = DATA_ROOT / "imports"  # 用户导入投放区（网络小说等自有文本）
META_DIR = DATA_ROOT / "meta"        # 元数据索引
LOGS_DIR = DATA_ROOT / "logs"        # 管线日志

# 索引文件
INDEX_FILE = META_DIR / "index.json"          # 语料主索引
CATALOG_FILE = META_DIR / "gutenberg_catalog.json"  # Gutenberg 中文书目

# 题材标签体系（用户要求覆盖的四大类）
GENRES = {
    "serious": "严肃文学",
    "humor_satire": "幽默讽刺",
    "tragic": "悲伤文学",
    "popular": "流行文学",
    "other": "其他",
}

# 来源类别
SOURCES = {
    "gutenberg": "Gutenberg 中文公版库",
    "ctext": "中国哲学书电子化计划(古籍)",
    "import": "用户导入(网络小说/自有文本)",
}


def ensure_dirs() -> None:
    """确保所有目录存在。"""
    for d in (RAW_DIR, CORPUS_DIR, IMPORTS_DIR, META_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)
