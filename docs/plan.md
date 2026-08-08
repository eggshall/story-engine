# 体检 + 优化任务分解计划 (Health Check & Optimization Plan)

> 状态：`docs/requirements.md` 不存在，本文基于对代码库的实际深度体检（ruff/mypy/246 tests 全绿 + 四路代码审查：LLM&core / API / pipeline&tools / tests&工程）推导的优化需求。
> 当前基线：ruff ✅ / mypy ✅ / 246 passed。

---

## 优先级定义

| 级别 | 含义 |
|------|------|
| **P0** | 安全红线 / 数据丢失风险，必须立即修复 |
| **P1** | 正确性 / 健壮性 / 性能问题 |
| **P2** | 工程健康（CI、测试、文档、配置） |
| **P3** | 死代码清理 / 低优重构 |

---

## Phase P0 — 安全红线（任意文件读写/删除）

### S1. novel_id 路径穿越 → 任意目录读/写/删
- **风险**：`novel_id` 未经净化直接拼目录名，`../../` 可越出 `NOVELS_ROOT` 任意读写删。
- **位置**：`src/story_engine/tools/novel_storage.py:101-108`（`_novel_dir`）、`:224-225`（save）、`:158-163`（load）、`:268-290`（delete `shutil.rmtree`）；`src/story_engine/api/routes/novel.py:44-47`
- **任务**：
  - [x] S1.1 新增 `_safe_novel_id()`：白名单校验（unicode 字母数字 + `_`/`-`），拒绝 `..`、`/`、`\`、`%`、控制符、空值
  - [x] S1.2 `_novel_dir()` 内统一走白名单校验（含 delete/load/save 全部入口）
  - [x] S1.3 delete 前 `Path.resolve()` 确认目录仍位于 `NOVELS_ROOT` 之下
  - [x] S1.4 补回归测试：`novel_id="../../"`、`".."`、`"%2e%2e"` 均被拒绝

### S2. save_path / output_dir / restore_path 任意目录写
- **位置**：`src/story_engine/api/routes/novel.py:78-79`、`src/story_engine/tools/novel_storage.py:213-222`；`src/story_engine/api/routes/export.py:76-84,120-128,160-178`
- **任务**：
  - [x] S2.1 抽出 `resolve_within(root, user_path)` 工具：`Path.resolve()` + parents 包含性校验，拒绝绝对路径/`..`
  - [x] S2.2 `save_novel(custom_path)`、MD/JSON 导出 `output_dir`、导入 `restore_path` 全部套用该校验
  - [x] S2.3 非法路径统一抛 HTTPException(400)，不落盘
  - [x] S2.4 补回归测试：绝对路径、`../`、Windows 盘符均被拒绝

### S3. 角色/设定/文风名称用作文件名 → 穿越
- **位置**：`src/story_engine/tools/novel_storage.py:254-256`（`cname`）、`:259-261`（lore 名）、`:340`（profile.name）；`src/story_engine/api/routes/novel.py:247`
- **任务**：
  - [x] S3.1 统一用 `_slug()` 清洗后作文件名，原始名称存入 JSON 内容字段
  - [x] S3.2 写文件前校验生成路径仍在 `NOVELS_ROOT` 内
  - [x] S3.3 补测试：`cname="../../x"`、含 `<>:"|?*` 名称不越界不崩溃

### S4. importer 书名作文件名 → 越界写
- **位置**：`src/story_engine/data_pipeline/importer.py:123`、`:23-27`（`_clean_title` 未处理 `/` `..`）
- **任务**：
  - [x] S4.1 `_clean_title` 后追加安全文件名清洗（拒绝 `/`、`..`、控制符）
  - [x] S4.2 落盘前 `resolve()` 校验仍在 `CORPUS_DIR/imports` 内

### S5. 无鉴权 + CORS 通配
- **位置**：`src/story_engine/api/main.py:43-49`
- **任务**：
  - [x] S5.1 增加 API Key 鉴权（`X-API-Key` header / config 中配置），未配置时仅本机可访问
  - [x] S5.2 CORS `allow_origins=["*"]` + `allow_credentials=True` 改为白名单配置
  - [x] S5.3 补测试：无 key 请求被拒

