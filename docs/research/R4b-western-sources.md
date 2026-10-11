# R4b — 西方/多语言创作资料源调研（题材无关 · 只做西方部分）

> 用途：为 story-engine(AI 长篇小说写作系统) 补充【西方奇幻】可借鉴的资料源与许可边界。
> 环境：WSL on Windows，国内网络裸连（无代理）。**所有直连结论均以单条 curl 实测为准**，实测格式：
> `curl -s -o /dev/null -w '%{http_code} %{time_total}s' --max-time 8 -A 'Mozilla/5.0' <URL>`
> 实测日期：2026-10-11（CST）。

## 0. 直连实测总表（速查）

说明：`200` 可直连；`401/403` = 端点可达但需 key（选型上意味着"需申请"）；`301/302` = 可达（跳转）；`000 8.0s` = 超时/被墙；`000 <1s` = DNS 解析失败或连接被拒。

| 源 | URL（直测） | HTTP 码 | 耗时 | 判定 |
|---|---|---|---|---|
| Met Museum Open Access | collectionapi.metmuseum.org/public/collection/v1/objects/45734 | 200 | 1.29s | ✅ 直连 |
| Met Museum search | .../search?q=costume | 410 | 0.97s | ⚠️ 端点返回 410（待复核，见 §1） |
| Smithsonian (api.si.edu) | api.si.edu/openaccess/api/v1.0/search?q=test | 403 | 0.86s | ✅ 可达，需 key |
| Europeana API | api.europeana.eu/record/v2/search.json?wskey=demo | 401 | 0.64s | ✅ 可达，需 key |
| Rijksmuseum API | rijksmuseum.nl/api/en/collection?key=demo | 410 | 1.47s | ⚠️ 待复核（可能参数问题） |
| V&A API (api.vam.ac.uk) | api.vam.ac.uk/v2/objects/search?... | 200 | 5.99s | ✅ 直连（较慢） |
| Wikidata SPARQL | query.wikidata.org/sparql?... | 000 | 8.0s | ❌ 超时（Wikimedia 被墙） |
| Wikimedia Commons API | commons.wikimedia.org/w/api.php?... | 000 | 8.0s | ❌ 超时 |
| Wikidata wbsearchentities | wikidata.org/w/api.php?... | 000 | 8.0s | ❌ 超时 |
| Project Gutenberg | gutenberg.org/ebooks/1342 | 200 | 2.18s | ✅ 直连 |
| Gutendex API | gutendex.com/books/?languages=en | 200 | 0.94s | ✅ 直连（推荐） |
| Internet Archive | archive.org/advancedsearch.php?... | 000 | 8.0s | ❌ 超时 |
| Open Library API | openlibrary.org/api/books?... | 000 | 8.0s | ❌ 超时 |
| Standard Ebooks | standardebooks.org/ | 200 | 2.42s | ✅ 直连 |
| Perseus DL | perseus.tufts.edu/hopper/text?... | 200 | 5.05s | ✅ 直连（慢） |
| English Wikisource API | en.wikisource.org/w/api.php?... | 000 | 8.0s | ❌ 超时 |
| Natural Earth | naturalearthdata.com/ | 000 | 0.26s | ❌ DNS/连接失败 |
| David Rumsey 地图库 | davidrumsey.com/ | 200 | 1.63s | ✅ 直连 |
| GeoNames API | api.geonames.org/searchJSON?... | 000 | 0.43s | ❌ DNS/连接失败 |
| Constitute Project | constituteproject.org/ | 200 | 1.16s | ✅ 直连 |
| Behind the Name | behindthename.com/ | 200 | 1.69s | ✅ 直连 |
| Royal Armouries 馆藏 | collections.royalarmouries.org/ | 302 | 1.71s | ✅ 可达 |
| FIT Fashion History Timeline | fashionhistory.fitnyc.edu/ | 200 | 2.05s | ✅ 直连 |
| KCI 京都服饰研究所 | kci.or.jp/en/archives/ | 200 | 1.22s | ✅ 直连 |
| The Getty | getty.edu/ | 200 | 0.77s | ✅ 直连 |
| Sacred Texts | sacred-texts.com/ | 301 | 0.49s | ✅ 可达 |
| Theoi Greek Mythology | theoi.com/ | 000 | 8.0s | ❌ 超时 |

