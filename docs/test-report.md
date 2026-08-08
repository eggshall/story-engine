# 测试报告 — story-engine

> 生成时间：2026-08-08
> 覆盖范围：`docs/plan.md` Phase P1 已实现功能（L1–L10）补充/完善测试 + 完整套件回归（含此前 P0 S1–S7 全部测试）+ 修复 P1 实现遗留的 lint/type 问题

---

## 1. 测试结果概览

| 指标 | 结果 |
|------|------|
| **测试总数** | **490 passed**（此前 443） |
| **本轮新增测试** | **+47 个**（净增 443 → 490） |
| **总覆盖率** | **74%**（此前 67%，P1 关键模块补至 98%–100%） |
| **静态检查** | ruff ✅ / mypy ✅（本轮顺带修复 P1 实现遗留的 5 处 lint + 2 处 type 问题） |
| **耗时** | ~7s |

### 运行命令

```bash
.venv/bin/python -m pytest -q          # 490 passed
.venv/bin/python -m ruff check src tests # All checks passed!
.venv/bin/python -m mypy src            # Success: no issues found
```

---

## 2. 补充的测试（按 plan.md P1 已实现功能 L1–L10）

### 新增 / 扩展文件

| 文件 | 对应任务 | 本轮补充内容 |
|------|---------|-------------|
| `tests/test_llm/test_local_client.py` | **L1 / L4 / L7 / L5** | 请求级超时覆盖 `_get_client`、探测成功路径（`<500` 判定 + 缓存）、预热成功置位 / `_warmed` 短路、预热失败、chat 未就绪 / 超时 / 泛异常结构化错误、流式未就绪抛 `LLMStreamError`、坏 JSON / 空行 / 注释行容错、流式异常转 `LLMStreamError`、`close()` 释放 client |
| `tests/test_llm/test_api_client.py` | **L2 / L7 / L5** | stop 载荷、api_key 请求头、流式空行/坏 JSON 容错、流式异常转 `LLMStreamError`、泛异常掩码、`close()`；**Anthropic 全链路**：请求头（x-api-key / 版本 / 超时）、system_prompt、多段 text 拼接、chat/chat_stream 错误、流式 `content_block_delta` |
| `tests/test_llm/test_router.py` | **L5 / L3** | `_pick_target` 默认模型 / 无默认取首个、`fallback=False` 直返失败、无模型错误信息、错误无 detail 兜底、流式"指定模型不在列表落默认"前缀、泛异常触发流式 fallback、全部泛异常聚合、无模型流式抛错、`close_all` 吞单 client 异常、provider→客户端映射、`list_models` |
| `tests/test_llm/test_base.py` | **L3** | `close_all()` 幂等 / 空 router 安全 |
| `tests/test_config_p1.py` | **L6** | `_validate_models` None/非列表/默认值填充、OSError 读取失败回退、`get` 中途非 dict 兜底、reload 无事件循环清空 router、运行中事件循环内调度 `close_router`、reload import 失败静默 |
| `tests/test_error_handling.py` | **L9** | `BusinessError`→400、lifespan shutdown 调用 `close_router`、shutdown 异常被吞 |
| `tests/test_writer/test_sse.py` | **L8** | 修复 `test_unknown_exception_masked` 的"coroutine was never awaited"告警（改真实生成器 + 显式 aclose） |
| `tests/test_style.py` / `test_style_recommend.py` / `test_delete_flow.py` | **L10 / E2** | 隔离配置 fixture（不触发本地鉴权）、删除流程断言化 |

### 覆盖的 plan.md P1 任务对照