### S6. SSRF：模型探测 + 搜索结果抓取
- **位置**：`src/story_engine/api/routes/models.py:89-129`、`:74-77`（任意 base_url）；`src/story_engine/tools/web_search.py:532,319`（`fetch_page_content`）
- **任务**：
  - [x] S6.1 `test_model_connection` 校验 base_url 必须 `https://` + 域名非私网/IP 段（回环地址放行本地模型）；探测只返回成功/失败
  - [x] S6.2 `fetch_page_content` 校验 scheme 并阻断私有网段/内网地址
  - [x] S6.3 补测试：内网 IP、`file://`、`169.254.169.254` 被拒

### S7. 敏感信息泄漏
- **位置**：`src/story_engine/api/schemas.py:86-95`（`ModelInfo.api_key` 未掩码）；`api/routes/models.py:127-129`、`export.py:152-157`（`str(e)` 回显）；`api/routes/system.py:31-76`（主机信息）
- **任务**：
  - [x] S7.1 `ModelInfo.api_key` 删除或改 `SecretStr`
  - [ ] S7.2 统一异常信息脱敏（见 P1-E2，随 P1 处理；模型测试端点错误已先行脱敏）
  - [x] S7.3 系统路径探测接口按调用方/权限裁剪或移除（仅返回 suggested）

---

## Phase P1 — 正确性 / 健壮性 / 性能

### L1. 本地模型超时配置失效（高危 bug）
- **位置**：`src/story_engine/llm/local_client.py:41-53,26-39,65-66,117`
- **问题**：`_check_server` 首个调用用 `read_timeout=10` 创建实例级复用 client，后续 120s/300s 超时全部被 `self._client is not None` 忽略。
- **任务**：
  - [ ] L1.1 探测/预热改用临时 client（不复用持久 client）
  - [ ] L1.2 持久 client 创建时按当前配置的 `read_timeout`/`connect_timeout` 重建；chat 每次显式传 timeout
  - [ ] L1.3 补测试：mock `_get_client` 断言 chat 走 300s 超时、探测走 10s

### L2. 远程客户端忽略注入的超时配置
- **位置**：`src/story_engine/llm/api_client.py:19,24,115,117`；`src/story_engine/api/routes/generate.py:38-46`
- **任务**：
  - [ ] L2.1 统一读取 `read_timeout`/`connect_timeout`，支持请求级覆盖
  - [ ] L2.2 补测试：注入超时被 `chat()`/`chat_stream()` 消费

### L3. close_all() 从未调用 → httpx 连接池泄漏
- **位置**：`src/story_engine/llm/router.py:98-102`；`src/story_engine/api/main.py`（无 lifespan）
- **任务**：
  - [ ] L3.1 `main.py` 注册 `lifespan`，shutdown 时 `await _router.close_all()`
  - [ ] L3.2 CLI 退出路径同样关闭（`cli.py` 入口包 try/finally）
  - [ ] L3.3 `BaseLLM.close()` 改为 `abstractmethod` 或文档强制子类实现
  - [ ] L3.4 补测试：`router.close_all()` 幂等可调用

### L4. 健康探测：3 次串行探测拖慢失败路径 + 无并发保护
- **位置**：`src/story_engine/llm/local_client.py:74,124,41-53,23,55-90`
- **任务**：
  - [ ] L4.1 健康状态缓存 + TTL（如 30s），`_warmed` 重置策略补上
  - [ ] L4.2 探测/预热加 `asyncio.Lock` 串行化，消除 `_warmed` 竞态

### L5. fallback 丢失诊断信息 + 误标前缀
- **位置**：`src/story_engine/llm/router.py:63-72,74-96`；`api_client.py:101-102,200-201`；`local_client.py:165-166`
- **任务**：
  - [ ] L5.1 全部失败时聚合各模型原始错误返回（去敏）
  - [ ] L5.2 未命中目标模型时不再加 `[Fallback → ...]` 前缀；仅真实 fallback 才标
  - [ ] L5.3 流式模式支持模型级 fallback；错误以结构化事件抛出，不再 `yield "[Error: ...]"` 混入正文

