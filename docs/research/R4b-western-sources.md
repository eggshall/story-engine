# R4b — 西方/多语言创作资料源调研（题材无关 · 只做西方部分）

> 用途：为 story-engine（AI 长篇小说写作系统）补充【西方奇幻】可借鉴的资料源与许可边界。
> 环境：WSL on Windows，国内网络裸连（无代理）。**所有直连结论均以单条 curl 实测为准**：
> `curl -s -o /dev/null -w '%{http_code} %{time_total}s' --max-time 8 -A 'Mozilla/5.0' <URL>`
> 实测日期：2026-10-11（CST）。

---

## 0. 直连实测总表（速查）

判定说明：`200` 可直连；`401/403` = 端点可达但需 key 或被反爬拦截（选型上意味着"需申请/需浏览器"）；`301/302/307` = 可达（跳转）；`404` = 路径错或对象不存在；`410` = 端点已弃用；`000 8.0s` = 超时/被墙；`000 <1s` = DNS 解析失败或连接被拒。

| 源 | 直测 URL | HTTP 码 | 耗时 | 判定 |
|---|---|---|---|---|
| Met Open Access（对象） | collectionapi.metmuseum.org/public/collection/v1/objects/45734 | 200 | 1.29s | ✅ |
| Met search 端点 | .../public/collection/v1/search?q=armor | 410 | 0.90s | ⚠️ 已弃用，改用 `objects?departmentIds=` |
| Met 服饰学院 | .../objects?departmentIds=8 | 200 | 5.51s | ✅ 31,897 件 |
| Met 兵器盔甲 | .../objects?departmentIds=4 | 200 | 2.72s | ✅ |
| Met 部门列表 | .../public/collection/v1/departments | 200 | 1.73s | ✅ |
| Smithsonian | api.si.edu/openaccess/api/v1.0/search?q=test | 403 | 0.86s | ✅ 可达，需 key |
| Europeana | api.europeana.eu/record/v2/search.json?wskey=demo | 401 | 0.64s | ✅ 可达，需 key |
| Rijksmuseum 旧 API | rijksmuseum.nl/api/nl/collection?key=demo | 410 | 1.48s | ⚠️ 已弃用 |
| Rijksmuseum 新搜索 API | data.rijksmuseum.nl/search/collection | 200 | 1.06s | ✅ **免 key** |
| Rijksmuseum 解析器 | id.rijksmuseum.nl/200107928 | 200 | 1.17s | ✅ |
| Rijksmuseum OAI-PMH | data.rijksmuseum.nl/oai?verb=Identify | 200 | 0.91s | ✅ 免 key |
| V&A API | api.vam.ac.uk/v2/objects/search?q_search=armour | 200 | 3.09s | ✅ 免 key（偏慢） |
| Cleveland Museum API | openaccess-api.clevelandart.org/api/artworks/?limit=1 | 200 | 2.13s | ✅ **免 key** |
| Walters Art Museum API | api.thewalters.org/v1/objects?apikey=demo | 000 | 1.60s | ❌ 连不上 |
| Getty 主站 | getty.edu/ | 200 | 0.77s | ✅ |
| Getty API | api.getty.edu/v1/objects/ | 000 | 0.06s | ❌ 连不上 |
| Wallace Collection | wallacecollection.org/ | 301 | 1.33s | ✅ 可达 |
| Philadelphia Museum | philamuseum.org/ | 307 | 0.46s | ✅ 可达 |
| Museum of London 馆藏 | collections.museumoflondon.org.uk/ | 000 | 6.97s | ❌ 超时 |
| Wikidata SPARQL | query.wikidata.org/sparql?query=… | 000 | 8.0s | ❌ Wikimedia 被墙 |
| Wikimedia Commons API | commons.wikimedia.org/w/api.php | 000 | 8.0s | ❌ 被墙 |
| Wikidata API | wikidata.org/w/api.php | 000 | 8.0s | ❌ 被墙 |
| 英文维基百科 | en.wikipedia.org/wiki/Main_Page | 000 | 8.0s | ❌ 被墙 |
| Project Gutenberg | gutenberg.org/ebooks/1342 | 200 | 2.18s | ✅ |
| Gutendex API | gutendex.com/books/?languages=en | 200 | 0.94s | ✅ 免 key |
| Internet Archive | archive.org/advancedsearch.php | 000 | 8.0s | ❌ 超时 |
| Open Library API | openlibrary.org/api/books | 000 | 8.0s | ❌ 超时 |
| Standard Ebooks | standardebooks.org/ | 200 | 2.42s | ✅ |
| Perseus DL | perseus.tufts.edu/hopper/text | 200 | 5.05s | ✅ 慢 |
| English Wikisource API | en.wikisource.org/w/api.php | 000 | 8.0s | ❌ 被墙 |
| Natural Earth | naturalearthdata.com/ | 000 | 0.26s | ❌ DNS 失败 |
| Natural Earth GitHub 镜像 | github.com/nvkelso/natural-earth-vector | 000 | 8.0s | ❌ GitHub 被墙 |
| David Rumsey 地图库 | davidrumsey.com/ | 200 | 1.63s | ✅ |
| Rumsey 版权页 | davidrumsey.com/about/copyright-and-permissions | 200 | 0.95s | ✅ |
| GeoNames API | api.geonames.org/searchJSON | 000 | 0.43s | ❌ DNS 失败 |
| OpenStreetMap | openstreetmap.org/ | 000 | 8.0s | ❌ 被墙 |
| WorldClim 气候 | worldclim.org/ | 200 | 1.56s | ✅ |
| Constitute Project | constituteproject.org/ | 200 | 1.16s | ✅ |
| Comparative Constitutions Project | comparativeconstitutionsproject.org/ | 200 | 0.90s | ✅ |
| Behind the Name | behindthename.com/ | 200 | 1.69s | ✅ |
| 美国人口普查局 | census.gov/ | 403 | 2.07s | ⚠️ 反爬拦截（浏览器可开） |
| 美国 SSA 婴儿名 | ssa.gov/oact/babynames/ | 403 | 0.10s | ⚠️ 反爬拦截 |
| 英国 ONS | ons.gov.uk/ | 200 | 1.71s | ✅ |
| Etymonline | etymonline.com/ | 403 | 0.50s | ⚠️ 反爬拦截 |
| Royal Armouries 馆藏 | collections.royalarmouries.org/ | 302 | 1.71s | ✅ 可达 |
| FIT 服饰史时间线 | fashionhistory.fitnyc.edu/ | 200 | 2.05s | ✅ |
| KCI 京都服饰研究所 | kci.or.jp/en/archives/ | 200 | 1.22s | ✅ |
| Sacred Texts | sacred-texts.com/ | 301 | 0.49s | ✅ 可达 |
| Theoi Greek Mythology | theoi.com/ | 000 | 8.0s | ❌ 超时 |

