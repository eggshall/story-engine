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

---

# N8 第二切片评审（设定集接口 + 素材库）

> 评审方式：`opencode run --agent requirements`（**只读**评审，未改代码）
> 评审日期：2026-10-12（同一天，承接 `2e84a34` 之后的新增改动）
> 输入：`lore/library.py`、`api/routes/lorebooks.py`、`api/main.py`、
>   `tests/test_lore/test_lorebooks_api.py`、`tests/e2e/test_n8_lorebooks_real_http.py`、三份文档改动

## 结论性核对结果

- 复核门禁：**982 passed / 3 skipped，覆盖率 94.27%**；ruff / mypy 68 文件全绿；两个新测试文件
  13 + 4 例，计数属实；确认测试**没有**写进真实 `data/`。
- **改名守卫实测有效**：`PUT /lorebooks/X {name:"Y"}`（Y 已存在）→ `success:false`，两条都在、内容未变。
- **书间隔离实测成立**（单测层 + E2E 层，且 E2E 另有用例证明该内容本来会进 prompt，非空洞）。
- **路由顺序无遮蔽**；`ApiResponse` 形状与 `characters.py` 一致；无 key 返回 401。
- 结论：**无 P0**（无串书、无真源丢失、改名守卫有效）；**素材库这一块存在 3 个 P1 + 6 个 P2**。

## P0

无。

## P1（3 条，全部已修）

- **P1-1 · 素材库文件名用 `_slug` 清洗 → 不同名字映射同一文件，静默覆盖。**
  实测：同书建 `"A B"` 与 `"A_B"` 分别另存，两次都 `success:true`，目录里只剩 `A_B.json`，
  先导出的**无声消失**；且 `names` 回的是 slug 后的 stem 而 `books[].name` 是真名，两者不自洽。
- **P1-2 · 导入不存在的素材时错误消息撒谎。** 实测 `{"source":"library","name":"ghost"}` →
  「本书已有同名设定集「ghost」（可勾选覆盖）」；加 `overwrite:true` 消息一字不变（源本不存在）。
- **P1-3 · 非法 `source` 触发未捕获异常 → HTTP 500。** 实测 `source:"../../etc/passwd"` →
  `500 {"detail":"服务器内部错误"}`。异常链 `_require_novel → load_novel → _safe_novel_id` 抛
  `ValueError`，而 `except` 只捕 `NovelNotFound`。**`characters.py` 同病。**

## P2（6 条，全部已处置）

- **P2-1** 导出对同名/跨书同名一律静默覆盖 → 加 `overwrite`。
- **P2-2** `extra="forbid"` 只覆盖顶层，条目内拼错字段仍被丢弃（`categorie` 被无视且 `success:true`）。
- **P2-3** `ImportLoreBookRequest` 不继承 `APIModel` → 驼峰 `newName` 被静默忽略。
- **P2-4** 空名字被接受（存成 key `""`、镜像落 `untitled.json`，与任何 slug 为 untitled 的名字碰撞）。
- **P2-5** `to-library` 的 `new_name` 只认 query、JSON body 被忽略。
- **P2-6** 上述每一条都缺失败用例（13+4 例全绿掩盖了它们）。

## 逐条处置表（⑥ 修复）

