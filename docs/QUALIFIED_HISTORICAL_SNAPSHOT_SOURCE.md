# P4-4D2B.7 Qualified Historical Snapshot Source

2026-10-02。当前结果：**Gate A PASS / Gate B BLOCKED / Gate C BLOCKED；Gate B blocker class = NO_ACCESS**。
机器记录见 [RESEARCH_CURRENT_STATE.json](RESEARCH_CURRENT_STATE.json) 的 `historical_source_qualification`。

本轮检查进程环境与项目 `.env` 后，The Odds API credential status 为 `NOT_AVAILABLE`。
没有调用 historical 数据端点，没有使用文档示例或 synthetic response 充当真实数据。
本轮只完成准入设计、两个官方开发者服务的有限筛查、基线复核与完整测试。
没有新增 adapter、数据库迁移、真实 fixture 或 Dataset。

## 冻结基线

- Sporttery target `2041790`：乌兹别亚（canonical team `2053`）主场，日本亚（`2060`）客场；competition `83`。
- kickoff `2026-09-30T18:30:00+08:00` = `2026-09-30T10:30:00Z`。
- `jc-football-official-pilot / 2041790-official-had-v1`：1 VERIFIED target，18 HAD snapshots，54 quotes，0 Result，Replay PASS。
- 现有内容 hash：`ebf451127c7e49a308b2d75116607c2df67449e4a0cfc50d4fd003ed20fb2095`。
- 新浪 `3867327 / sina:2:1`：5 historical rows；mapping/schema VALID，timestamp encoding VERIFIED，timestamp semantics UNKNOWN，verification/license UNVERIFIED，replay BLOCKED。`replay_available_at`、`availability_basis` 仍为 NULL。

`external_qualification` 原对象完整保留，其 canonical SHA-256 另存于本轮 metadata。
不将新浪 `oddsTime` 解释为任何 availability basis。
冻结 replay-v1、D2A、analysis_visibility 与两份 SEALED Dataset 均未修改；生产数据库只读核验。

## The Odds API：文档证明与实际证据分开