### L6. 配置加载零校验 + _get_router 污染共享配置
- **位置**：`src/story_engine/core/config.py:53-58`；`src/story_engine/llm/router.py:24-30`；`src/story_engine/api/routes/generate.py:30-48`
- **任务**：
  - [ ] L6.1 YAML 加载失败给清晰错误 + 空配置回退；加载后用 Pydantic 校验 `llm.models`
  - [ ] L6.2 `_get_router()` 深拷贝模型 dict 后再注入 timeout，杜绝 `cfg.save()` 持久化注入值
  - [ ] L6.3 router 实例懒加载加锁，或改 lifespan 初始化；提供 `reload_config()` 时重建 router 的钩子（解决 PATCH 配置需重启问题）

### L7. reasoning 模型 content 为空被误判错误
- **位置**：`src/story_engine/llm/api_client.py:56-57,95-98`；`local_client.py:158-160`
- **任务**：
  - [ ] L7.1 对齐 local client：content 为空时回退 `reasoning_content`
  - [ ] L7.2 补测试：mock reasoning_content 返回

### L8. SSE 语义与资源清理
- **位置**：`src/story_engine/api/sse.py:15-22`；`src/story_engine/api/routes/generate.py:127-180,166,180,92-100`；`style.py:239-247`
- **任务**：
  - [ ] L8.1 统一 SSE 事件协议：错误转 `{"event":"error"}`，内部生成器只 yield 纯文本/结构化对象，外层统一包装（消除双重 JSON 编码）
  - [ ] L8.2 生成器加 `try/finally`，客户端断开时释放 httpx 流连接
  - [ ] L8.3 补 `event_stream()` 单测 + 断开中断测试

### L9. 错误处理统一
- **位置**：`src/story_engine/api/main.py`（无全局 exception handler）；`novel.py:49,376,387,403`；`export.py:67-71`；`generate.py:75,112`
- **任务**：
  - [ ] L9.1 约定：业务失败统一 `HTTPException`(4xx)，成功统一 200
  - [ ] L9.2 `@app.exception_handler(Exception)` 统一记日志 + 返回脱敏信息（不泄露 `str(e)`）
  - [ ] L9.3 移除各端点 `str(e)` 回显

### L10. async 端点内阻塞 IO
- **位置**：`novel.py`（CRUD 同步 IO）、`research.py:50-64`、`style.py`（同步 sqlite）、`generate.py:80-83`、`system.py:22-37`、`tools/web_search.py:415-424`（`subprocess ip route` 阻塞 3s）
- **任务**：
  - [ ] L10.1 纯同步 IO 端点改 `def`（FastAPI 自动线程池）或 `anyio.to_thread`
  - [ ] L10.2 `subprocess.run(['ip','route'])` 加超时 + 缓存，避免每次阻塞 3s

### L11. 输入校验补齐
- **位置**：`src/story_engine/api/schemas.py:21-27,70,79`；`novel.py:111-382`（大量 `body: dict`）
- **任务**：
  - [ ] L11.1 `messages` 加 `min_length=1`；`temperature` 加 `ge=0,le=2`；`max_tokens` 加 `ge=1`；`query`/`mode`/`format` 加长度与枚举约束
  - [ ] L11.2 逐一替换 `body: dict` 端点为请求 schema（含 `content:null` 时 `len()` 崩溃、`Chapter` 字段类型错误 500 等）

### L12. 章节数据完整性
- **位置**：`src/story_engine/api/routes/novel.py:176-177,126-142`；`generate.py:169-178`
- **任务**：
  - [ ] L12.1 `reorder` 校验 `set(order) == set(existing_numbers)`，杜绝静默丢章节
  - [ ] L12.2 新增章节前检查 `chapter_number` 是否已存在（同号覆盖或报错）

### L13. 字数统计口径
- **位置**：`src/story_engine/api/routes/generate.py:164-175`；`models.py:157-158`
- **任务**：
  - [ ] L13.1 错误/fallback 前缀不计入正文与字数；统一由 `Chapter.content` 计算