| 编号 | 处置 | 落点 |
|---|---|---|
| P1-1 | 素材库**身份改为文件内嵌的 `name`**，文件名只负责寻址：`load_from_library` 校验内嵌名与请求名一致（不一致视为不存在），导出前比对目标文件 —— **同名同身份 = 幂等刷新**，**异身份撞同一文件名 = 显式失败**（除非 `overwrite=true`）；`list_library` 返回内嵌名。`characters/library.py` 同步 | `lore/library.py`、`characters/library.py` |
| P1-2 | 返回码从 `bool` 改为 `Literal`：导出 `ok / source_missing / name_taken / write_failed`、导入 `ok / source_missing / target_exists`，路由分别发诚实消息（「素材库里没有 X」不再冒充「本书已存在」） | 两个 library + 两条路由 |
| P1-3 | `import` 路由增捕 `ValueError` → `success:false`「源标识非法」；**`characters.py` 一起改** | `lorebooks.py`、`characters.py` |
| P2-1 | 导出加 `overwrite`（默认 False）；同身份重复另存仍幂等，避免前端点两次报错 | 两个 library + 两条路由 |
| P2-2 | 请求层新增 `LorebookEntryRequest(extra="forbid")`，`LoreBookRequest` 改为**独立边界模型** + `to_book()`（子类化会撞 `entries` 类型不协变）。**不动磁盘模型** `LoreBook`/`LorebookEntry` | `api/routes/lorebooks.py` |
| P2-3 | `ImportLoreBookRequest` 改继承 `APIModel` | 同上 |
| P2-4 | 请求层 `name: str = Field(min_length=1)`（同样只约束边界，老文件的空名不会被盘面校验炸掉） | 同上 |
| P2-5 | **保留 query**（与角色卡端点、前端 `exportCharacterToLibrary` 一致）但**写进 docstring 作为契约**；返回值是素材身份名。**偏离评审建议**：改 body 会改掉既有 UI 调用契约，收益不足 | 两条路由 docstring |
| P2-6 | 补 12 条失败用例：slug 碰撞不覆盖 / 同身份幂等 / `overwrite` 生效 / names 与 books 自洽 / 源缺失消息诚实 / 非法 source 非 500 / 驼峰 `newName` / 嵌套拼错 422 / 空名 422（lore 侧 9 条 + characters 侧 3 条）；characters 的 5 条旧用例改断 `ok`/`source_missing`/`target_exists` | 两个测试文件 |
| **新发现** | 见下节，**本切片不修**，另开增量 | — |

**修复后门禁**：**995 passed / 3 skipped，覆盖率 94.43%** · ruff 全绿 · mypy 68 文件全绿 ·
vitest 104 · vue-tsc 0 · vite build ✓

## ⚠️ 新发现（既有缺陷，比评审看到的更严重，本切片不修）

**`characters/` 镜像文件名 slug 碰撞 + `load_novel` 回读镜像 = 真丢卡。**

探针实测（`/tmp/probe_chars.py`，隔离 NOVELS_ROOT/LIBRARY_DIR）：

```
create 'A B'  200 True
create 'A_B'  200 True
to-library 'A B'  200 {'success': False, 'message': '角色卡「A B」不存在'}
library files: ['A_B.json']
names: ['A_B']
```

两处既有行为叠加：① `_write_files` 写 `characters/` 镜像时文件名走 `_slug`（有损，两个名字 →
同一个文件，后写覆盖先写）；② `load_novel` **会回读** `characters/` 镜像并**替换** `novel.json`
里的 `characters`。于是先建的那张卡在界面上**立刻看不见**（真源 `novel.json` 里其实两张都在，
但要等一次「绕过镜像读」才能看到）。

- `lore/` **没有**这个问题：它不回读镜像（评审第一轮 P2-8，刻意为之），真源即所见。
- `threads/` 同理走 `_slug`，但 id 通常不含空格/斜杠，实际触发面小得多。
- 修法（另开增量，需要 RED 先行）：镜像文件名不再单靠 `_slug` 定身份（加短 hash 后缀，或
  回读时按内嵌 `name` 合并而不是整体替换）；改名会让既有镜像文件失效，但真源在 `novel.json`，
  下次保存重建即可 —— 需专门验证老数据兼容。
- 评级：**P1**（静默数据丢失路径，但触发需要名字 slug 碰撞这一条件）。

---

# N8 缺陷修复切片评审（镜像文件名身份碰撞）

> 评审方式：`opencode run --agent requirements`（**只读**评审，未改代码）
> 评审日期：2026-10-12（第三轮）
> 说明：**第一轮尝试中途终止**（评审进程在 `/tmp` 写探针脚本被权限系统拒绝后自行停止，未产出
> 结论段；其唯一产物是「stash 掉源码后新用例 6 失败 / 2 通过、stash 干净弹出」这条可证伪性确认）。
> 改用「禁止写文件、只用只读命令 + `.venv/bin/python -c`」的提示词重跑后拿到完整报告，即本节。

## 结论性核对结果

- 复核门禁：**1003 passed / 3 skipped，覆盖率 94.45%**；ruff / mypy 全绿（与提交前一致）。
- **兼容性（实测）**：非撞名场景文件名与旧实现**逐字节相同**；`_slug` 幂等，二次 slug 不改变新文件名；
  撞名落盘后旧 `A_B.json` 已被清掉、**无残影**；删掉撞名的那一个后能正确回退成 `A_B.json`。