### 选型结论
- **免 key 且本机直连可用（首选）**：Met、Rijksmuseum（新 API）、V&A、Cleveland、Gutendex、Gutenberg、Standard Ebooks、Perseus、Constitute（仅非商用）、CCP、Behind the Name（参考）、ONS、WorldClim、Rumsey（仅参考）、FIT、KCI、Getty（主站）、Sacred Texts。
- **可达但需申请 key**：Smithsonian（403）、Europeana（401）。
- **被墙/连不上，需代理或放弃**：Wikimedia 全系（Wikidata/Commons/Wikisource/Wikipedia）、Internet Archive、Open Library、Natural Earth（含 GitHub 镜像）、GeoNames、OpenStreetMap、Theoi、Walters API、Getty API、Museum of London。
- **可达但反爬拦截 curl（浏览器/手工可开）**：census.gov、ssa.gov、etymonline（数据本身公有领域，只是 API 不可用）。

---

## 1. 博物馆/文化机构开放数据

### 大都会艺术博物馆 (The Met) Open Access API
- 接口：`https://collectionapi.metmuseum.org/public/collection/v1/`，**无需 key**。
- 许可：高分辨率图 + 元数据 **CC0**（Open Access，可商用、免署名）。
- 实测：objects 端点 `200`；departments `200`；**search 端点已弃用（410 Gone）**，检索改用：
  - `GET /objects?departmentIds=<id>` 拿对象 ID 列表，再 `GET /objects/<objectID>` 拿详情。
  - 关键 departmentId：`4`=Arms and Armor，`8`=The Costume Institute（31,897 件），`12`=European Sculpture & Decorative Arts，`13`=Greek and Roman Art，`17`=Medieval Art（`/departments` 可查全表）。