### 选型结论（初版）
- **被墙/超时，需代理或替代**：Wikimedia 全系（Wikidata/Commons/Wikisource）、Internet Archive、Open Library、Natural Earth、GeoNames、Theoi。
  - Wikidata SPARQL 有镜像/替代（如 QLever、Wikidata 的 query.wikidata.org 走代理才可达）。
- **免 key 且直连**：Met Open Access、V&A、Gutendex、Gutenberg、Standard Ebooks、Perseus、Constitute、Behind the Name、FIT、KCI、Getty、Rumsey、Sacred Texts。

---

## 1. 博物馆/文化机构开放数据

### 大都会艺术博物馆 (The Met) Open Access API
- 官网/接口：`https://collectionapi.metmuseum.org/public/collection/v1/...`
- 形式：REST，无需 key。
- 许可：馆藏高分辨率图 + 元数据 **CC0**（Open Access 政策，可商用、无需署名）。API 返回对象元数据（作者、年代、文化、部门、图像 URL）。
- 实测：objects 端点 `200 1.29s` ✅；`search` 端点返回 `410`，**待复核**（可能已迁移/需新参数，见下）。
- 对奇幻创作的用处：**Costume Institute(服饰)、Arms & Armor(兵器)、European Sculpture & Decorative Arts(器物)** 三个部门是金矿；可按 `departmentId` 批量拉对象列表。
- [待补：search 端点复核结果 / departmentId 对照]

### Smithsonian Open Access
- 接口：`https://api.si.edu/openaccess/api/v1.0/...`，**需申请 API key**（免费，通过 api.data.gov）。
- 许可：2D 藏品图像与元数据 **CC0**；3D 模型另有条款。
- 实测：`403 0.86s`（无 key 被拒，端点可达）✅。

### Europeana
- 接口：`https://api.europeana.eu/record/v2/search.json?wskey=<key>&query=...`，**需 key**（免费注册）。
- 许可：元数据 **CC0**；预览图/内容**逐件不同**（CC0 / CC-BY / PD / 受限均有，须逐件看 `rights` 字段）。
- 实测：`401 0.64s`（无 key 被拒，端点可达）✅。

### Rijksmuseum (荷兰国立博物馆)
- 接口：`https://www.rijksmuseum.nl/api/en/collection?key=<key>&format=json`，**需免费 key**。
- 许可：图像 **CC0/公有领域**（开放数据）。
- 实测：`410 1.47s`，**待复核**（demo key 通常返回 401，410 存疑，可能 URL 路径需 `api/nl` 或加 `format=json`）。

### V&A Museum (英国维多利亚与阿尔伯特博物馆)
- 接口：`https://api.vam.ac.uk/v2/...`，**无需 key**。
- 许可：API 元数据 CC0；藏品图像**逐件不同**（大量 PD/CC0，部分 CC-BY-NC）。V&A 有世界顶级 **Textiles & Fashion** 收藏。
- 实测：`200 5.99s` ✅（偏慢，注意超时设长）。

### Wikimedia Commons / Wikidata（⚠️ 直连失败）
- SPARQL 端点 `query.wikidata.org/sparql`、Commons API、Wikidata API 均 `000 8.0s` 超时。
- 结论：**本机裸连不可用**；数据本身是 CC0（Wikidata）/逐文件授权（Commons，多为 CC-BY-SA 或 PD）。若未来有代理，SPARQL 是查询"某历史人物的职业/年代/国籍"的最强工具。
- [待补：代理下可行性 / 镜像端点]

---

## 2. 文本/文献库

### Project Gutenberg
- 官网：`https://www.gutenberg.org/`（直连 200 ✅）。库内 ~7.5 万册，**多语言**（英/法/德/拉丁/希腊等）。
- 接口：Gutendex `https://gutendex.com/` 提供 JSON API（直连 200 ✅），可 `?languages=de`、`?topic=mythology` 过滤，**无需 key**。
- 许可：文本在**美国公有领域**（1929 前出版为主）；"Project Gutenberg" 是**商标**，转载需遵守 PG License（保留免责声明、不用商标）。可商用、可改编，但要保留 PG 商标条款。
- 对创作用处：神话、史诗、服饰/礼俗类 19 世纪英文史料原文。