- **顺序无关（实测）**：`_mirror_file_names(["A B","A_B","x"])` 与打乱顺序的结果相同。
- **身份推导（实测）**：全仓唯一「从文件名 stem 反推身份」的活代码是 `novel_storage.py:255`，
  且内嵌 `name` 优先、`stem` 仅作损坏兜底 —— hash 后缀不会打断任何调用方。
- **安全**：hash 只追加 `[0-9a-f-]`，仍过 `_safe_json_path` 的 resolve+parent 校验；
  既有 `test_malicious_character_names_do_not_escape` 仍绿。
- 结论：**无 P0**（新发生的碰撞不再静默丢卡）；1 个 P1 + 3 个 P2。

## P1-1 · 既有「已撞名损坏」的书不会自愈，且下一次保存会把**可恢复**的数据变成永久丢失

实测：手工构造升级前遗留目录（`novel.json` 里两张都在、`characters/` 只剩 `A_B.json`）→
`load_novel` 后内存里只剩 `A_B` → 一次 load→save 就把 `"A B"` 从 `novel.json` **永久抹掉**，
而此刻它的内容**仍完好在真源里、完全可恢复**。判据：本切片自称消除「静默丢卡」，却只防未来、
不治旧账。这是既有缺陷的残余（本 diff 未让它更糟，但也没关掉这条仍在的丢数据路径）。

## P2（3 条）

- **P2-1「唯一」并非严格成立**：单成员组用裸 slug，多成员组产出 `slug-<8位digest>`，字符集相同 →
  有人把条目命名成 `"A_B-8aabb8bc"`（= `_slug("A B")` + `sha1("A B")[:8]`）就会与另一组产出
  **逐字节相同**。实测 3 张卡只落 2 个文件、`"A B"` 被覆盖丢失。构造性碰撞确定发生
  （`sha1[:8]` 的偶发生日碰撞在实践中可忽略）。
- **P2-2 新用例有近似恒真断言**（`assert all("/" not in f for f in files)` —— `glob("*.json")`
  取自单目录，名字里本就不可能有 `/`），且缺两类反例。
- **P2-3 素材库仍用有损 `_slug`**，与新镜像命名不一致。**不丢数据**（撞名走 `name_taken` 显式失败），
  故非缺陷，只是同仓两套文件名规则易漂移。

## 逐条处置表（⑥ 修复）

| 编号 | 处置 | 落点 |
|---|---|---|
| P1-1 | `load_novel` 回读 `characters/` 从**整体替换**改为**合并**：以真源字典为底、镜像只覆盖**同名**项，绝不删除只存在于真源的条目。于是残缺镜像不再能「吞掉」真源，`load→save` 不会销毁可恢复数据；镜像的手改能力保留（同名仍以镜像为准，有专项用例）。补 3 条用例（load 保留 / save 不销毁 / 镜像仍能覆盖同名） | `novel_storage.py::load_novel` + `tests/test_characters/test_mirror_names.py` |
| P2-1 | `_mirror_file_names` 生成后做**全局唯一性自检**，冲突则把 digest 从 8 位延长到 16 / 40 位重算；全量 sha1 仍撞则 `raise ValueError`（宁可报错也不让两个身份共用一个文件）。补构造性碰撞用例（RED 先行：修前 3 张卡只落 2 个文件） | `novel_storage.py::_mirror_file_names` + 新用例 |
| P2-2 | 把近恒真断言换成「目录里恰有 N 个 `*.json`、没有子目录被拖进来」；补「遗留纯 slug 目录 load→save 不丢卡」与「构造性 hash 碰撞」两类反例 | 同上 |
| P2-3 | **两边都保留现状**（库=裸 slug + 显式失败；镜像=自动加 hash）并**把差异写进两个 library 的 docstring**：库文件是真源/作者资产，静默改名比报错更糟；镜像由 `_write_files` 整目录重建，不需要与人协商 | `characters/library.py`、`lore/library.py` |

**修复后门禁**：**1007 passed / 3 skipped，覆盖率 94.43%** · ruff 全绿 · mypy 68 文件全绿。

**另修（同一类「提示不诚实」）**：`cli.py` 的 `character example` / `lore example` 原来打印
`<目录>/<名字>.json`，撞名时与实际文件名不符 → 改为打印**目录**并说明命名规则。
