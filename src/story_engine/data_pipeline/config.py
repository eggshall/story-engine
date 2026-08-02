"""P6 数据管线 — 路径配置。

所有采集数据统一存于 D:/文章数据 (WSL 挂载 /mnt/d/文章数据)。
"""
from pathlib import Path

# D 盘数据根目录（用户指定）
DATA_ROOT = Path("/mnt/d/文章数据")

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
    "other": "其他/未分类",
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