- 对奇幻创作：服饰/兵器/器物/中世纪美术四个部门是核心金矿；对象详情含 `title/objectDate/culture/medium/department/primaryImage` 等字段，可直接用于设定卡"事实字段"。

### Smithsonian Open Access
- 接口：`https://api.si.edu/openaccess/api/v1.0/`，**需申请 key**（免费，经 api.data.gov）。
- 许可：2D 藏品图像 + 元数据 **CC0**；3D 模型另有条款。
- 实测：`403 0.86s`（无 key 被拒，端点可达）。

### Europeana
- 接口：`https://api.europeana.eu/record/v2/search.json?wskey=<key>&query=...`，**需免费 key**。
- 许可：元数据 **CC0**；预览图/内容**逐件不同**（须读响应里 `rights` 字段，CC0/CC-BY/PD/受限都有）。
- 实测：`401 0.64s`（端点可达，需 key）。

### Rijksmuseum（荷兰国立博物馆）
- **旧 API 已弃用（410）**：`www.rijksmuseum.nl/api/...`。
- **新 Linked Open Data API（免 key）**：
  - 搜索：`https://data.rijksmuseum.nl/search/collection?type=…&material=…`（Linked Art Search 规范，返回对象标识符列表）
  - 解析器：`https://id.rijksmuseum.nl/<id>`（据标识符取详情）
  - OAI-PMH：`https://data.rijksmuseum.nl/oai?verb=ListRecords&metadataPrefix=edm`
- 许可：绝大多数馆藏图像 **公有领域**（PD/CC0）；历史元数据曾以 CC-BY 发布。
- 实测：搜索/解析器/OAI 均 `200 0.9–1.2s` ✅。

### V&A Museum（英国，维多利亚与阿尔伯特博物馆）
- 接口：`https://api.vam.ac.uk/v2/`，**无需 key**。示例 `GET /v2/objects/search?q_search=armour&page_size=1`。
- 许可：API 元数据 **CC0**；藏品图像**逐件不同**（大量 PD/CC0，部分 CC-BY-NC）。V&A 有世界顶级 **Textiles & Fashion** 收藏。
- 实测：`200 3.09s` ✅（偏慢，调用超时建议 ≥15s）。

### Cleveland Museum of Art（克利夫兰艺术博物馆）
- 接口：`https://openaccess-api.clevelandart.org/api/artworks/?limit=1`，**无需 key**。
- 许可：公版藏品高清图 + **全馆元数据 CC0**（官网 Open Access 页确认）。
- 实测：`200 2.13s` ✅。收藏含盔甲、纺织、装饰艺术。

### 其他（可达性）
- **Wallace Collection**（伦敦，顶级盔甲/兵器）：`wallacecollection.org` 可达（301）。
- **Philadelphia Museum of Art**（开放馆藏）：`philamuseum.org` 可达（307）。
- **The Getty**：主站 `getty.edu` 可达（200），Open Content 图像 CC0（约 16 万件）；但其 `api.getty.edu` 连不上。
- **Walters Art Museum API**（`api.thewalters.org`）：连不上（000）。
- **Museum of London 馆藏**（`collections.museumoflondon.org.uk`）：超时（000）。

### Wikimedia Commons / Wikidata（❌ 直连失败）
- SPARQL、Commons API、Wikidata API、英文维基百科**全部 `000 8.0s`**。
- 数据本身：Wikidata **CC0**；Commons 逐文件授权（多为 CC-BY-SA / PD）。SPARQL 是"查某历史人物职业/年代/国籍"的最强工具，但本机需代理才能用。

---

## 2. 文本/文献库

### Project Gutenberg + Gutendex
- 官网 `gutenberg.org` 直连 200 ✅；~7.5 万册，**多语言**（英/法/德/拉丁/希腊…）。
- 接口：**Gutendex** `https://gutendex.com/` JSON API，**免 key**，可 `?languages=de`、`?topic=mythology` 过滤。
- 许可：文本在**美国公有领域**；"Project Gutenberg" 是商标，转载需保留其 License 页与免责声明、不用其商标。
- 对创作用处：神话、史诗、19 世纪服饰/礼俗史料原文。

