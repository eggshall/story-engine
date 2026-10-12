# N8 评审报告（世界观测切片：按书绑定 + 装配器 `lore` 槽位 + 镜像语义）

> 评审方式：`opencode run --agent requirements`（**只读**评审，未改代码）
> 评审日期：2026-10-12
> 输入：`AGENTS.md`（§4 强约定 / §5 测试 / §6 节点流程）+ `PLAN.md` 阶段 Ⅱ · Ⅱ.5 +
>   `docs/design/P7-MVP-PLAN.md` §9.1 / §9.1.1 / §9.3 + 本切片全部改动（工作区未提交状态）
> 说明：以下为报告正文（原会话含工具调用噪声，此处只留结论与逐条处置）。

---

## 结论性核对结果

- 读全了改动（6 个源文件 + 4 个改测试）与 3 个新增测试文件；跑了全量门禁。
- 门禁复核：**961 passed / 3 skipped，覆盖率 94.52%**（门禁 75%）；ruff / mypy 全绿。
- **核心逻辑正确**：
  - `lore` 槽位已注册、`provider="lore"`、优先级 `CHARACTERS`（可被预算裁）；
  - `_lore_provider` 只读传入的 `novel.lorebooks`，书间隔离在**当前所有调用点**成立；
  - E2E 用「两本书同一触发词、内容不同」验证了**非空洞**隔离，并断言了假上游真实收到的 prompt；
  - `previous_chapter_text` 的边界（补写中间章 / 重写 / 编号乱序 / 正文为空）处理正确；
  - 镜像目录语义修正正确，删除后无残影有单测与 E2E 双重钉死。
- **未见数据丢失 / 串书类 P0**。老书缺 `lorebooks` 键的兼容有回归用例。
- **N8 节点本身仍未完成**：本 diff 只做了「按书绑定 + `lore` 槽位 + 镜像语义」三件事；
  `/api/novel/{id}/lorebooks` 系列、素材库 lore 端点、`WorldView` 设定集 UI、浏览器 E2E 均未做，
  且本 diff 未同步任何文档。

---

## P0（阻断）

无。

---

## P1（应修）

**P1-1 · 文档与代码直接矛盾（陷阱表把 `lore/` 记成「只写不清空」）**
- `docs/design/P7-MVP-PLAN.md` §9.1.1 陷阱表写着 `lore/` = 只写、不清空；而
  `tools/novel_storage.py` 本切片已改成先清空再重建。触发：任何人按该表判断「绕过模型直接写
  `lore/*.json` 安全」都会踩坑；N9 实施记录还把「lore 只写不清空」当作已核实事实引用。
- 判据：文档声称的行为 ≠ 当前代码行为，且该表被声明为「必须遵守的陷阱」。

**P1-2 · N8 残项仍未做却被 PLAN 暗示完成**
- `PLAN.md` 把「世界观管理 (`/world`)」及「Lorebook 条目列表 + 编辑」标 `[x]`；而
  `docs/design/P7-MVP-PLAN.md` 明确「WorldView 那页只有世界地图，lorebook 完全没有 UI」、
  浏览器 E2E 未做。触发：以 `PLAN.md` 为准的人会以为世界观 UI 可用。
- 判据：两个计划文档对同一事实给出相反状态；本 diff 未新增任何 lorebooks 路由、
  `WorldView.vue` 的 lorebook 区块、`e2e/` Playwright 用例。

---

## P2（建议）

**P2-1 · 弱（误导性）隔离单测** —— `test_other_novels_lorebooks_never_leak_in` 名为「别的书设定
不漏进来」，但只构造了一本**空 `lorebooks`** 的书，从未在共享目录里放第二本带命中的书。
把 provider 改回读全局，该测试仍会通过（与「空设定集→不注入」是同一个断言）。

**P2-2 · `find_matching_entries` 静默丢弃第 11 条起** —— provider 侧不传 `max_results`，
吃默认 10 条；某章触发 >10 条设定时，第 11 条起既不进 `entries` 也不进 `skipped`/`dropped`，
与 §4「`context_manifest` 必须与真正注入的文本一一对应」相悖。

**P2-3 · `skipped` 理由 `empty` 掩盖三种成因** —— 「本书无设定集 / 第一章无触发源 /
有触发源但没命中」都压成 `empty`，作者无法区分该去建设定集还是该检查上一章。

**P2-4 · CLI `--novel` 指向不存在小说时抛原始异常** —— `_resolve_novel_id` 对显式 id 不校验，
`NovelNotFound`（普通 Exception）冒到 Click，用户看到裸堆栈而非「小说不存在」。

