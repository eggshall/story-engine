# N7 设计要点 —— 章摘要 + 摘要树 + SQLite + 离线串行队列

> 状态：**设计待拍板**（2026-10-12）。按项目规矩，设计定了再起 RED。
> 上游要求：`PLAN.md` 阶段 Ⅱ、`docs/design/P7-MVP-PLAN.md` 节点表 N7 行
> （「章摘要 + SQLite（走 `_novel_dir`）+ 装配接入 + 离线串行队列」，依赖 N4）。
> 为什么现在做：阶段 Ⅱ 的验收「**第 N 章正确接续第 N−100 章主线与伏笔**」卡在这条上 ——
> 伏笔账本已由 N9 落地，缺的是"很久以前发生了什么"这层记忆。

## 1. 要解决的具体问题（不是"做个摘要"）

一本 20M 字的书，写到第 900 章时，装配器里能放的东西是有限的：
`CHAPTER_TAIL`（上一章尾巴）、`CHARACTERS`、`PINNED`、lore、threads、summaries。
今天 `SUMMARIES` 槽位**存在但没有数据源** —— 第 300 章发生过的主线事件，作者和模型都记不住。
N7 要提供的是：**可增量维护、可审计、按预算装配的"很久以前"层**。

验收（照抄并拆成可测的）：
1. 第 N 章生成时，装配输入里能稳定带上「第 N−100 章附近的主线」与「仍未回收的伏笔」；
2. 20M 字级下装配输入仍在预算内（不随章数线性增长）；
3. 摘要层**可重建**：删掉摘要库 → 跑一遍离线队列 → 内容回来（不依赖人肉补录）。

## 2. 数据分层（三层，物化 + 增量）

| 层 | 粒度 | 内容 | 何时生成 |
|---|---|---|---|
| L1 章摘要 | 每章一条 | 事件 / 出场人物 / 状态变化 / 钩子（见 §3） | 该章定稿后入队（离线） |
| L2 组摘要 | 每 10 章一条 | 由 10 条 L1 归并（保留伏笔与转折，压缩过程） | 组内 L1 全齐且组已"封口"（第 10k 章已写完） |
| L3 卷摘要 | 每 100 章一条 | 由 10 条 L2 重建的**主线 arc** | 卷末**从原文重建**（不是从 L2 再压 —— 防止误差累积） |

关键设计点（要先说清，不然后面全是坑）：
- **L3 从原文重建**，不从 L2 二级压缩。二级压缩的误差会沿 100 章放大；卷级是"主线"，
  错一次会毒害后面所有章的接续质量。代价是卷末要读 100 章原文（离线、串行，可以慢慢跑）。
- **层与层之间只依赖"已封口的块"**：第 15 章生成 L2 时只用 L1(11–20)；第 15 章还没写完就不可能
  有 L2(11–20) —— 这条约束让增量天然正确，也让"第 N 章接续第 N−100 章"能落到具体的数据行上。
- 装配时按距离选取：距当前章最近的 L1 若干条 + 相邻 L2 + 当前卷 L3 + 更早的 L3（各自有预算上限）。

## 3. L1 章摘要 schema（要能校验、能审计）

```jsonc
{
  "chapter_number": 312,
  "title": "问询",
  "summary": "…一两句话的本章梗概…",        // 40–120 字
  "events": [                               // 本章发生的**事件**（主干，≤5 条）
    {"text": "白小姐承认钥匙是她换的", "importance": 4}
  ],
  "characters": ["白小姐", "方警官"],        // 出场人物（按出现先后）
  "state_changes": [                        // 状态变化（人/物/地/关系）
    {"subject": "白小姐", "field": "立场", "from": "配合", "to": "隐瞒"}
  ],
  "hooks": [                                // 钩子（本章新埋/推进的悬念）
    {"text": "钥匙的来历未交代", "status": "open"}
  ],
  "model": "qwen3.5:9b-q6-fixed",           // 谁抽的（可审计、可回滚重跑）
  "source_sha1": "…",                       // 依据的章正文指纹（正文改了 → 摘要过期）
  "created_at": "2026-10-12T…"
}
```

三个必须有的字段，理由是它们让这一层**可信**：
- `model`：抽取失败/降级时能一眼看出混进了不同模型的产物；
- `source_sha1`：**正文改了就作废**（否则"摘要说的"与"正文写的"会分叉，而且没人发现）；
- `status`（hooks）：为 N9 伏笔状态机留接口（本轮只存，不做自动对账）。

## 4. 存储：SQLite 走 `_novel_dir(novel_id)`，且**它是派生数据**

`data/novels/<id>/summaries.db`（与 `novel.json` 同目录，随书走、可整本拷走）。

```sql
CREATE TABLE IF NOT EXISTS chapter_summary (
  chapter_number INTEGER PRIMARY KEY,
  payload        TEXT    NOT NULL,   -- §3 的 JSON（整条存，schema 演进不用改表）
  source_sha1    TEXT    NOT NULL,
  model          TEXT    NOT NULL,
  created_at     TEXT    NOT NULL
);
CREATE TABLE IF NOT EXISTS group_summary (   -- L2：10 章一组
  level INTEGER NOT NULL, span INTEGER NOT NULL,   -- level=10 / 100
  block_start INTEGER NOT NULL,                    -- 起章号
  payload TEXT NOT NULL, source_sha1 TEXT NOT NULL,
  model TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY (level, block_start)
);
CREATE TABLE IF NOT EXISTS summary_job (     -- §5 的队列状态机
  chapter_number INTEGER PRIMARY KEY,
  state TEXT NOT NULL,          -- pending | running | done | failed
  attempts INTEGER NOT NULL DEFAULT 0,
  last_error TEXT NOT NULL DEFAULT '',
  updated_at TEXT NOT NULL
);
```

