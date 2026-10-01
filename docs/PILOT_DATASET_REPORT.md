# P4-4D2B.1 Source Unblock & Real Evidence Intake

结论：**BLOCKED**。本轮完成离线 intake、实际响应 Inspector、历史 envelope 时间检查和 Git-safe manifest 工具；未取得可验证的官方目标比赛或外部历史赔率。停止在本阶段，不扩大三个赛季，不开始模型开发。

## 真实证据与逐项结果

- 本轮在既有 2026-09-26～28 窗口执行一次普通官方历史请求，仍为 HTTP 567。仅保留验证 HTML，没有重试、代理轮换、Cookie 伪造、请求伪装或浏览器自动化。
- 用户确认暂无手工保存的官方文件。因此没有真实离线 JSON/HTML intake；测试文件全部明确为 synthetic。
- 没有真实 Sporttery 比赛 JSON，实际 Observed Schema 为验证 HTML；比赛字段、球队 ID、kickoff 均未观测到。`EXPECTED_FROM_JS` 仅为前端字段参考。
- 没有真实 getOddsHistoryV1 响应；未编造 matchId 请求它。`updateDate/updateTime` 及其时区/含义没有得到真实记录验证，保持 `TIMESTAMP_SEMANTICS_UNVERIFIED`，回放时间和 basis 均为 NULL。
- 环境及 `.env` 均无 `ODDS_PROVIDER_API_KEY`，状态为 `BLOCKED_MISSING_CREDENTIAL`。本轮没有发送 The Odds API 历史请求；原 D2B 匿名 401 原件仍保留。没有真实 envelope 或 snapshot timestamp。
- 没有 Target、Result 或球队映射被生成；未创建 BUILDING、SEALED 或 Research Run，Dataset hash 无。Gate A～F 逐项原因见机器表。
- odds-api.net 与 Betfair 继续作为候选发现；公共文档的示例不是历史快照。本轮未开通账号、购买服务或取得授权数据。来源、时间字段与许可依据见 [RESEARCH_SOURCES](RESEARCH_SOURCES.md)。

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
.venv/Scripts/python.exe -m jc.research.probe_manifest --input artifacts/research-probes/20261001-discovery artifacts/research-probes/20261001-unblock --blocked-report docs/PILOT_DATASET_REPORT.md
```

构建时重新检查 D2A secret guard、canonical hash、summary/Raw 一致性、路径边界；有编码且 UNCHANGED 的原件重算响应字节 SHA-256。早期 D2B 少数 Raw 缺编码元数据，明确记为 `LEGACY_BYTE_ENCODING_UNVERIFIED`，不补造编码、不宣称原字节复核成功。脱敏/withheld 原件不能成为已接受数据源。
生成稳定排序；机器表由同一 manifest 生成，CI 从已提交 manifest 重建并比较，不依赖本地 ignored Raw。出现真实 JSON/envelope 后，no-evidence 报告生成器拒绝继续写全零报告，要求先复核真实证据。

原始文件仍在 ignored `artifacts/research-probes/`；Git 中的哈希可用于比对用户本机原件，不能替代审查者获取正文后对 schema 的检查。

## 验证与边界

本轮最终验证：

| 检查 | 结果 |
|---|---|
| 全量 pytest（默认 SQLite 路径） | **821 passed、1 skipped**，134.23 秒；跳过项为 opt-in 真实网络测试 |
| Intake / Inspector / manifest / probe / pilot 专项 | **83 passed、1 skipped** |
| Ruff：apps/api/src + tests | 通过 |
| Mypy：apps/api/src | 通过，49 个 source files |
| Raw / manifest / report | canonical hash、summary 一致性、排序稳定重建及报告数字检查通过 |
| Alembic heads | `009_research_dataset_persistence`，单一 head；本轮未复验 PostgreSQL |
| Git 边界 | Raw 仍 ignored；`git diff --check` 通过，冻结文件无 diff |

新增检查覆盖离线 JSON/HTML、单个 HAR body、WAF/登录/错误页、HTTP/域名/凭据拒绝、Raw-first、
observed/expected 隔离、缺失字段、D2A 官方证据、赔率时间缺失/未知语义、历史 envelope、
closing/opening 无时刻时三个 cutoff 均为零、A/B 独立、manifest 无正文/凭据、稳定排序与报告一致。
测试里的成功响应和官方声明都是合成控制流用例，没有被统计为真实 Target、历史赔率或已密封 Pilot。
保留既有 Starlette/httpx 弃用警告 1 条，没有为此修改依赖。

未改 `research-replay-v1`、D2A contracts/importer/repository、analysis_visibility、LIVE providers 或 migrations。无三赛季采集、xG、Elo、ML、Ensemble、Recommendation、EV/ROI。

<!-- BEGIN MACHINE PROBE STATUS -->
## P4-4D2B.1 机器核验

由 `python -m jc.research.probe_manifest` 与 manifest 同次生成；仅报告尚无真实数据的分支。

| 项目 | 数量 / 状态 |
|---|---|
| probe_count | 32 |
| response_raw_count | 30 |
| no_response_count | 2 |
| official_json_count | 0 |
| historical_envelope_count | 0 |
| accepted_source_count | 0 |
| VERIFIED Sporttery Target | 0 |
| external historical odds | 0 |
| T-30M / T-90M / T-360M coverage | 0 / 0 / 0 |
| Market replay evaluable | 0 |
| SEALED Pilot / Dataset hash | 无 / 无 |
| Gate A：官方 Target | BLOCKED：没有已复核官方目标比赛 |
| Gate B：外部历史赔率 | BLOCKED：没有匹配目标的完整 1X2 与快照时间 |
| Gate C：常规时间赛果 | BLOCKED：没有目标赛果证据 |
| Gate D：稳定实体 | BLOCKED：没有已核验映射 |
| Gate E：SEALED | BLOCKED：没有实际 ResearchImport |
| Gate F：Replay | BLOCKED：没有真实 SEALED / Run |
| 扩大三个赛季 | 不允许 |

<!-- END MACHINE PROBE STATUS -->
