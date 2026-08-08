"""P6 数据管线模块。"""
from .config import DATA_ROOT, ensure_dirs

__all__ = ["DATA_ROOT", "ensure_dirs"]

ensure_dirs()
