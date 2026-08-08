# 测试报告 — story-engine

> 生成时间：2026-08-08
> 覆盖范围：**Phase P3 死代码清理/低优重构（C1–C5）** 全部完成 + 完整套件回归（含此前 P0 S1–S7、P1 L1–L17、P2 E1–E6 全部测试）

---

## 1. 测试结果概览

| 指标 | 结果 |
|------|------|
| **测试总数** | **592 passed**（上一阶段 605） |
| **本轮测试净变化** | **-13 个**（删除死代码相关测试 15 个 + 新增 C4 回归测试 2 个） |
| **总覆盖率** | **92.31%**（上一阶段 90.28%，**未下降**，随死代码删除而提升；门禁 75% 生效） |
| **静态检查** | ruff ✅ / mypy ✅ |
| **警告** | 0（StarletteDeprecationWarning 已过滤） |
| **耗时** | ~5.7s |

### 运行命令

```bash
.venv/bin/python -m pytest -q          # 592 passed, 92.31% (门禁 75%)
.venv/bin/python -m ruff check src tests # All checks passed!
.venv/bin/python -m mypy src            # Success: no issues found in 52 source files
```

---

## 2. Phase P3 完成内容（C1–C5 全勾）

本轮按 `docs/plan.md` Phase P3 逐项落地：死代码清理 + 数据模型统一 + 指标口径修复。**核心验证结论：清理后测试全绿、覆盖率不降反升（90.28% → 92.31%），删除的死代码均未在业务路径被调用。**

### C1. LLM/Core 层死代码
- 删除未消费的 `ModelConfig`/`LLMConfig`、`WritingMode`、重复 Lorebook 结构（`LoreEntry`/`CharacterLoreBook`，`CharacterCard.lorebook` 统一用 `LoreBook`/`LorebookEntry`）。
- 删除未消费的 `LLMRequest.stream`；`base.py` 的 `if False: yield` hack 改为标准异步生成器写法（`yield ""  # pragma: no cover`）。
- `local_client.py` 函数内 `import time` 移至模块顶部。

### C2. 工具层死代码
- 删除无调用代码：`web_search.py` 六处（`_search_so_mobile`/`_search_sogou_mobile`/`_search_duckduckgo`/`_VPN_ENDPOINTS`/`search_zhihu`/`search_wenku`）、`fixed_tasks.py` 三函数（`extract_keywords`/`summarize_chapter`/`compress_history`）、`prompts.py` 未用 `SEARCH_ASSIST_PROMPT`、`fetcher.download_many`/`cleaner.clean_file`/`index.find_by_id`；`catalog` 接入 `pipeline.py`（`_check_catalog` 校验书单）。
- `_SEARCH_ENGINES_CN`/`_INTL` 去重合并，拼接前按名称过滤消除 bing 双请求；删除未用循环变量的空跑正则循环。
- `_clean_url` docstring 与实现对齐。

### C3. 数据模型统一
- `tools/memory_models.StyleProfile`（小说维度量化画像）重命名为 `NovelStyleProfile`，`StyleProfile` 仅剩 `style/db.py` 一个。
- `fixed_tasks.check_consistency`（角色/地名正则校验）重命名为 `check_name_consistency`，`check_consistency` 仅剩 `StyleAnalyzer`（LLM 文风一致性）一个入口。

### C4. 指标口径修复
- `tools/style_analyzer.py` 四类百分比改为互斥（每句归入 对话/心理/动作/描写 四类之一），保证合计 = 1。
- 新增回归测试：`test_percentages_mutually_exclusive`（互斥）+ `test_percentages_sum_to_one`（合计 ≈ 1）。

### C5. 无效索引清理落地
- `novel_storage.list_novels` 真正移除失效索引条目（非只 log），`test_list_cleans_invalid_index_entries` 验证失效条目不入列表且物理清理。

---

## 3. 全量覆盖率（本轮回归）

```
TOTAL          3680    283    92%
```

关键模块（P3 清理后回归）：

| 模块 | 覆盖率 | 模块 | 覆盖率 |
|------|-------|------|-------|
| `data_pipeline/fetcher.py` | 100% | `tools/memory_models.py` | 100% |
| `data_pipeline/pipeline.py` | 95% | `tools/style_analyzer.py` | 92% |
| `data_pipeline/importer.py` | 96% | `tools/web_search.py` | **58% → 82%** |
| `data_pipeline/catalog.py` | 87% | `llm/base.py` | 100% |
| `api/sse.py` | 100% | `llm/router.py` | 100% |
| `api/routes/system.py` | 98% | `utils/file_utils.py` | 100% |

覆盖提升主要来自死代码删除（`web_search` 58%→82%、`fixed_tasks` 从 277+ 行缩减至 22 行等），P0 接线的 `file_utils.py` 保持 100%。剩余低覆盖模块（`api/routes/generate.py` 52%、`style.py` 69%）依赖真实 LLM 调用，属计划内范围。

---

## 4. 静态检查与卫生

- ruff ✅ / mypy ✅（P3 清理后 0 残留；52 源文件全部通过）。
- 测试输出 0 警告（E6.1 过滤后）。

---

## 5. 结论

- **P3（C1–C5）全部完成**：LLM/Core、工具层死代码删除（源码净删 431 行），数据模型统一（`NovelStyleProfile`/`check_name_consistency`），文风指标四类互斥合计=1，无效索引物理清理。
- 完整套件 **592 passed**，总覆盖率 **90.28% → 92.31%**（**未下降，随死代码删除而提升**）；ruff / mypy 全绿，0 警告。
- 测试数 -13 = 删除死代码对应测试 15 个（download_many 2 / extract_keywords 6 / summarize_chapter 4 / compress_history 3）+ 新增 C4 回归测试 2 个（互斥 + 合计≈1），**删除部分均未在业务路径被调用，无覆盖损失**。
- 遗留低覆盖模块（`api/routes/generate.py`、`style.py`）需真实 LLM 调用，属计划内范围，P0–P3 全部阶段完成。
