# P4-4D2B.1 Source Unblock & Real Evidence Intake

> Current status: [docs/RESEARCH_CURRENT_STATE.json](RESEARCH_CURRENT_STATE.json).
> HISTORICAL SNAPSHOT: the report and its machine tables below retain their original observations.

> 最新单场官方 Pilot：2041790 的 Gate A PASS，`jc-football-official-pilot` 已 SEALED。
> Gate C/B 与全部 Replay cutoff 继续 BLOCKED；见 [当前报告](SPORTTERY_GATE_A_REPORT.md)。
> 下文为较早阶段历史报告，原始来源决策不回写。

结论：**BLOCKED**。已取得新浪单场带时间的真实外部赔率变动记录；仍未取得可验证的体彩官方目标，新浪数据也未完成正式 Replay 准入。完成离线 intake、响应检查和 Git-safe manifest 工具，停止在本阶段，不扩大三个赛季，不开始模型开发。

## 真实证据与逐项结果

- 本轮在既有 2026-09-26～28 窗口执行一次普通官方历史请求，仍为 HTTP 567。仅保留验证 HTML，没有重试、代理轮换、Cookie 伪造、请求伪装或浏览器自动化。
- 用户确认暂无手工保存的官方文件。因此没有真实离线 JSON/HTML intake；测试文件全部明确为 synthetic。
- 没有真实 Sporttery 比赛 JSON，实际 Observed Schema 为验证 HTML；比赛字段、球队 ID、kickoff 均未观测到。`EXPECTED_FROM_JS` 仅为前端字段参考。
- 没有真实 getOddsHistoryV1 响应；未编造 matchId 请求它。`updateDate/updateTime` 及其时区/含义没有得到真实记录验证，保持 `TIMESTAMP_SEMANTICS_UNVERIFIED`，回放时间和 basis 均为 NULL。
- 环境及 `.env` 均无 `ODDS_PROVIDER_API_KEY`，状态为 `BLOCKED_MISSING_CREDENTIAL`。本轮没有发送 The Odds API 历史请求；原 D2B 匿名 401 原件仍保留。没有该供应商的真实 envelope 或 snapshot timestamp；新浪赔率时刻另见下段。
- 没有 Target、Result 或球队映射被生成；未创建 BUILDING、SEALED 或 Research Run，Dataset hash 无。Gate A～F 逐项原因见机器表。
- odds-api.net 与 Betfair 继续作为候选发现；公共文档的示例不是历史快照。本轮未开通账号、购买服务或取得授权数据。来源、时间字段与许可依据见 [RESEARCH_SOURCES](RESEARCH_SOURCES.md)。

## 后续“立即同步”核对（2026-10-01）

用户反馈项目“立即同步”成功后，只读核查了当前数据库。北京时间 18:51:13 的 sporttery matches
记录为 SUCCESS、records=49；18:51:14 的 odds 记录为 SUCCESS、records=46。
两条关联 Raw 均为 `mock=true`，`source_url=fixture://sporttery.json`；当前配置 `DEMO_MODE=true`。
成功状态来自本地演示 fixture 的导入，处理数不能计入真实 Target 或真实历史赔率。

同日 10:54:01.764998 UTC，对原历史接口按原日期参数执行一次普通复测，仍为 HTTP 567，
未取得比赛 JSON。已追加保存 Raw 和 manifest，没有切换演示模式、修改 LIVE provider 或重试绕过验证。

## 新浪历史数据发现（2026-10-01）

用户提供新浪开奖页后，已通过其公开接口取得真实第三方历史 JSON：
2026-09-26 返回 24 条、2025-09-26 返回 18 条；2026-10-01 本次返回空列表。
原件先保存，随后检查到比赛 ID、`tiCaiId`、球队、比分、半场比分及五类竞彩 SP / 开奖奖金。
字段与样本计数详情见 [新浪来源实测](RESEARCH_SOURCES.md)。

这些第三方记录尚未规范化导入，不能计作 VERIFIED Sporttery Target。
这些开奖接口记录不含逐条历史赔率快照时刻；响应 `_timestamp` 对齐本次取数时间，不能计入赛前 cutoff coverage。

用户随后提供指数页截图，已进一步取得截图对应比赛 `3867328` 的独立公司变动 JSON。
同一公司来源 ID `2`（显示名 `36*`）返回完整胜平负 12 条、让球 42 条、总进球 49 条，均带 `oddsTime`。
页面代码确认按 Unix 秒显示赔率变动时间；胜平负首条是 2026-09-28T06:46:39Z，主/平/客 1.20 / 5.50 / 12.00。
所以“真实历史赔率候选已取得”；不能再把它与无时刻的开奖 SP 混为一谈。

