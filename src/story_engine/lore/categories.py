"""条目「类型」（`LorebookEntry.category`）的**后端定义处**。

## 事实（第五切片评审 P1-1 纠正过一次说法，别再写成"唯一定义处"）

- 前端 `src/frontend/src/views/WorldView.vue` 里的 `CATEGORY_OPTIONS` 是**第二份手抄字面量**
  —— 跨语言 import 不了，所以**不存在**"一处定义"这种保障；
- 两份表之间没有编译器帮忙，唯一的保障是一条测试：
  `tests/test_lore/test_lorebooks_api.py::TestCategoryVocabulary::test_frontend_vocabulary_matches_backend`
  **读 `.vue` 源码文本**把两份表逐项比对。**加 / 改 / 删类型必须同时改两处**，否则它必然红。
- 同理，`PLACE_CATEGORIES`（哪些类型算"地名"）是**后端独有**的语义，前端不需要知道 ——
  但前端唯一会写的「地点」必须在里面，那一条由 `test_place_category_feeds_the_place_check`
  与 `e2e/worldview.e2e.ts` 第 4b 步（真 HTTP）各钉一道。

## 两个消费方

1. 前端下拉框（**写**什么值）—— `WorldView.vue::CATEGORY_OPTIONS`
2. `api/routes/novel.py::api_check_consistency`（**认**什么值算地名）—— 本模块 `PLACE_CATEGORIES`

两边漂移就是"我明明把这条标成了地点、一致性检查却不认"的**静默失效**
（同类事故：N9 的驼峰字段被静默丢、N8 第四切片的 `category` 被前端抹掉）。
"""

from __future__ import annotations

# 「其他 / 未分类」的存储值 —— 与磁盘模型的默认值一致，**不要改**：
# 历史数据（含第四切片之前建的所有条目）都是这个值，改了老条目就会显示成未知类型。
DEFAULT_CATEGORY = "general"

# UI 下拉的取值（存储值 → 界面标签）。字典顺序即下拉顺序。
# 前端那份手抄表必须与本字典**逐项且同序**（由上面提到的那条测试把守）。
CATEGORY_LABELS: dict[str, str] = {
    "地点": "地点",
    "物品": "物品",
    "规则": "规则",
    "势力": "势力",
    "世界观": "世界观",
    DEFAULT_CATEGORY: "其他",
}

# 会被 `check_name_consistency` 当作**已知地名**的类型。
# 前端 UI 只写「地点」；其余几个是历史/英文写法，保留识别能力（老书里可能有）。
PLACE_CATEGORIES: frozenset[str] = frozenset(
    {"地理", "地点", "location", "geography", "place"}
)