### Standard Ebooks
- `standardebooks.org` 直连 200 ✅。公版经典精校 EPUB；文本 PD，排版成果 **CC0**。

### Perseus Digital Library（古典学）
- `perseus.tufts.edu/hopper/` 直连 200 ✅（慢）。希腊/拉丁/英译原文多为**公有领域**；后加注释/译本部分 CC-BY-NC，逐条看。
- 对创作用处：希罗多德、李维、荷马等**原始文本**（政体/军事/神话最佳一手来源）。

### Internet Archive / Open Library / Wikisource（❌ 直连失败）
- archive.org、openlibrary.org、en.wikisource.org 均 `000 8.0s`。
- 许可备忘：Open Library 书目元数据 CC0；扫描书**有版权**（仅借阅）。

---

## 3. 服饰史/器物史/日常生活史

| 源 | URL | 实测 | 许可/用法 |
|---|---|---|---|
| Met Costume Institute | collectionapi（dept 8） | 200 ✅ | CC0 图+元数据，可直接用 |
| V&A Textiles & Fashion | api.vam.ac.uk | 200 ✅ | 元数据 CC0；图逐件看 |
| Cleveland（纺织/装饰艺术） | openaccess-api.clevelandart.org | 200 ✅ | CC0 |
| Royal Armouries（兵器盔甲） | collections.royalarmouries.org | 302 ✅ | 许可待查，作参考 |
| Wallace Collection（盔甲） | wallacecollection.org | 301 ✅ | 图逐件看，作参考 |
| FIT Fashion History Timeline | fashionhistory.fitnyc.edu | 200 ✅ | 词条**逐篇版权**；只参考改写，勿照抄 |
| KCI 京都服饰研究所数字档案 | kci.or.jp/en/archives/ | 200 ✅ | 图像**受限**（仅供浏览参考，不可商用转载） |
| The Getty Open Content | getty.edu | 200 ✅ | CC0（约 16 万件） |

> 提示：服饰/兵器类"可商用直接引用"最强的是 **Met + Cleveland + V&A 的 CC0 部分**；FIT 文字与 KCI 图只能当"形制研究"输入，产出时改写为自己设定文字。

---

## 4. 政体/制度/法律史

### Constitute Project（各国宪法全文，可对比条款）
- `constituteproject.org` 直连 200 ✅。现行宪法全文、按主题检索、国与国对比。
- **许可：禁止商业使用**（Terms："commercial use is expressly prohibited"）。→ 只用于**内部设定研究**；产出商用文本时，把宪法条款**改写**为虚构政体条款，不整段照搬。
- 归属：Comparative Constitutions Project（UT Austin + U Chicago）。

### Comparative Constitutions Project（比较政体数据集）
- `comparativeconstitutionsproject.org` 直连 200 ✅。学术数据集，供下载。

### 贵族爵位/官制对照
- 无单一权威开放库。可行组合：Constitute 条款（非商用研究）+ Gutenberg/Perseus 史料原文（公版）+ **Wikipedia**（被墙，需代理）+ Burke's Peerage（商业库，勿用）。
- 学术补充：V-Dem（Varieties of Democracy）、Polity IV 数据集（免费学术用）。

---

## 5. 地理/气候/物产

### Natural Earth（❌ 直连失败，数据本身公有领域）
- `naturalearthdata.com` 实测 `000 0.26s`（DNS 失败）；GitHub 镜像 `github.com/nvkelso/natural-earth-vector` 也 `000 8.0s`（GitHub 被墙）。
- 许可：全量矢量/栅格地图数据**公有领域**（官网 Terms 确认）。有代理后是首选基础地理底图。

### David Rumsey 历史地图库
- `davidrumsey.com` 直连 200 ✅。18–19 世纪海量高清历史地图。
- **许可：CC BY-NC-SA 3.0**（版权页确认）。个人/免费出版物可用（需署名），**商用需另行联系**；地图单张复刻出售需授权。
- 对创作用处：真实历史海岸线/疆域/城市形态做"西式地图"**内部参照**；商用产品中不要直接嵌图。

### 气候数据
- WorldClim `worldclim.org` 直连 200 ✅（栅格气候数据，开放）。NOAA/ERA5 待进一步评估。