### L14. 原子写 / 保存可靠性
- **位置**：`src/story_engine/tools/novel_storage.py:240-265`（先 unlink 再写）
- **任务**：
  - [ ] L14.1 先写临时文件再 `os.replace` 原子替换（逐文件或目录级事务）

### L15. 数据管线健壮性
- **位置**：`data_pipeline/index.py:38-44`、`fetcher.py:29-39`、`importer.py:30-37,40-51,155-165,190-205`、`cleaner.py:59-60,130-133`、`catalog.py:49-50`
- **任务**：
  - [ ] L15.1 index 并发丢失更新：单写者锁或追加式写入；损坏 JSON 防御式返回空
  - [ ] L15.2 fetcher：临时文件 + `os.replace` 原子落盘；校验首行/哈希替代 `st_size>1000`
  - [ ] L15.3 importer：编码 round-trip 校验防 GBK 误判；epub 改流式/分卷处理控内存
  - [ ] L15.4 仅当全部子项成功才归档 `done/`，失败文件留在原地 + 写失败日志
  - [ ] L15.5 迭代目录时不移走条目（先收集列表再处理）
  - [ ] L15.6 cleaner：START 标记无换行时从首个可见字符截取；段落切分空行缺失时按单换行兜底并告警
  - [ ] L15.7 catalog JSON 加载加容错

### L16. 性能
- **位置**：`src/story_engine/tools/fixed_tasks.py:112-124`（O(N×M) 一致性检查）
- **任务**：
  - [ ] L16.1 预分词建索引；每地名最多一条 issue；提高匹配阈值

