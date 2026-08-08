# 测试报告 — story-engine

> 生成时间：2026-08-08
> 覆盖范围：已实现功能（`docs/plan.md` Phase P0 安全红线 S1–S7）补充测试 + 完整测试套件回归

---

## 1. 测试结果概览

| 指标 | 结果 |
|------|------|
| **测试总数** | **395 passed**（此前 304） |
| **新增测试** | **91 个**（净增 304 → 395） |
| **总覆盖率** | **67%** |
| **静态检查** | ruff ✅ / mypy ✅ |
| **耗时** | ~7.7s |

### 运行命令

```bash
.venv/bin/python -m pytest -q          # 395 passed
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
| `tools/novel_storage.py` | 79% → **91%** | `_safe_novel_id`、索引管理、损坏数据、`_ensure_within` |
| `api/main.py` | 98%（不变） | 鉴权中间件直接单测（非回环 403 / 回环放行） |

### 全量覆盖率（模块一览）

```
TOTAL          3663   1209    67%
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
| **S2** save_path/output_dir/restore_path | ✅ | `test_file_utils.py` / `test_export_import.py` / `TestIndexManagement` — 绝对路径、`../`、Windows 盘符全拒 |
| **S3** 角色/设定/文风名称 | ✅ | `TestNameAsFilename` / `TestSlug` — `../../x`、`<>:"|?*` 不越界不崩溃 |
| **S4** importer 书名 | ✅ | `test_data_pipeline.py` — `_safe_filename` / `_save_corpus` 越界拒绝 |
| **S5** 鉴权 + CORS | ✅ | `test_auth.py` — 无 key 401、错误 key 401、正确 key 200、非回环 403、CORS 白名单 |
| **S6** SSRF | ✅ | `test_url_utils.py` / `test_models.py` / `test_web_search.py` — 内网、`file://`、`169.254.169.254`、整数 IP 全拒 |
| **S7** api_key 泄漏 | ✅ | `test_models.py` — 掩码、PATCH 持久化、`/api/system/paths` 不泄主机信息 |

---

## 5. 测试中发现的行为备注（非缺陷）

补充测试时发现以下实现细节，均已在测试中如实反映：

1. **自定义路径已全面收紧**：`save_novel(novel, "/custom")` 因 S2 `resolve_within` 拒绝绝对路径而抛 `ValueError`，`/custom` 这类路径不再可写；索引复用仅对已注册 id 生效（已单测 `_index_register` → 复用路径）。
2. **`list_novels` 失效索引仅跳过、未物理清理**（对应 plan.md **C5.1 未勾选**），测试断言"不列出"而非"已删除"。
3. **白名单 `_safe_novel_id` 接受纯空白 id**（如 `"   "`）——非穿越风险，未作拒绝。
4. 探测端点 3xx/404 按"连接成功"处理，仅 5xx 记 error。

---

## 6. 结论

- P0 安全红线（S1–S7）已实现功能全部具备回归测试，关键安全函数覆盖从缺口补至 88%–100%。
- 完整套件 **395 passed**，ruff/mypy 全绿。
- 遗留低覆盖模块均为 plan.md 中尚未实施的 P1–P3 任务，待对应功能实现后补测。