最新记录有开球后数据，让球/总进球还有同秒多盘口记录。公司映射、历史可见性及研究使用许可尚未核验，
`replay_available_at` 与 basis 均保持 NULL。没有导入、Target 验证或 SEALED。
正式 coverage 仍为 0；机器表的 `replay-qualified external historical odds` 明确只计通过 Replay 准入的数据。
`historical_envelope_count` 仅指 The Odds API envelope；新浪三个真实变动响应单独机器计数，详见 [来源实测](RESEARCH_SOURCES.md)。

## VIPC 单场证据核验（2026-10-01）

固定 `matchId=498257749`、公司 `432`（显示名香港**）、1X2 历史，已取得详情、公司列表、
公司历史三份真实业务 JSON。全部先保存 Raw，再离线检查。
身份、API→JS→UI 字段对应、时间原值、候选截点及逐项结果见 [VIPC_SOURCE_REPORT](VIPC_SOURCE_REPORT.md)。
其机器统计与 candidate 由 `jc.research.vipc_evidence` 从已保存原件生成，不手工维护第二套行数。

`updateTime` 不带时区；根据 detail 中 `matchTime=2026-09-30 14:00:00` 与
`liveTime=2026-09-30T06:00:00Z` 的 +08 对齐关系及页面模板直接展示 `updateTime` 的行为，
暂以 `Asia/Shanghai` 作为仅用于 candidate cutoff 的解析假设；正式时区及 availability 语义未由来源文档确认。
`timezone=NULL`、`candidate_timezone=Asia/Shanghai`、`timezone_status=ASSUMED_FOR_CANDIDATE_ONLY`，
`replay_available_at/availability_basis` 均保持 NULL。
robots 明确排除 `/i/*`，许可为 RESTRICTED；发现后已停止网络取数。
VIPC source decision 为 UNVERIFIED，Gate A/B 仍 BLOCKED，没有 Replay、SEALED 或规模扩展。
累计 manifest 新增 `vipc_1x2_history_response_count`，只数观测响应，不认证快照或 Gate。
验收收尾已重跑 SQLite 与 PostgreSQL 全量：各 **857 passed、1 skipped**（跳过 opt-in 真实网络测试）；
`ruff check apps/api/src tests`、`mypy apps/api/src`（50 个 source files）及 `git diff --check` 均通过。
全部指定统计、三个 candidate 及已保存文件哈希在回归前后保持一致；详见 [验收记录](VIPC_SOURCE_REPORT.md#离线复核)。

## 可复现入口

用户通过正常浏览器保存单个响应后执行（时间必须是实际采集时间并含时区）：

```powershell
.venv/Scripts/python.exe -m jc.research.official_evidence --input <local-file> --source-url <official-https-url> --retrieved-at <timestamp-with-timezone>
```

只接受四个明确列出的 Sporttery 官方 HTTPS host；HTTP 拒绝。任务测试列表中的“HTTP 官方域允许”与正文“只接受 HTTPS”冲突，按 HTTPS-only 实施。
完整 HAR 不接受，须先由用户选出单个 response body；不会读取或保存 HAR 请求头、Cookie 或凭据。被 secret scan 拒绝的文件不复制。安全原件以可还原字节的 text payload、编码和响应 SHA-256 保存，再执行 schema inspection。
HTML 保留供复核，支持检查内嵌 application/json；没有真实页面 schema 时不猜表格/JavaScript，不产生 Match。官方域仅核验来源声明，不认证手工文件的真实性。

Inspector 不生成 VERIFIED。后续只有实际 Raw、池成员身份、双方球队和带时区开球时间全部复核后，才能提交现有 D2A `SPORTTERY_POOL` 证据及 `SportteryVerificationInput`；`assess_intake_gates` 再调用原 `validate_import` 校验，分别判断 A/B。单个 Target 即可走原 D2A importer，不设 50 场门槛；销售日可缺失，不能从 matchDate 推断。

`assess_intake_gates` 只评估 A/B；B 要求已核验外部来源、同公司完整 1X2 和冻结 v1 在 cutoff 可见的记录。C/D/E/F 必须从各自真实证据、导入或执行结果另行核验，不能由 A/B 推导。该函数不运行模型、不自动 seal。

已有 `jc.research.pilot` 仍是有界 discovery 命令；有凭据时只查询一个 EPL 历史 envelope，markets 为 h2h,spreads,totals。真实网络必须显式 `RESEARCH_NETWORK_ENABLED=1`；默认 pytest 不联网。envelope 的原始 timestamp/previous_timestamp/next_timestamp 进入本地报告；缺 timestamp 或时序无效时，回放时间仍为 NULL。任何 200/成功 envelope 都不能单独令来源 ACCEPTED。

## Manifest 与复核

[research-probe-manifest.json](research-probe-manifest.json) 是机器生成的累计记录，包括原 D2B 和本轮。仅含来源、公用 URL、UTC、HTTP status、原响应 SHA-256、canonical sanitized Raw hash、retention、schema/scan 状态、本地相对路径与 evidence decision；没有正文或凭据。

```powershell
.venv/Scripts/python.exe -m jc.research.probe_manifest --input artifacts/research-probes/20261001-discovery artifacts/research-probes/20261001-unblock artifacts/research-probes/20261001T105401Z-user-access-check artifacts/research-probes/20261001-sina-discovery artifacts/research-probes/20261001-sina-indicators artifacts/research-probes/20261001-vipc-discovery --blocked-report docs/PILOT_DATASET_REPORT.md
```

构建时重新检查 D2A secret guard、canonical hash、summary/Raw 一致性、路径边界；有编码且 UNCHANGED 的原件重算响应字节 SHA-256。早期 D2B 少数 Raw 缺编码元数据，明确记为 `LEGACY_BYTE_ENCODING_UNVERIFIED`，不补造编码、不宣称原字节复核成功。脱敏/withheld 原件不能成为已接受数据源。
生成稳定排序；机器表由同一 manifest 生成，CI 从已提交 manifest 重建并比较，不依赖本地 ignored Raw。出现官方 JSON / The Odds API envelope 后，报告生成器拒绝继续写当前阻塞分支，要求先复核真实证据；新浪结构观测单独计数，并不生成准入结论。

原始文件仍在 ignored `artifacts/research-probes/`；Git 中的哈希可用于比对用户本机原件，不能替代审查者获取正文后对 schema 的检查。

## 验证与边界

Source Unblock 工程阶段验证（早于后续新浪发现）：

| 检查 | 结果 |
|---|---|
| 全量 pytest（默认 SQLite 路径） | **821 passed、1 skipped**，134.23 秒；跳过项为 opt-in 真实网络测试 |
| Intake / Inspector / manifest / probe / pilot 专项 | **83 passed、1 skipped** |
| Ruff：apps/api/src + tests | 通过 |
| Mypy：apps/api/src | 通过，49 个 source files |
| Raw / manifest / report | canonical hash、summary 一致性、排序稳定重建及报告数字检查通过 |
| Alembic heads | `009_research_dataset_persistence`，单一 head；本轮未复验 PostgreSQL |
| Git 边界 | Raw 仍 ignored；`git diff --check` 通过，冻结文件无 diff |

新浪指数后续改动仅补充 manifest 结构观测、计数及报告，没有增加采集 Adapter。
此次针对性验证：`tests/test_probe_manifest.py` **17 passed**（含新增“有/无 oddsTime 均不自动准入”检查），
修改文件 Ruff 与 `git diff --check` 通过；未重复宣称全量测试已在此次修改后运行。

新增检查覆盖离线 JSON/HTML、单个 HAR body、WAF/登录/错误页、HTTP/域名/凭据拒绝、Raw-first、
observed/expected 隔离、缺失字段、D2A 官方证据、赔率时间缺失/未知语义、历史 envelope、
closing/opening 无时刻时三个 cutoff 均为零、A/B 独立、manifest 无正文/凭据、稳定排序与报告一致。
测试里的成功响应和官方声明都是合成控制流用例，没有被统计为真实 Target、历史赔率或已密封 Pilot。
保留既有 Starlette/httpx 弃用警告 1 条，没有为此修改依赖。

未改 `research-replay-v1`、D2A contracts/importer/repository、analysis_visibility、LIVE providers 或 migrations。无三赛季采集、xG、Elo、ML、Ensemble、Recommendation、EV/ROI。

<!-- BEGIN MACHINE PROBE STATUS -->
## P4-4D2B.1 机器核验

由 `python -m jc.research.probe_manifest` 与 manifest 同次生成；仅报告尚无已核验官方 Target 或外部历史快照的分支。

| 项目 | 数量 / 状态 |
|---|---|
| probe_count | 60 |
| response_raw_count | 58 |
| no_response_count | 2 |
| official_json_count | 0 |
| historical_envelope_count | 0 |
| sina_odds_history_response_count | 3 |
| vipc_1x2_history_response_count | 1 |
| accepted_source_count | 0 |
| VERIFIED Sporttery Target | 0 |
| replay-qualified external historical odds | 0 |
| T-30M / T-90M / T-360M coverage | 0 / 0 / 0 |
| Market replay evaluable | 0 |
| SEALED Pilot / Dataset hash | 无 / 无 |
| Gate A：官方 Target | BLOCKED：没有已复核官方目标比赛 |
| Gate B：外部历史赔率 | BLOCKED：没有匹配已核验官方目标且通过来源/时间准入的完整 1X2 |
| Gate C：常规时间赛果 | BLOCKED：没有目标赛果证据 |
| Gate D：稳定实体 | BLOCKED：没有已核验映射 |
| Gate E：SEALED | BLOCKED：没有实际 ResearchImport |
| Gate F：Replay | BLOCKED：没有真实 SEALED / Run |
| 扩大三个赛季 | 不允许 |

<!-- END MACHINE PROBE STATUS -->