### L17. 杂项修复
- **位置**：`novel_storage.py:213`（Windows 路径转换触发条件）、`pipeline.py:75-76` vs `config.py:27`（题材回退名不一致）、`data_pipeline/config.py:8`（硬编码 `/mnt/d/文章数据`）
- **任务**：
  - [ ] L17.1 Windows 盘符路径 `D:\` 正确识别
  - [ ] L17.2 题材回退目录名统一
  - [ ] L17.3 `DATA_ROOT` 改为环境变量/配置注入，失败给清晰提示

---

## Phase P2 — 工程健康（CI / 测试 / 文档）

### E1. 建立 CI
- **任务**：
  - [ ] E1.1 新建 `.github/workflows/ci.yml`：`pip install -e .[dev]` → `ruff check` → `mypy src` → `pytest -q` → 上传 coverage
  - [ ] E1.2 `ruff`、`mypy`、`pytest-cov`/`coverage` 写入 `pyproject.toml [dev]`

### E2. 测试隔离与有效性
- **任务**：
  - [ ] E2.1 移除/重写 `tests/test_delete_flow.py`（伪测试，污染真实 `data/novels/`），改为 fixture 隔离
  - [ ] E2.2 新增 `tests/conftest.py` 统一最小配置 fixture（tempfile config + monkeypatch），收敛 7+ 份重复复制
  - [ ] E2.3 `tests/test_research.py` 联网用例改 mock，非幂等测试从 CI 剔除
  - [ ] E2.4 清理弱断言：`test_analyze.py`（`in (200,422)`）、`test_writer/test_api.py`（`in (200,500)`）改为精确断言

### E3. 补核心链路测试（当前零/低覆盖）
- **任务**：
  - [ ] E3.1 `writer/engine.py`（277 行 0 覆盖）：三种写作模式
  - [ ] E3.2 `cli.py`（307 行 0 覆盖）：各命令冒烟
  - [ ] E3.3 `llm/local_client.py` + `api_client.py`（<25%）：chat/chat_stream/close/错误分支/超时
  - [ ] E3.4 `data_pipeline/fetcher.py`/`importer.py`/`pipeline.py`/`catalog.py`（0 覆盖）：核心流程
  - [ ] E3.5 `api/sse.py event_stream()`、`style/analyzer.py check_consistency`、`api/routes/system.py` 其余端点
  - [ ] E3.6 `llm/base.py close()`、`router.close_all()`、`style/recommend.get_genre_prototypes`

### E4. coverage 门禁
- **任务**：
  - [ ] E4.1 `pyproject.toml` 增加 `[tool.coverage.run]` + `[tool.coverage.report] fail_under` 阈值
  - [ ] E4.2 `addopts = "--cov ... --cov-fail-under=..."`

### E5. 文档与版本同步
- **任务**：
  - [ ] E5.1 `README.md`：更新测试数（246）、项目结构（style/data_pipeline/tools/utils）、补 uvicorn 启动命令
  - [ ] E5.2 `pyproject.toml` version 0.1.0 → 与 CHANGELOG 对齐（0.8.x）
  - [ ] E5.3 `.gitignore`：补 `.mypy_cache/`、`.ruff_cache/`，删死条目 `src/frontend/dist/`

### E6. 依赖与警告
- **任务**：
  - [ ] E6.1 处理 StarletteDeprecationWarning（httpx/starlette.testclient 兼容）

---

## Phase P3 — 死代码清理 / 低优重构

### C1. LLM/Core 层死代码
- **位置**：`core/models.py:169-185`（`ModelConfig`/`LLMConfig` 未使用，`weight` 摆设）、`:117-121`（`WritingMode` 未使用）、`:23-34` vs `:94-109`（两套重复 Lorebook 结构）、`llm/base.py:50-51`（`if False: yield` hack）、`base.py:18`（`LLMRequest.stream` 未消费）、`local_client.py:147`（函数内 import json）
- **任务**：
  - [ ] C1.1 让 router 消费 `ModelConfig` 或删除；删 `WritingMode`；合并重复 Lorebook 结构
  - [ ] C1.2 用 `typing.AsyncGenerator` 标注替代 `if False: yield`；消费或删除 `LLMRequest.stream`
  - [ ] C1.3 `import json` 移到模块顶部

### C2. 工具层死代码
- **位置**：`utils/file_utils.py`（整模块无调用）；`web_search.py`（`_search_so_mobile`/`_search_sogou_mobile`/`_search_duckduckgo`/`_VPN_ENDPOINTS`/`search_zhihu`/`search_wenku` 未引用；`_SEARCH_ENGINES_CN` 与 `_INTL` 相同导致 bing 双请求；`:148-153` 未用循环变量）；`fixed_tasks.py`（`extract_keywords`/`summarize_chapter`/`compress_history` 无调用）；`prompts.py:23`（未使用）；`fetcher.download_many`/`cleaner.clean_file`/`index.find_by_id`（仅测试用）；`catalog.py`（整模块未接线）
- **任务**：
  - [ ] C2.1 删除无调用死代码，或补测试 + 接线（catalog 接入 pipeline）
  - [ ] C2.2 引擎表去重、拼接前过滤；删除空跑正则循环
  - [ ] C2.3 `_clean_url` docstring 与实现对齐

### C3. 数据模型统一
- **位置**：`tools/memory_models.py:121` 与 `style/db.py:28` 两套 `StyleProfile`；`fixed_tasks.check_consistency`（正则）与 `style/analyzer.py:146`（LLM）同名不同实现
- **任务**：
  - [ ] C3.1 统一为单一数据模型与单一入口

### C4. 指标口径修复
- **位置**：`src/story_engine/tools/style_analyzer.py:82-84`（四类百分比非互斥、合计 ≠ 1）
- **任务**：
  - [ ] C4.1 按句子/段落分类后分别统计占比，保证互斥

### C5. 无效索引清理落地
- **位置**：`src/story_engine/tools/novel_storage.py:132-134`（只 log 不清理）
- **任务**：
  - [ ] C5.1 `list_novels` 真正移除失效索引条目

---

## 建议执行顺序

```
P0 安全红线 (S1→S7)   —— 先堵任意文件读写/删除 + 鉴权
P1 正确性/健壮性 (L1→L17) —— 修复超时 bug、SSE、错误处理、原子写
P2 工程健康 (E1→E6)   —— CI + 测试门禁 + 文档同步
P3 清理重构 (C1→C5)   —— 死代码 + 指标修复
```

每完成一个任务：`ruff check src tests` + `mypy src` + `pytest -q` 全绿后勾选。