**P2-5 · lore 反向依赖 characters 异常类型（层次耦合）** —— `lore/lorebook.py` 为复用异常
`import story_engine.characters.manager`，两个业务上无关的模块被绑在一起。

**P2-6 · 同一装配器里两套「上一章」口径** —— `chapter_tail` 用精确 `chapter_number - 1`，
`lore` 用「编号 < 本章 的最大者」。章节跳号（缺第 4 章）时会出现「世界观拿到第 3 章正文、
上一章结尾却是空的」这种自相矛盾的清单。

**P2-7 · 遗留未跟踪脚本** —— `scripts/_audit_slots.py` 是临时审计脚本，功能已被
`test_lore_slot.py` 覆盖；若一并提交会污染仓库。

**P2-8 · `lore/` 镜像只写不读，与 characters 不对称** —— `load_novel` 回读 `characters/` 镜像
但不读 `lore/`；作者手改 `lore/<名>.json`（CLI 的 `story lore example` 还打印这个路径）后，
载入被忽略、下次保存被覆盖。

---

## 逐条处置表（⑥ 修复，2026-10-12）

| 编号 | 处置 | 落点 |
|---|---|---|
| P1-1 | 陷阱表 `lore/` 行改为「先清空再重建（N8 统一）」；N9 实施记录里「lore 只写不清空」标注为**已变更**并说明镜像仍是只读导出 | `docs/design/P7-MVP-PLAN.md` §9.1.1 + N9 实施记录 |
| P1-2 | `PLAN.md` 的「世界观管理 (`/world`)」**去掉错误勾选**并写明「页面是写死的假数据、全项目无 `/api/lore` 调用」；§9.1 的 N8 行拆清「已落地/未做」；新增「N8 世界观切片」状态表 | `PLAN.md` Phase 2.3 + `P7-MVP-PLAN.md` §9.1 |
| P2-1 | 用例改为在 `novels_root` 里真放一本**会被命中**的第二本书，并先断言它命得中，再断言本书拿不到 | `tests/test_lore/test_lore_slot.py::TestIsolation` |
| P2-2 | `find_matching_entries` 支持 `max_results=None`（不截断）；provider 自己截到 `LORE_MAX_ENTRIES=50`，超出部分发 `lore:overflow` 片段自报条数（`truncated=True`），**清单与真实注入重新一致** | `lore/lorebook.py`、`writer/context_sources.py`、`tests/test_lore/test_lore_slot.py::TestOverflowVisibility` |
| P2-3 | 口径**写清楚**而不拆新理由字符串（拆了会与 `chapter_tail` 等既有槽位不一致）：docstring 明列三种成因，并用 `test_skipped_empty_reason_is_shared_by_three_causes` 把口径钉住 | `writer/context_sources.py::_lore_provider` + 新用例 |
| P2-4 | `_resolve_novel_id` 对显式 `--novel` 也校验存在，报可读错误（同一处顺带修掉 character 命令的同病） | `cli.py` + `tests/test_cli.py::test_missing_novel_is_a_readable_error` |
| P2-5 | 新增 `core/errors.py::NovelNotFound`，characters / threads / lore 三方都从这里取；`characters.manager` 保留再导出以兼容既有导入点 | `core/errors.py`（新增）、`characters/manager.py`、`threads/manager.py`、`lore/lorebook.py` |
| P2-6 | 抽出 `previous_chapter()` 作为**唯一**的「上一章」口径，`chapter_tail` 与 `lore` 共用；`source` 改写**真实**章号（`chapter_tail:ch_0003`，跳号时不再撒谎） | `writer/context_sources.py` + `tests/test_writer/test_context_sources.py::test_chapter_gap_uses_the_last_written_chapter` |
| P2-7 | 删除 `scripts/_audit_slots.py`（功能已由 `test_lore_slot.py::TestSlotRegistration` 覆盖） | `scripts/` |
| P2-8 | 明确 `lore/` 为**只读导出**：`load_novel` 处写明非对称是刻意的（回读会让已删设定集从残影复活），CLI 输出改为「只读导出 + 手改不会生效」 | `tools/novel_storage.py`、`cli.py` |

**修复后的门禁**：**965 passed / 3 skipped，覆盖率 94.54%** · ruff 全绿 · mypy 66 文件全绿 ·
vitest 104 · vue-tsc 0 · vite build ✓

**仍然未做（不属修复范围，是 N8 的后续增量）**：`/api/novel/{id}/lorebooks` 系列 +
素材库 lore 端点、`WorldView` 设定集区块、世界观浏览器 E2E。
