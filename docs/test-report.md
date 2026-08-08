# 测试报告 — story-engine

> 生成时间：2026-08-08
> 覆盖范围：**Phase P2 工程健康（E1–E6）** 全部完成 + 完整套件回归（含此前 P0 S1–S7、P1 L1–L10 全部测试）+ P1 遗留的 lint/type 修复

---

## 1. 测试结果概览

| 指标 | 结果 |
|------|------|
| **测试总数** | **605 passed**（上一阶段 542） |
| **本轮新增测试** | **+63 个**（净增 542 → 605） |
| **总覆盖率** | **90.28%**（上一阶段 83%，全量 `--cov-fail-under=75` 门禁已启用） |
| **静态检查** | ruff ✅ / mypy ✅ |
| **警告** | 0（StarletteDeprecationWarning 已过滤） |
| **耗时** | ~5s |

### 运行命令

```bash
.venv/bin/python -m pytest -q          # 605 passed, 90.28% (门禁 75%)
.venv/bin/python -m ruff check src tests # All checks passed!
.venv/bin/python -m mypy src            # Success: no issues found
```

---

## 2. Phase P2 完成内容（E1–E6 全勾）

本轮按 `docs/plan.md` Phase P2 剩余项逐项落地，核心是可测试性 + 工程门禁：

### E2.3 测试隔离 — 联网用例 mock
- **`tests/test_research.py`** 全面重写：`research.search_web` 替换为可控 `AsyncMock`（假 `SearchResponse`），**彻底移除真实网络依赖**，CI 幂等。
- 断言细化为精确断言（不再依赖网络返回真值）：mock 参数透传、落盘文件校验、`save_to_lore` 的 `category` 记录、空结果不抛错。
- 新增边界：损坏 JSON 文件跳过、`limit/offset` 分页、`limit>200` 返回 422。

### E3.4 数据管线核心流程（0% → ~95%）
新增 `tests/test_data_pipeline_core.py`（32 用例，全部离线 mock，不触碰 `/mnt/d` 真实数据）：

| 模块 | 覆盖 | 本轮覆盖点 |
|------|------|-----------|
| `fetcher.py` | 0% → **100%** | 下载/已存在短路/过小重下/HTTP 错误/批量单点失败 |
| `importer.py` | 29% → **96%** | 书名清洗、GBK/UTF-8 解码、HTML→文本、epub 合集拆分（ncx 损坏兜底）、目录多分卷合并、扫描失败不中断、归档覆盖 |
| `pipeline.py` | 0% → **99%** | `_genre_dir`、`collect_one`（下载→清洗→落盘→登记）、清洗为空抛错、`collect` 题材过滤与单本失败容错、`main` 四分支 |
| `catalog.py` | 0% → **87%** | 抓取解析、保存/加载、不存在时抓取并落盘 |
| `index.py` / `cleaner.py` | → 94% / 89% | 既有用例回归覆盖 |

### E3.5 关键模块补测
- **`api/sse.py`**：`event_stream()` 此前已 **100%**（token/done/error 事件、`LLMStreamError` 转 error、断开 aclose 清理）。
- **`style/analyzer.py`**（62% → **95%**）：新增 `tests/test_style_analyzer.py`（21 用例）覆盖 `analyze_style`（JSON 成功/坏 JSON 兜底/长文本截断）、`check_consistency`（含无风格信息、features 兜底、坏响应兜底）、`generate_style_prompt`、`_chat`（think 块剥离、错误脱敏）、`_get_client`/`close`、`_extract_json`、`_features_to_prompt`、`render_style_block`。
- **`api/routes/system.py`**（96% → **98%**）：补 Windows 用户探测 + E 盘挂载 → 桌面/文档/下载/D:/E: 建议分支、无用户时仅 D:/ 建议（monkeypatch 辅助函数，不依赖真实 `/mnt`）。

### E3.6 遗留低覆盖点
- **`llm/base.py`**（98% → **100%**）：`__repr__`、`close()` 抽象方法强制约束（未实现子类无法实例化）、实现可调用。
- **`llm/router.py close_all()`**：已有幂等/空 router/异常吞除测试，**100%**。
- **`style/recommend.get_genre_prototypes`**（84% → **97%**）：非空库返回题材→原型向量（13 维、0-1 归一化）、空库返回 `{}`。

### E4 coverage 门禁
- `pyproject.toml` 新增 `[tool.coverage.run]`（`source=["story_engine"]`）+ `[tool.coverage.report]`（`fail_under=75`）。
- `[tool.pytest.ini_options] addopts = "--cov=story_engine --cov-report=term-missing --cov-fail-under=75"`：本地/CI 低于 75% 即失败。

### E5 文档与版本同步
- `README.md`：测试数（605/覆盖率 90%+）、项目结构补齐 `style`/`data_pipeline`/`tools`/`utils`、补 uvicorn 启动命令与安全提示。
- `pyproject.toml` + `src/story_engine/__init__.py`：version `0.1.0` → **`0.8.0`**（与 CHANGELOG 对齐）。
- `.gitignore`：补 `.mypy_cache/`、`.ruff_cache/`，删死条目 `src/frontend/dist/`。

### E6.1 警告处理
- starlette 1.3.x 在未安装 `httpx2` 时对 `starlette.testclient` 发出的 `StarletteDeprecationWarning`（httpx2 尚未发布，无法升级消除）→ pytest `filterwarnings` 定向过滤，测试输出 0 警告。

---

## 3. 全量覆盖率（本轮回归）

```
TOTAL          3849    374    90%
```

关键模块（P2 重点补测）：

| 模块 | 覆盖率 | 模块 | 覆盖率 |
|------|-------|------|-------|
| `data_pipeline/fetcher.py` | 100% | `style/analyzer.py` | 95% |
| `data_pipeline/importer.py` | 96% | `style/recommend.py` | 97% |
| `data_pipeline/pipeline.py` | 99% | `llm/base.py` | 100% |
| `data_pipeline/catalog.py` | 87% | `llm/router.py` | 100% |
| `api/sse.py` | 100% | `api/routes/system.py` | 98% |

剩余低覆盖模块（`tools/web_search.py` 58%、`api/routes/generate.py` 52%、`style.py` 69%）依赖 LLM/真实搜索引擎，属 P2 范围之外，留待 P3 按计划补测或接线。

---

## 4. 静态检查与卫生

- ruff ✅ / mypy ✅（本轮新增 5 处 import 排序/未用 import 由 `ruff --fix` 清理，0 残留）。
- 测试输出 0 警告（E6.1 过滤后）。

---

## 5. 结论

- **P2（E1–E6）全部完成**：`data_pipeline` 从 0% 补至 ~95%、`style/analyzer` 62%→95%、`llm/base`/`recommend` 补满、research 测试彻底离线化；coverage 门禁（75%）、文档/版本/`.gitignore` 同步到位。
- 完整套件 **605 passed（+63）**，总覆盖率 **83% → 90.28%**；ruff / mypy 全绿，0 警告。
- 遗留低覆盖模块均为需要真实 LLM/网络或 P3 接线的内容，属计划内范围。