### 地名库
- GeoNames `api.geonames.org` 实测 `000 0.43s`（失败）；数据本身 **CC BY 4.0**（需署名）。
- OpenStreetMap `openstreetmap.org` 实测 `000 8.0s`（被墙）。

---

## 6. 命名学

### Behind the Name（人名/地名词源）
- `behindthename.com` 直连 200 ✅。西方人名+地名词源，附**真实语言/文化标签**（对"某文明取什么名字"极有用）。
- **许可（关键，来源 /info/copyright 与 /info/licensing）**：
  - **词义/历史解说文字不开放**，禁止抓取/转载；仅允许"少量"展示并回链。
  - 名字/性别/usage/相关名等**结构化数据**可付费授权（内部/后台用，不得公开再分发、不得转售）。
  - 第三方项目（如 Evennia）曾以 **CC BY-SA 4.0** 引用其 name 数据 → 即 name 数据存在 CC BY-SA 子集，但官方条款更严。
- 结论：**选名参考改写可用；不要把整库搬进产品。** 需要批量真实人名列表时，改用下文的公有领域官方统计。

### 官方姓名统计（公有领域，curl 被反爬拦截但数据开放）
| 源 | URL | 实测 | 许可 |
|---|---|---|---|
| 美国人口普查局姓氏 | census.gov/topics/population/genealogy | 403（反爬） | **公有领域**（美国政府作品） |
| 美国 SSA 婴儿名 | ssa.gov/oact/babynames/ | 403（反爬） | **公有领域** |
| 英国 ONS 婴儿名 | ons.gov.uk | 200 ✅ | Open Government Licence |
| Etymonline（词源） | etymonline.com | 403（反爬） | **受版权保护**（参考，勿转载） |

> census.gov/ssa.gov 是反爬拦截（curl 403），浏览器或带真实 UA/会话可下数据文件；数据本身公有领域，可自由用于命名卡样本。

---

## 7. 宗教/神话

### Sacred Texts Archive
- `sacred-texts.com` 直连 301 ✅。宗教/神话/民俗**公版文本**大合集（多语言多传统）。
- 许可：所收文本多为公有领域；其 HTML 转写页有网站版权，**文本可引，页面勿整站搬运**。

### Theoi Greek Mythology（❌ 直连失败）
- `theoi.com` 实测 `000 8.0s`。希腊神话权威资料站；文字是其自译、图像来自博物馆，**整体非商业授权**。被墙下不可用。

### Perseus（见 §2）— 神话/宗教一手原文最佳来源之一，直连 200 ✅。

---

## A. 版权与许可分域

| 域 | 典型源 | 可否商用 | 需否署名 | 边界 |
|---|---|---|---|---|
| **公有领域文本** | Gutenberg、Standard Ebooks、Sacred Texts、Perseus 古文本、Wikisource | ✅ 可 | 否（PG 有商标条款） | 直接引用/改写均可；PG 转载保留其 License 页 |
| **CC0 图像与元数据** | Met、Smithsonian(2D)、Cleveland、Getty Open Content、V&A 部分、Rijksmuseum(PD)、Europeana 元数据、Natural Earth、Wikidata | ✅ 可 | 否 | 图像/元数据可直接用；逐件核对个别例外 |
| **CC BY 类数据** | GeoNames(CC BY 4.0)、Europeana 部分预览图、Rijksmuseum 历史元数据 | ✅ 可 | ✅ 需署名 | 数据可用但保留 attribution |
| **CC BY-NC(-SA)** | David Rumsey 地图(CC BY-NC-SA 3.0) | ❌ 商用受限 | ✅ 需署名 | **只作内部研究/参考改写，不可商用发布** |
| **明确禁止商用** | Constitute Project 条款 | ❌ 禁商用 | — | 只作内部设定研究，产出时改写为虚构条款 |
| **需申请 key 的 API** | Smithsonian、Europeana | 依许可 | 依许可 | key 免费，限流/用途条款要看 |
| **受限整理本/词条** | Behind the Name 词义、Theoi 译文、KCI 图、FIT 文章、Etymonline | ❌ 不可再分发 | — | **只作"参考改写"素材，禁止抓取/整段引用** |
| **公有领域官方统计（反爬）** | census.gov 姓氏、ssa.gov 婴儿名 | ✅ 可 | 否 | 数据开放但需浏览器/会话下载 |

