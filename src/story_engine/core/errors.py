"""跨模块共享的领域异常（N8 评审 P2-5 的处置）。

**为什么单独一个模块**：「小说不存在」不是某一层的私有概念——角色卡、伏笔账本、世界观都要在
「这本书不在」时给出同一种可读失败。此前 `NovelNotFound` 定义在 `characters/manager.py`，
`threads` 与 `lore` 为了共用同一个类而 `import` 它，于是**世界观反向依赖了角色卡**（两个业务上
毫无关系的模块），挪动/重命名任一方都会外溢。

定义在这里之后，三方都从这里取，同一个类，`except NovelNotFound` 仍能跨路由通用。
"""

from __future__ import annotations


class NovelNotFound(Exception):
    """小说不存在（调用方应转成用户可读的失败响应）。"""