[官方 v4 文档](https://the-odds-api.com/liveapi/guides/v4/#get-historical-odds)说明
`/v4/historical/sports/{sport}/odds` 返回历史快照，`date` 选择不晚于该时刻的最近快照，
`timestamp` 是实际快照时刻，`previous_timestamp` / `next_timestamp` 为相邻快照时刻。
历史权限属于付费计划；sport、market、bookmaker 的历史覆盖只能从加入服务时起计算。
这确立了**文档中的 snapshot 语义**，没有证明 2041790 被覆盖，也没有形成真实 envelope。

[官方使用条款](https://the-odds-api.com/terms-and-conditions.html)（页面更新日期 2026-08-31）明确允许研究、
分析及长期本地保留，禁止将原始数据作为独立数据产品再分发。
本轮 `license/use = VERIFIED` 仅限按有效订阅取得的数据用于本地研究、私有保留；
不表示账号已注册、历史订阅可用或原始数据可提交 Git。

| 独立检查 | 当前结论 | 转为通过所需证据 |
|---|---|---|
| Transport | NOT_TESTED_NO_KEY；文档 HTTP 200 | 有权限的真实 historical HTTP 响应；错误/空响应独立分类 |
| Schema | DOCUMENTED_NOT_OBSERVED | 保存 Raw 后核对 envelope 四字段及 data[] 的真实结构 |
| Match identity | UNVERIFIED | event ID、主客顺序、精确 kickoff、competition/sport 与官方目标逐项一致 |
| Bookmaker identity | UNVERIFIED | 真实返回且非空、无歧义的 bookmaker key |
| 1X2 mapping | DOCUMENTED_NOT_OBSERVED | 同一 envelope、同一 event、同一 bookmaker 的 h2h HOME/DRAW/AWAY |
| Historical timestamp | DOCS_VERIFIED_RESPONSE_UNVERIFIED | 实际 envelope 绝对时间有效，符合官方语义与 chronology |
| Availability semantics | DOCS_VERIFIED_RESPONSE_UNVERIFIED | 实际响应与文档一致；只能使用 envelope.timestamp |
| License/use | VERIFIED（上述本地研究范围） | 保留本次条款 URL、时间、hash；取得有效历史访问权限 |
| Replay | BLOCKED | 通过来源、身份、完整性与 cutoff 检查后进入原 replay/market 流程 |

因此 source `verification_status = UNVERIFIED`，实际 `replay_available_at = NULL`、`availability_basis = NULL`。
只有 time、license/use、identity 全部 VERIFIED，且其余检查通过，才作显式、有日期和依据的 source verification。
已有 `inspect_odds_history_payload` 只是结构检查器，不能充当来源资格证明；本轮未调用它检查任何真实 historical 响应。

## 取得权限后的最小准入流程（设计，未执行）

1. 核对可用 sport key 与目标赛事。不能沿用旧 pilot 的 `soccer_epl`，也不能把国家队名称近似匹配当作亚运队身份。
   保留人工核验说明及引用的官方/供应商证据 hash；精确核对 home、away、commence_time、sport_key/sport_title 与 competition。
   若 provider 不返回稳定 team ID，保留经复核的名称别名映射及 canonical team ID，不生成虚构 provider team ID。
2. 凭据存在才请求。先用一个 sport、T-5 的 historical events 查询定位目标，
   将 kickoff 范围限定到该场并只检查目标；后续使用真实 event ID 过滤。
   目录查询只作定位，不导入其他比赛。单次空响应、单个 cutoff 或 region 缺数据均不能证明整场不覆盖。
   覆盖不明确保持 UNVERIFIED；明确不覆盖才记 `TARGET_NOT_COVERED` 并停止。
3. 对五个 cutoff 各至多一次请求 `/v4/historical/sports/{sport}/odds`，参数只含
   `markets=h2h`、`oddsFormat=decimal`、`dateFormat=iso`、已核验 event ID、一个 region 和相应 `date`。
   选实际返回的 bookmaker，不预设品牌存在。没有真实响应前不实现 historical adapter。
4. `NO_KEY` / 明确历史计划拒绝 `PLAN_NOT_ALLOWED` / `TARGET_NOT_COVERED` 立即停止该源。
   其他鉴权/限流/网络错误保留本来类别，不伪称计划不足或目标缺失。没有重试循环、多赛季或多比赛探测。
5. HTTP response → 脱敏并持久化 Research Raw → response SHA-256 与 canonical payload hash → inspect → normalize。
   使用已有 `probe_source` / `ResearchRawArtifactInput`；URL 去凭据，不输出 key、headers 或异常 URL。
   Raw retention 为 REDACTED/WITHHELD 时不能称为完整真实赔率 envelope 或进入正式归一化。

每个真实 envelope 的准入 metadata schema（本轮没有实例）：

| 字段 | 类型 / 来源 / 约束 |
|---|---|
| provider | 固定 `the_odds_api` |
| requested_date | 带时区绝对时间；保存本次请求的原始 date，来自脱敏 request 参数 |
| timestamp | 必需，来自 envelope；保留原值并解析为 UTC；不能来自其他字段 |
| previous_timestamp / next_timestamp | 必须保留原值或显式 NULL；非 NULL 时分别严格早于/晚于 timestamp |
| retrieved_at | 本次真实响应完成接收时间；独立保存，不能代替 snapshot 时间 |
| raw_path / response_sha256 / raw_content_hash | ignored artifacts 工件定位、响应字节 hash、D2A canonical payload hash |
| external_event_id / sport_key / sport_title | 来自实际 event；跨五个 cutoff 身份一致；证据冲突即阻塞 |
| home / away / commence_time | 实际 event 值，与已核验 canonical identity 的映射说明、版本及证据 hash 同存 |
| bookmaker_key | 实际返回 key；稳定 identity `the_odds_api:<bookmaker_key>` |
| market / outcomes | 只收 h2h；HOME、DRAW、AWAY 各一条，有限 Decimal 且 > 1；重复/冲突或缺项拒绝 |
| bookmaker/market last_update | 只保留供应商观察字段；不填 published_at、effective_at 或 replay_available_at |
| replay_available_at / availability_basis | 资格通过前均 NULL；通过后仅 `timestamp / SOURCE_SNAPSHOT_AT` |
| qualification evidence | 文档/条款/映射引用与 hash、各独立检查结果、验证时间及说明 |

同一 timestamp 的完全相同 envelope 可复用同一 Raw；每次请求的 requested_date / retrieved_at 仍另存为 acquisition metadata。
同一 event/bookmaker/timestamp 出现内容冲突则阻塞，不能选最新下载覆盖历史。
缺少 timestamp、无时区、时序矛盾、snapshot 在 cutoff 之后、两项 moneyline、h2h_lay、spreads、totals 均不能进入本轮 1X2。

## Cutoff 与 Gate B

| Cutoff | requested_date / UTC 上限 | 北京时间 | 当前 |
|---|---|---|---|
| T-360 | 2026-09-30T04:30:00Z | 12:30 | BLOCKED_NO_ACCESS |
| T-90 | 2026-09-30T09:00:00Z | 17:00 | BLOCKED_NO_ACCESS |
| T-30 | 2026-09-30T10:00:00Z | 18:00 | BLOCKED_NO_ACCESS |
| T-15 | 2026-09-30T10:15:00Z | 18:15 | BLOCKED_NO_ACCESS |
| T-5 | 2026-09-30T10:25:00Z | 18:25 | BLOCKED_NO_ACCESS |

每个 cutoff **先选最近的 timestamp <= cutoff 的 envelope，再检查其中 bookmaker 的完整 1X2**。
不能先筛完整行再退回更旧快照；最新 envelope 缺项时该 bookmaker 在此 cutoff 阻塞。
不跨 envelope、event、bookmaker 拼接，不允许 closest-after；timestamp 还必须 <= retrieved_at 且严格赛前。
对五个日期精确请求时，next_timestamp 若非 NULL 应晚于 requested_date，否则“最近”性质未成立，阻塞复核。

未来 adapter 在原 `assess_intake_gates` 前完成以上 envelope 选择：该 helper 接受 quotes，
无法表示完全缺失的较新 envelope，单独调用它不能证明本轮最近快照规则。
不要为此修改冻结的 `build_research_feature` 或 D2A contract。

在内存中构造带 Raw provenance 的候选 ResearchImport，复用 `validate_import`，
按每个 cutoff 将已选完整 snapshot 交给 `build_research_feature` → `build_market_data`。
只有 VERIFIED 官方目标、VERIFIED 外部来源、同一 canonical target、完整赛前 1X2、
可靠 replay_available_at / availability_basis 同时具备，且实际 source_count >= 1、p_market 非 NULL，才允许 Gate B PASS。
逐个报告五个 cutoff 的 coverage；不得将一个可用 cutoff 说成五个全部可用。

只有实际 Gate B PASS 才用原 D2A importer 创建并封存
`jc-football-official-pilot / 2041790-external-1x2-v1`（1 VERIFIED target、54 HAD quotes、合格外部 quotes、0 Result）。
版本已存在时仅允许幂等核验，不能覆盖旧内容。封存后重新 load/replay 校验。
仅报告 external consensus、官方 HAD no-vig 及 `external_consensus - sporttery` 的 market disagreement。
不引入 Edge、EV、Recommendation 或其他模型；Gate C 仍因缺真实 finished_at 而 BLOCKED。

## 两个官方候选的有限筛查

只阅读官方 API 文档与条款，不请求其比赛数据，不逆向展示页面；本轮筛查到此停止。

| 独立检查 | Odds-API.io | OpticOdds |
|---|---|---|
| Transport | 文档 HTTP 200；数据 API NOT_TESTED | 文档 HTTP 200；数据 API NOT_TESTED |
| Schema | 历史文档是 settled event 的 closing odds，实际响应未观察 | 历史文档是赔率变化记录；snapshot 文档是当前同步，实际响应未观察 |
| Match identity | 2041790 的 event/主客/开球/赛事均 UNVERIFIED | 同左，UNVERIFIED |
| Bookmaker identity | 文档使用 bookmaker 名；未观察目标实际公司，UNVERIFIED | 文档使用 sportsbook id/name；未观察目标实际公司，UNVERIFIED |
| 1X2 mapping | 文档示例有 home/draw/away；真实三项未核验 | 未取得本目标完整三项，UNVERIFIED |
| Historical timestamp | 文档 updatedAt 并非任意时点 snapshot envelope 证明 | 历史 timeseries 为检测到的逐项变化；不能等同完整 envelope |
| Availability semantics | 任意历史 cutoff 的绝对 snapshot 语义 UNVERIFIED | 当前 snapshot 保留每条 odds 的更新时间，历史 snapshot 语义不满足 |
| License/use | 官方条款明确研究用途；本地研究范围 VERIFIED，账号权限未测试 | 已查公开条款未取得明确本地研究/长期保留授权，UNVERIFIED |
| Replay | BLOCKED；不满足本轮 snapshot 准入条件，停止 | BLOCKED；不满足本轮 snapshot 准入条件，停止 |

两者 source verification 均 UNVERIFIED；不会因为停止筛查而声明 TARGET_NOT_COVERED。
Odds-API.io 的 [historical 指南](https://docs.odds-api.io/guides/historical)限定为 closing odds，
其 [条款](https://odds-api.io/terms)允许研究但限制再分发；仅有使用许可不足以满足本轮历史快照要求。
OpticOdds 的 [historical 接口](https://developer.opticodds.com/reference/get_fixtures-odds-historical)
区分逐项变动；[Snapshots API](https://developer.opticodds.com/docs/snapshots)是当前状态同步，
时间来自每条赔率更新；[公开条款](https://opticodds.com/terms-of-service)未提供本轮所需明确授权。
这是所审阅端点的筛查结果，不声称供应商全部产品都没有其他能力。

## 工件与最短解阻路径

所有新 HTTP 文档工件、原状态备份、只读基线快照和测试日志都在
`artifacts/research-probes/20261002-qualified-history/`（Git ignored）。
当前状态仅保存 URL、获取时间、hash、retention、资格结论及计数；没有新增真实 provider Raw fixture。
文档 HTML 中的凭据示例/脚本可能触发现有 secret guard，REDACTED/WITHHELD 如实登记；
这不是赔率请求失败，浏览器官方文本核验也不替代真实 historical 响应。

最短路线：先请 The Odds API 确认该场亚运队赛事的历史覆盖及 sport key，
然后在本机配置具备 historical 权限的 `ODDS_PROVIDER_API_KEY`，按上述单场五 cutoff 请求复核。
不在聊天中粘贴 key；如果确认不覆盖，停止该源，获取具有同样时间语义与本地研究许可的单场官方 API 授权数据。
本轮主 blocker 为 `NO_ACCESS`（`NO_KEY`），不是未经实测的 `NO_TARGET_COVERAGE`。