**为什么摘要可以直接以 SQLite 为唯一存储**（与项目"真源唯一"的惯例不冲突）：
摘要**不是作者手写的资产**，它是**可从原文完整重建的派生数据** —— 删库重跑即可复原。
这与角色卡/世界观/伏笔（作者手写、丢了就真丢了）性质不同，所以不需要 `novel.json` 真源 + 镜像那一套。
反过来，SQLite 给了「按章号区间查询」「断点续跑」这两件 JSON 目录很难做好的事。
> 这条需要一个**回归测试**钉住：删掉 `summaries.db` → 队列重跑 → 摘要内容重建出来（验收 3）。

## 5. 离线串行队列（不阻塞写作）

- **入队**：章正文保存成功后写一行 `summary_job(pending)`；**不做任何联网调用**（保存路径必须快）。
- **消费**：`story-engine summarize --novel <id> [--limit N] [--retry-failed]` 串行处理：
  取一条 `pending`（或 `source_sha1` 与当前正文不符的）→ 标记 `running` → 抽 → 写 `chapter_summary`
  → `done`。失败落 `failed` + `last_error` + `attempts+1`（连续失败 N 次停手，不无限重试）。
- **为什么串行**：本地模型（Qwen3.5-9B）单实例，并发只会互相抢显存/CPU；串行还让进度**可预测**。
- **幂等与断点续跑**：主键是章号；重跑同一章 = 覆盖（幂等）。中途 Ctrl-C 留下的 `running`
  在下次启动时按"超时未更新"回收成 `pending`（不允许卡死）。
- **进度可见**：`story-engine summarize --status` 打印 `pending/running/done/failed` 计数 +
  失败样例。**不许静默**（本项目的老规矩：没做成必须可见）。
- 与后端的关系：后端只**读**摘要装配、只**写** pending 行；抽取进程单独跑，
  这样"写作时卡住"与"批量抽取"互不影响（也便于以后换模型/换机器批跑）。

## 6. 装配接入（改动最小化的那条路）

装配器已有 `SUMMARIES` 槽位（N9 把 threads 挂在 `priority=SUMMARIES`）。N7：
- 新增 `summaries` provider（`writer/context_sources.py`），**不改 `build_novel_builder` 签名**
  （与 N9 的 lore/threads 同一口子 `extra_providers`）；
- 选取顺序与预算：`L1(近 3 章) → L2(覆盖 N−100 附近) → L3(全书主线) → threads(未回收)`,
  超预算时**按槽位自报**（沿用 `ContextPiece.truncated` / `lore:overflow` 那套"截断必须自报"）；
- **不引入检索**（向量/BM25 留给更后面）：本轮只用"按章号区间取"这种确定性的取法，
  理由是验收要求的是"接续第 N−100 章"，这本来就是**按距离**的取法，不是语义检索。

## 7. 拆成可交付的切片（每片走完 ①→⑦）

| 片 | 内容 | 验收 |
|---|---|---|
| S1 | schema + SQLite 存取 + 单章抽取命令（本地模型）+ 幂等/断点 | 一章能抽出 §3 全部字段；重跑幂等；`source_sha1` 变了会重抽 |
| S2 | L2/L3 物化 + 增量封口规则 + 卷末从原文重建 | 20 章数据下三层都对得上；改一章正文只影响它那一块 |
| S3 | 队列状态机 + `--status` + 失败可见 + 删库重建回归 | 验收 3（可重建）在测试里钉住 |
| S4 | 装配 `summaries` 槽位 + 预算自报 + **验收 1** 的真 HTTP E2E | 「第 N 章接续第 N−100 章」在 E2E 里可断言 |

## 8. 非目标（本轮明确不做）

- 向量/BM25 检索式装配；人物关系图谱自动更新；时间线抽取的可视化；跨书摘要复用；
- 把摘要反写进 `novel.json`（它就是派生数据，见 §4）；
- AI 改正文（摘要只读原文，绝不回写正文）。

## 9. 待拍板（三个问题，定了我就起 RED）

1. **抽取用哪个模型？**
   (a) 本地 Qwen3.5-9B（免费、离线、与"辅助填补"定位一致；慢、质量中等）
   (b) DeepSeek 远程（快、质量高；20M 字级成本不小）
   → 建议 (a) 为默认，配置里可换（`summarize.model`），失败可降级到 (b)。
2. **队列由谁跑？**
   (a) CLI 手动/定时跑（`story-engine summarize`，与写作彻底分离）
   (b) 后端加一个后台 asyncio worker（省事，但后端一重启就断、且和写作抢资源）
   → 建议 (a) + 可选 cron（与现有看门狗习惯一致）。
3. **L3 卷摘要的"卷"边界谁来定？**
   (a) 固定每 100 章
   (b) 按作者的"卷"元数据（如果 `Novel` 有卷概念则优先；目前没有）
   → 建议 (a) 固定 100 章起步（可配置），等有卷元数据再切。
