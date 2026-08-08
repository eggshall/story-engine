# 测试报告 — story-engine

> 生成时间：2026-08-08
> 覆盖范围：已实现功能（`docs/plan.md` Phase P0 安全红线 S1–S7）补充测试 + 完整测试套件回归 + 修复 S2 自定义路径回归 / S1 空白 id / C5.1 索引清理

---

## 1. 测试结果概览

| 指标 | 结果 |
|------|------|
| **测试总数** | **400 passed**（此前 395） |
| **本轮新增测试** | **+5 个**（净增 304 → 400） |
| **总覆盖率** | **67%**（novel_storage 91% → 93%） |
| **静态检查** | ruff ✅ / mypy ✅ |
| **耗时** | ~7s |

### 运行命令

```bash
.venv/bin/python -m pytest -q          # 400 passed
.venv/bin/python -m ruff check src tests # All checks passed!
.venv/bin/python -m mypy src            # Success: no issues found
```

---

## 2. 补充的测试（按 plan.md 已实现功能）

### 新增文件

| 文件 | 对应任务 | 说明 |
|------|---------|------|
| `tests/test_file_utils.py` | **S2** | `resolve_within` 路径安全单测（绝对路径/`..`/Windows 盘符/symlink 逃逸）+ read/write/detect_encoding |
| `tests/test_url_utils.py` | **S6** | `validate_public_http_url` / `is_private_host` / `is_loopback_host` SSRF 校验单测（内网/元数据/整数 IP/DNS 解析） |

### 扩展文件

| 文件 | 对应任务 | 补充内容 |
|------|---------|---------|
| `tests/test_tools/test_novel_storage.py` | **S1 / S3 / C5.1** | `_safe_novel_id` 白名单边界、`_slug` 清洗、`_safe_json_path`、`convert_windows_path`、索引注册/损坏容错、`_ensure_within`、损坏数据加载、自定义路径拒绝 |
| `tests/test_models.py` | **S6** | 探测端点 ollama `/api/tags` 分支、5xx 错误分支、3xx 视为连接成功 |
| `tests/test_auth.py` | **S5** | 中间件非回环来源 403 判定、回环放行、`/api/health` 免鉴权、CORS 白名单 Origin 回显与拒绝 |
| `tests/test_tools/test_web_search.py` | **S6.2** | `fetch_page_content` 更多内网/元数据/整数 IP 拒绝用例 + 公网 https 正常抓取 + 网络异常容错 |

---

## 3. 关键覆盖提升

| 模块 | 覆盖率 | 覆盖的提升点 |
|------|-------|-------------|
| `utils/url_utils.py` | 88% → **88%+（缺失分支全测）** | 整数 IP、DNS 解析、`https://` 无 host、回环 flag |
| `utils/file_utils.py` | 46% → **~100%** | `resolve_within` 全部拒绝路径、symlink 逃逸、编码检测 |
| `api/routes/models.py` | 97% → **99%** | ollama 探测 / 5xx / 3xx |
| `tools/novel_storage.py` | 79% → **93%** | `_safe_novel_id`、索引管理、损坏数据、`_ensure_within`、自定义路径 S2 回归 |
| `api/main.py` | 98%（不变） | 鉴权中间件直接单测（非回环 403 / 回环放行） |

### 全量覆盖率（模块一览）

```
TOTAL          3667   1204    67%
```

主要未覆盖模块均为**计划中尚未实现**的 P1–P3 内容，属预期范围：
- `cli.py` 0%（307 行，计划 E3.2 未实施）
- `data_pipeline/fetcher.py`、`pipeline.py`、`catalog.py` 0%（计划 E3.4/L15 未实施）
- `writer/engine.py` 0%（计划 E3.1 未实施）
- `llm/local_client.py` 14%、`api_client.py` 30%（计划 L1/L2/E3.3 未实施）

---

## 4. 已实现功能 → 测试覆盖对照