### "可直接引用" vs "只可参考改写" 边界（一句话原则）
- **可直接引用/直接用**：公有领域文本（摘录原文）、CC0/CC BY 图像与数据（含署名）、CC0 元数据、美国政府公有领域统计。
- **只可参考改写**：CC BY-NC(-SA) 内容（只能研究，不能把素材图/文本放进商用产品）、Constitute 条款（禁商用）、受限词条与译文（把"词源/形制结论"转写成自己的设定文字，而非复制原文）、一切"逐件看 rights"的博物馆预览图。
- 设定卡片（§B）引用源时，**每条记下许可标签 + 来源 URL**，产出商用文本时据此过滤。

---

## B. 多来源资料 → 小说设定卡片模板

### 设计原则
- 每张卡 = 结构化字段表 + **来源/许可**字段（用于后续合规过滤）。
- 字段分两类：`事实字段`（来自真实资料，抄录/翻译）+ `设定字段`（世界观内的决定，标"已定/待定"）。

### B1. 服饰/器物卡
| 字段 | 类型 | 说明 | 示例 |
|---|---|---|---|
| id / 名称 | str | 物品名（中+原文） | doublet 紧身上衣 |
| 时代/地区 | str | 真实对应时代·地区 | 16 世纪英国 |
| 功能/场合 | str | 礼仪/军/日常/宗教 | 宫廷礼服 |
| 材质与工艺 | str | 织物/金属/装饰 | 天鹅绒、金线刺绣 |
| 形制描述 | text | 真实形制（参考改写） | 耸肩、束腰、开襟… |
| 社会等级信号 | str | 谁穿/谁不能穿 | 贵族专属 |
| 来源 URL + 许可 | str | 引用记录 | Met obj id / CC0 |
| 世界观映射 | text | 在本故事中如何化用 | 改名 X 礼服 |

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
| 来源+许可 | str | 例：Constitute（非商用） |

### B3. 地理/气候/物产卡
| 字段 | 类型 | 说明 |
|---|---|---|
| 名称/类型 | str | 王国/城市/海岸/山脉 |
| 真实参照 | str | 例：参照 18c 地图的莱茵河谷 |
| 气候带/季相 | str | 温带海洋性等（WorldClim 参考） |
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
| 真实人名样本 | list | 从 BtN(受限)/SSA·Census·ONS(PD) 取 |
| 地名构成规则 | text | -burg/-ton/-heim 等 |
| 音系约束 | text | 保证同族名字"听感一致" |
| 禁忌/避讳 | str | 王族名不得复用等 |
| 来源+许可 | str | Behind the Name(受限) / SSA(PD) |

### 公开 worldbuilding bible 模板先例（附 URL）
- 22 问故事优先世界设定模板：`https://theselfpublishingsite.com/tools/worldbuilding-template`
- K.M. Weiland 六要素 + World Anvil 结构归纳：`https://showmemybook.com/guides/world-building-bible-template`
- Notion "Author Story/Series Bible"：`https://www.notion.com/templates/author-story-series-bible`
- Melon Pope World Bible Template：`https://melonpope.neocities.org/worldbuilding`
- 11 页可商用 Story Bible（PDF/MD/DOCX 免费下载）：`https://nanowritlabs.com/blog/story-bible-template`

---

## 附：关键工程注意点
- **Met search 端点已 410**，代码里不要再用 `GET /search`，改用 `objects?departmentIds=` + `objects/<id>` 两步。
- **Rijksmuseum 旧 API 已 410**，改用 `data.rijksmuseum.nl/search/collection`（免 key）与 `id.rijksmuseum.nl/<id>` 解析器。
- **V&A / Perseus / Met dept 检索偏慢**（3–6s），客户端超时设 ≥15s。
- **Wikimedia/IA/GitHub/OSM/GeoNames 全被墙**：若后续加代理，Wikidata SPARQL（CC0）与 Natural Earth（PD）是最高价值补充。
- **反爬 403（census/ssa/etymonline）**：数据开放但需浏览器/会话下载，不适合服务端 curl 直取。