### Internet Archive / Open Library（⚠️ 直连失败）
- archive.org、openlibrary.org 均 `000 8.0s` 超时。
- 许可：Open Library 书目元数据 **CC0**；扫描书籍**有版权**（仅借阅，不可整本再分发）。直连失败下暂不可用。

### Standard Ebooks
- 官网：`https://standardebooks.org/`（直连 200 ✅）。公版经典的精校 EPUB。
- 许可：文本公有领域；其排版/校对成果 **CC0** 奉献。可自由取用。

### Perseus Digital Library（古典学）
- 官网：`https://www.perseus.tufts.edu/hopper/`（直连 200 ✅，慢）。
- 许可：希腊/拉丁/英译原文多为**公有领域**；部分后加注释与译本受版权/CC-BY-NC 限制（须逐条看）。
- 对创作用处：希腊罗马神话/政体/军事的**原始文本**（希罗多德、李维、荷马等）。

### English Wikisource（⚠️ 直连失败）
- en.wikisource.org API `000 8.0s`。内容本身公有领域/CC，但本机不可达。

---

## 3. 服饰史/器物史/日常生活史

### 已实测直连 ✅
| 源 | URL | 实测 | 说明/许可 |
|---|---|---|---|
| Met Costume Institute | collectionapi.metmuseum.org（同上） | 200 ✅ | CC0；部门 ID 可筛服饰。 |
| V&A Textiles & Fashion | api.vam.ac.uk | 200 ✅ | 元数据 CC0；图逐件看。 |
| FIT Fashion History Timeline | fashionhistory.fitnyc.edu | 200 ✅ | 文字条目**逐篇版权**，作为研究参考（改写，勿照抄）。 |
| KCI 京都服饰研究所数字档案 | kci.or.jp/en/archives/ | 200 ✅ | 图像**版权受限**（仅供浏览参考，不可商用转载）。 |
| Royal Armouries 馆藏 | collections.royalarmouries.org | 302 ✅ | 兵器/盔甲；许可待确认。 |
| The Getty（含 Open Content） | getty.edu | 200 ✅ | Open Content 图像 CC0（约 16 万件）。 |

### 待补实测
- Wallace Collection（伦敦，顶级盔甲/兵器）：wallacecollection.org
- Philadelphia Museum of Art Open Access：philamuseum.org
- Cleveland Museum of Art Open Access API：openaccess-api.clevelandart.org
- Walters Art Museum API：api.thewalters.org
- Museum of London 馆藏：collections.museumoflondon.org.uk

---

## 4. 政体/制度/法律史

### Constitute Project（各国宪法全文）
- 官网/接口：`https://www.constituteproject.org/`（直连 200 ✅）。提供国家→现行宪法全文、可对比条款。
- 许可：**待确认**（通常 CC BY-NC，即**非商用**，用于内部设定研究可，公开商用发布需注意）。
- 对创作用处：各国政体、王权/议会/继承制度、官职的**真实条款**可做"异世界政体"蓝本。

### 待补：比较政体数据集、贵族爵位/官制对照
- Comparative Constitutions Project（comparativeconstitutionsproject.org）
- V-Dem（Varieties of Democracy）、Polity 数据集（学术，免费）
- 爵位/官制对照：无单一权威开放库，可用 Wikipedia（被墙）+ Gutenberg 史料 + Constitute 条款组合。Burke's Peerage 为商业库。

---

## 5. 地理/气候/物产

### Natural Earth（⚠️ 直连失败）
- `naturalearthdata.com` 实测 `000 0.26s`（DNS/连接失败）。数据本身**公有领域**（已确认官网条款）。
- 替代：GitHub 镜像 `github.com/nvkelso/natural-earth-vector`（若 GitHub 可达）；或从地图切片服务取基础地理。

### David Rumsey 历史地图库
- `davidrumsey.com` 直连 200 ✅。18–19 世纪高清历史地图（海量）。
- 许可：图像下载 **CC BY-NC-SA**（署名+非商用+相同方式共享）——**只能参考/内部研究，不可商用直接嵌图**。
- 对创作用处：真实历史海岸线/疆域/城市形态做"西式地图"参照。

### 气候数据
- WorldClim / NOAA / ERA5：待实测。

### 地名库
- GeoNames `api.geonames.org` 实测 `000 0.43s`（失败）。数据本身 **CC BY 4.0**（需署名）。

---

## 6. 命名学