| plan.md 任务 | 测试覆盖 |
|-------------|---------|
| **L1** 本地超时配置失效 | `TestTimeout` — chat 走 300s、探测走 10s 临时 client、超时变化重建持久 client、请求级覆盖 |
| **L2** 远程忽略注入超时 | `TestTimeoutInjection` / `TestAnthropic::test_chat_stream_content_block_delta` — chat/chat_stream 消费 `LLMRequest.timeout` |
| **L3** 连接池泄漏 | `TestCloseAll`（router）/ `TestClose`（local）/ `TestStreamTolerance::test_close_releases_client` / `TestAnthropic::test_close_releases_client` / `TestLifespan`（lifespan shutdown） |
| **L4** 健康探测缓存 + 锁 | `TestHealthCache` / `TestEnsureReady` — TTL 缓存、`asyncio.Lock` 串行化、`_warmed` 短路 |
| **L5** fallback 诊断 | `TestChatFallback` / `TestChatStream` — 聚合错误、前缀标记规则、流式 fallback、`LLMStreamError` 结构化抛出 |
| **L6** 配置校验 + 污染 | `TestConfigLoad` / `TestRouterNoPollution` — YAML 容错、Pydantic 校验、深拷贝、reload 重建 router |
| **L7** reasoning 回退 | `TestReasoningFallback` / `TestStreamErrorFormat` — content 空回退 `reasoning_content` |
| **L8** SSE 语义 | `TestEventStream` — token/done/error 事件、双重编码消除、断开中断清理 |
| **L9** 错误处理统一 | `TestGlobalExceptionHandler` — 未捕获异常脱敏、HTTPException 保留、BusinessError→400 |
| **L10** async 阻塞 IO | novel/research/style/system 同步端点由既有 API 测试回归覆盖；`anyio.to_thread` 路径经 `generate` 流程测试验证 |

---

## 3. 关键覆盖提升

### P1 关键模块（本轮重点）

| 模块 | 覆盖率 | 提升点 |
|------|-------|-------|
| `llm/local_client.py` | 83% → **100%** | 超时覆盖、错误分支、流式容错、close、探测成功路径 |
| `llm/api_client.py` | 69% → **100%** | stop/头、流式容错、Anthropic 全链路、close |
| `llm/router.py` | 86% → **100%** | provider 映射、目标选择、fallback 策略、close_all 异常吞除 |
| `api/main.py` | 87% → **100%** | BusinessError、HTTPException、lifespan shutdown |
| `core/config.py` | 90% → **98%** | 校验边界、OSError 回退、reload 两分支 |

### 全量覆盖率（模块一览）

```
TOTAL          3849    991    74%
```

主要未覆盖模块仍为 **计划中尚未实现** 的 P1 剩余项与 P2–P3 内容，属预期范围：
- `cli.py` 0%（307 行，计划 E3.2 未实施）
- `data_pipeline/fetcher.py`、`pipeline.py`、`catalog.py` 0%（计划 E3.4/L15 未实施）
- `writer/engine.py` 0%（计划 E3.1 未实施）
- `api/routes/generate.py`、`style.py`、`tools/web_search.py` 低覆盖（部分依赖 LLM/网络 mock，随 E3.3/E3.5 补齐）

---

## 4. 本轮修复的行为问题（顺带，非测试遗留）

| 问题 | 修复 |
|------|------|
| P1 实现遗留 lint：`generate.py` 未用 `json`、`sse.py` 未用 `Union`/`e` | 清理 import 与未用变量 |
| P1 实现遗留 type：`local_client._get_client(read_timeout: int)` 与 `request.timeout: float` 不兼容 | 签名放宽为 `float | None`，`_client_read_timeout` 同步放宽 |
| `test_writer/test_sse.py` 误把 async 函数当生成器（coroutine never awaited 告警） | 改为真实 async 生成器 + 显式 `aclose()` 清理 |

---

## 5. 行为备注（非缺陷）

- 流式错误以 `LLMStreamError` 结构化抛出，由 SSE 层包装为 `event: error`；已实现调用方（generate/style 路由）在 `finally` 中 `aclose` 释放 httpx 流连接。
- `reload_config()` 在运行中事件循环内调度 `close_router()` 关闭旧连接池；无事件循环时直接清空引用，连接池由进程退出回收。
- P1 中尚未实现的任务（L11 输入校验、L12 章节完整性、L13 字数口径、L14 原子写、L15 管线健壮性、L16 性能、L17 杂项）对应的 `[ ]` 勾选维持不变，实现后补测。

---

## 6. 结论

- P1 已实现功能（L1–L10）全部具备针对性回归测试，`llm` 层三个核心模块（local/api/router）与 `api/main.py` 覆盖补至 **100%**。
- 完整套件 **490 passed**（+47），总覆盖率 **67% → 74%**；ruff / mypy 全绿（含修复 P1 实现遗留的 lint/type 问题）。
- 遗留低覆盖模块均为 plan.md 中尚未实施的任务，待功能实现后按计划补测。