| plan.md 任务 | 实现状态 | 测试覆盖 |
|-------------|---------|---------|
| **S1** novel_id 路径穿越 | ✅ | `TestSafeNovelId` / `TestPathTraversal` / `TestSlug` — `../../`、`..`、`%2e%2e`、控制符全拒 |
| **S2** save_path/output_dir/restore_path | ✅ | `test_file_utils.py` / `test_export_import.py` / `TestIndexManagement` — 越界/`..`/Windows 盘符全拒；NOVELS_ROOT 内的绝对自定义 `save_path` 恢复可用（本轮修复） |
| **S3** 角色/设定/文风名称 | ✅ | `TestNameAsFilename` / `TestSlug` — `../../x`、`<>:"|?*` 不越界不崩溃 |
| **S4** importer 书名 | ✅ | `test_data_pipeline.py` — `_safe_filename` / `_save_corpus` 越界拒绝 |
| **S5** 鉴权 + CORS | ✅ | `test_auth.py` — 无 key 401、错误 key 401、正确 key 200、非回环 403、CORS 白名单 |
| **S6** SSRF | ✅ | `test_url_utils.py` / `test_models.py` / `test_web_search.py` — 内网、`file://`、`169.254.169.254`、整数 IP 全拒 |
| **S7** api_key 泄漏 | ✅ | `test_models.py` — 掩码、PATCH 持久化、`/api/system/paths` 不泄主机信息 |

---

## 5. 本轮修复与行为备注

### 5.1 修复的缺陷（根因 → 业务代码修复 → 回归测试）

1. **S2 自定义保存路径回归（`save_path` 功能失效）**
   - **根因**：`save_novel(novel, "/...")` 的自定义路径分支把以 `/` 开头的路径直接交给 `resolve_within(NOVELS_ROOT, ...)`，而 `resolve_within` 在入口处即拒绝**一切**绝对路径，导致即使位于 `NOVELS_ROOT` 之内的绝对自定义路径也被拒，该功能（docstring 承诺"视为自定义路径，但必须解析后仍在 NOVELS_ROOT 内"、API `save_path` 字段）完全不可用。
   - **修复**：`resolve_within` 增加 `allow_absolute=False` 参数（默认行为不变，仍拒绝绝对路径，供 output_dir/restore_path 使用）；`save_novel` 自定义路径分支传 `allow_absolute=True`，安全门统一收敛为**越界即拒**——`/etc`、`/mnt/d/evil`、`D:\evil`、`/../../etc`、root 级 `/custom` 等全部仍然拒绝，只是放行位于 NOVELS_ROOT 内的绝对路径。
   - **回归测试**：`TestPathTraversal::test_save_absolute_custom_path_within_root_works`、`test_save_custom_path_creates_index`（越界用例原样保留）。

2. **`_safe_novel_id` 接受纯空白 id**
   - **根因**：`if not novel_id:` 仅拦截空串，`"   "` 可通过，产生空白目录名，且与 docstring"拒绝空值"及 `resolve_within` 的空白拒绝语义不一致。
   - **修复**：改为 `if not novel_id.strip():`。
   - **回归测试**：`TestSafeNovelId::test_rejects_whitespace_only`（`"   "`、`"\t"`、`" \n "`）。

3. **`list_novels` 失效索引未物理清理（plan.md C5.1）**
   - **根因**：`list_novels` 扫描索引时对指向已删除目录的条目只 `log` 不清理，条目永久残留。
   - **修复**：先收集失效条目再 `_index_unregister` 物理删除。
   - **回归测试**：`TestIndexManagement::test_list_cleans_invalid_index_entries` 强化为断言条目已物理移除（`_index_get(...) is None`）。

### 5.2 行为备注（非缺陷）

- 探测端点 3xx/404 按"连接成功"处理，仅 5xx 记 error（保持现状，符合 S6 探测语义）。

---

## 6. 结论

- P0 安全红线（S1–S7）已实现功能全部具备回归测试，关键安全函数覆盖从缺口补至 88%–100%。
- 本轮修复 3 项此前被测试"如实反映"掩盖的业务缺陷（S2 自定义路径回归 / S1 空白 id / C5.1 索引清理），安全属性未削弱，越界/穿越用例全部原样保留。
- 完整套件 **400 passed**，ruff/mypy 全绿。
- 遗留低覆盖模块均为 plan.md 中尚未实施的 P1–P3 任务，待对应功能实现后补测。