### Behind the Name（人名/地名词源）
- `behindthename.com` 直连 200 ✅。西方人名+地名词源库，附**真实历史语言/文化标签**（对"某文明取什么名字"极有用）。
- **许可（关键）**：名字/性别/usage 等**结构化数据**可付费授权（内部分析用，不得公开再分发）；**词义/历史解说文字不开放**，禁止抓取/转载；允许"少量"展示并回链。**对小说选名：参考改写可用；不要整库搬进产品。**（来源：behindthename.com/info/copyright + /info/licensing；另 Evennia 项目以 CC BY-SA 4.0 引用其 name 数据——即 name 数据存在 CC BY-SA 子集。）

### 官方姓名统计（公有领域，直连待测）
- 美国人口普查姓氏数据：census.gov（美国政府作品 = **公有领域**）
- 美国 SSA 婴儿名：ssa.gov（公有领域）
- 英国 ONS 婴儿名：ons.gov.uk（Open Government Licence）
- 地名：GeoNames（CC BY 4.0，但本机连不上）；Wikidata（CC0，被墙）

---

## 7. 宗教/神话

### Sacred Texts Archive
- `sacred-texts.com` 直连 301 ✅。宗教/神话/民俗**公版文本**大合集（多语言、多传统）。
- 许可：所收文本多为公有领域；其 HTML 转写页有网站版权声明，**文本本身可引，页面勿整站搬运**。

### Theoi Greek Mythology（⚠️ 直连失败）
- `theoi.com` 实测 `000 8.0s` 超时。希腊神话权威资料站；**文字是其自译，图像来自博物馆，整体非商业授权**。被墙下不可用。

### Perseus（见 §2）—— 神话/宗教原始文本最佳来源之一，直连 ✅。

---

## A. 版权与许可分域

| 域 | 典型源 | 可否商用 | 需否署名 | 边界 |
|---|---|---|---|---|
| **公有领域文本** | Gutenberg、Standard Ebooks、Sacred Texts、Perseus(古文本)、Wikisource | ✅ 可 | 否（PG 有商标条款） | 直接引用/改写均可；PG 转载保留其 License 页 |
| **CC0 开放图像与元数据** | Met、Smithsonian(2D)、Getty Open Content、V&A 部分、Rijksmuseum、Europeana 元数据、Natural Earth、Wikidata | ✅ 可 | 否 | 图像可直接用；逐件核对个别藏品例外 |
| **CC BY 类数据** | GeoNames(CC BY 4.0)、Europeana 部分预览图 | ✅ 可 | ✅ 需署名 | 数据可用但保留 attribution |
| **CC BY-NC(-SA)** | David Rumsey 地图、Constitute(待确认)、部分博物馆图 | ❌ 商用受限 | ✅ 需署名 | **只能内部研究/参考改写，不可商用发布** |
| **需申请 key 的 API** | Smithsonian、Europeana、Rijksmuseum、GeoNames | 依许可 | 依许可 | key 免费，但限流/用途条款要看 |
| **受限整理本/词条** | Behind the Name 词义文字、Theoi 译文、KCI 图、FIT 文章 | ❌ 不可再分发 | — | **只作"参考改写"素材，禁止抓取/整段引用** |

### "可参考改写" vs "可直接引用" 边界（一句话原则）
- **可直接引用/直接用**：公有领域文本（摘录原文）、CC0/CC BY 图像与数据（含署名）、CC0 元数据。
- **只可参考改写**：CC BY-NC(-SA) 内容（只能研究，不能把素材图/文本放进商用产品）、受限词条与译文（把"词源结论"转写成自己的设定文字，而非复制原文）、一切"逐件看 rights"的博物馆预览图。
- 设定卡片（§B）引用源时，**记下许可标签 + 来源 URL**，产出商用文本时据此过滤。

---

## B. 多来源资料 → 小说设定卡片模板

### 设计原则
- 每张卡 = 一个可被 story-engine 复用的**结构化字段表** + **来源/许可**字段（用于后续合规过滤）。
- 字段分两类：`事实字段`（来自真实资料，抄录/翻译）+ `设定字段`（世界观内的决定，标注"已定/待定"）。

### B1. 服饰/器物卡
| 字段 | 类型 | 说明 | 示例 |
|---|---|---|---|
| id / 名称 | str | 物品名（中文+原文） | doublet 紧身上衣 |
| 时代/地区 | enum+str | 真实对应时代·地区 | 16 世纪英国 |
| 功能/场合 | str | 礼仪/军/日常/宗教 | 宫廷礼服 |
| 材质与工艺 | str | 织物/金属/装饰 | 天鹅绒、金线刺绣 |
| 形制描述 | text | 真实形制（可参考改写） | 耸肩、束腰、开襟… |
| 社会等级信号 | str | 谁穿/谁不能穿 | 贵族专属 |
| 来源 URL + 许可 | str | 引用记录 | Met obj id / CC0 |
| 世界观映射 | text | 在本故事中如何化用 | 改名为 X 礼服 |

### B2. 政体/制度卡
| 字段 | 类型 | 说明 |
|---|---|---|
| 名称 | str | 政体/官职名（中+原） |
| 真实对应 | str | 例：神圣罗马帝国选帝侯制 |
| 权力来源/继承 | text | 血统/选举/神授 |
| 官职与爵位层级 | list | 对照表（源自 Constitute/Gutenberg 史料） |
| 义务/特权 | text | 兵役、税、司法 |
| 现实参照条款 | url | 宪法条款/史料链接 |
| 世界观差异 | text | 与现实的偏离点 |
| 来源+许可 | str | — |

### B3. 地理/气候/物产卡
| 字段 | 类型 | 说明 |
|---|---|---|
| 名称/类型 | str | 王国/城市/海岸/山脉 |
| 真实参照 | str | 例：参照 18c 地图的莱茵河谷 |
| 气候带/季相 | enum+str | 温带海洋性等 |
| 物产/资源 | list | 决定经济与贸易 |
| 交通/距离 | text | 旅行时间（防设定自相矛盾） |
| 地图参照 URL | str | Rumsey 图（CC BY-NC-SA，仅内部） |
| 来源+许可 | str | — |

### B4. 宗教/神话卡
| 字段 | 类型 | 说明 |
|---|---|---|
| 神系/信仰名 | str | 真实参照（希腊/北欧/一神教…） |
| 创世/末世叙事 | text | 源自公版文本 |
| 仪式/节庆 | list | 真实→改写 |
| 禁忌/道德律 | list | 影响角色行为 |
| 神职层级 | list | 教士/祭司/先知 |
| 原始文本 URL | str | Perseus / Sacred Texts |
| 世界观差异 | text | 改写的关键点 |
| 来源+许可 | str | — |

### B5. 命名卡
| 字段 | 类型 | 说明 |
|---|---|---|
| 文化/语系 | str | 例：古诺斯语、拉丁语 |
| 人名构成规则 | text | 名+父名/氏；后缀规律 |
| 真实人名样本 | list | 从 BtN/官方统计取（标注来源） |
| 地名构成规则 | text | -burg/-ton/-heim 等 |
| 音系约束 | text | 保证同族名字"听感一致" |
| 禁忌/避讳 | str | 王族名不得复用等 |
| 来源+许可 | str | Behind the Name(受限)/SSA(PD) |

### 公开 worldbuilding bible 模板先例（附 URL）
- 22 问故事优先世界设定模板：`https://theselfpublishingsite.com/tools/worldbuilding-template`
- K.M. Weiland 六要素 + World Anvil 结构归纳：`https://showmemybook.com/guides/world-building-bible-template`
- Notion "Author Story/Series Bible"：`https://www.notion.com/templates/author-story-series-bible`
- Melon Pope World Bible Template：`https://melonpope.neocities.org/worldbuilding`
- 11 页可商用 Story Bible（PDF/MD/DOCX 免费下载）：`https://nanowritlabs.com/blog/story-bible-template`

---

## 待补清单（后续逐节补全）
- [ ] Met search 端点 410 复核 + departmentId 对照
- [ ] Rijksmuseum 正确 URL/key 复核
- [ ] Wallace / Philly / Cleveland / Walters / Museum of London 实测
- [ ] Constitute 许可确认（CC BY-NC?）
- [ ] 气候数据（WorldClim/NOAA）+ OSM 实测
- [ ] census.gov / ssa.gov / ons.gov.uk 直连实测
- [ ] 比较政体数据集（V-Dem/Polity/CCP）实测
- [ ] Wikimedia 镜像/代理替代方案
