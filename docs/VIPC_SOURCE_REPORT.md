# VIPC 单场 1X2 历史证据核验

核验日：2026-10-01。范围固定为 VIPC `498257749`、韩国 U23 vs 中国 U23、
公司 `432`（后台显示 `香港**`；用户描述 `香港***`）、European 1X2。
**技术上值得保留为新浪之外的第二候选源；当前 source decision 为 UNVERIFIED，尚不能正式接入 Replay。**
没有扩展到其他比赛或公司的历史，没有查询让球/总进球接口。

## 实际 API 与原件

| 用途 | 实际公开 API | HTTP / Raw |
|---|---|---|
| 比赛详情 | https://www.vipc.cn/i/match/football/498257749 | 200 / UNCHANGED |
| 公司列表及当前/初始欧赔 | https://www.vipc.cn/i/match/football/498257749/odds/euro | 200 / UNCHANGED |
| 指定公司完整响应列表 | https://www.vipc.cn/i/match/football/498257749/odds/euro/432 | 200 / UNCHANGED |

发现链：[目标页面](https://www.vipc.cn/live/football/498257749#/pl/op)
→ 页面引用的 `/js/app/match3-football.js?v=20260410`
→ `base / oddsOp / oddsOpChanges` 公开相对路径
→ `/js/app/render-common.js` 的普通同源 GET。
没有认证请求头、登录、伪造 Cookie、Token 破解、代理或自动浏览器操作。
页面、公开 JS、许可页、robots 与三个 API 的本轮普通 HTTPS 响应全部先经现有 secret guard，
保存 `ResearchRawArtifactInput` 后才解析。页面/部分 JS 的 guard 脱敏如实标为 REDACTED；
业务 JSON 均为 UNCHANGED。没有重新取数以绕过脱敏或访问限制。

原件在 ignored `artifacts/research-probes/20261001-vipc-discovery/`；
每次本机 probe 的 URL、UTC、HTTP、字节 SHA-256、sanitized canonical hash、相对路径和状态进入
[机器 manifest](research-probe-manifest.json)。Git 不包含响应正文或全部历史行。
网页搜索工具的页面抓取失败不代表本机 HTTPS 失败；以上成功状态只来自已保存的本机响应。

## 身份及字段交叉核验

详情实际字段 `model.matchId=498257749`，`model.home=韩国U23`、`model.guest=中国U23`，
`model.matchTime=2026-09-30 14:00:00`；`room.liveTime=2026-09-30T06:00:00.000Z` 与用户提供的开球时刻一致。
`homeTeamId=4457`、`guestTeamId=4219` 只是 VIPC 命名空间的球队 ID。
`model.startTime=2026-09-30 15:01:07` 与预定开球不同，不能覆盖指定 kickoff；其含义未核验。

公司列表和历史响应均明确 `companyId="432"`；JS 将该 ID 放入历史 API 路径。
历史顶层是 `issue,companyId,companyName,list`；列表与详情的 `issue=202609303001` 一致。
未发现 `offerId` 或 `companyCode`，保持 NULL，不造 `:1` 后缀。
本次身份为 `provider=vipc, bookmaker=vipc:432, market=1X2`；
这证明本次跨接口身份一致，不证明跨年代永不重用、也不证明其与新浪某 ID 是同一家公司。
脱敏名称只保存为 display_name，不猜机构全名。
`issue` 仅作 `official_mapping_candidate`，不能产生 Sporttery VERIFIED。

| 选择 | API 原字段 | 公开页面模板与 UI |
|---|---|---|
| HOME | `list[i].odds[0]` | `tml_pl_op_changes` 的“胜”列，比赛主队为 `model.home` |
| DRAW | `list[i].odds[1]` | 同一模板“平”列 |
| AWAY | `list[i].odds[2]` | 同一模板“负”列，比赛客队为 `model.guest` |

`match3-football.js` 的公司点击回调使用 `oddsOpChanges(matchId,companyId)`，
再把 API 数据直接传给 `pl_op_changes` 模板；模板按上述字段显示赔率，没有重排。
UI 交叉核验依据真实 HTML 中的渲染模板及用户提供的显示值；没有声称自动操纵浏览器完成视觉点击。
所有计算复用现有 Decimal 赔率解析器，要求 finite 且 > 1；不接受二进制 float 替代原始字符串，
不借返还率反推缺失价格。

## 时间、完整性与泄漏边界

`raw_time_field=updateTime`；例如原始 `2026-09-30 13:27:00`。
`time_unit=WALL_CLOCK_STRING_SECONDS`：完整年月日时分秒文本，**不是 Unix 秒/毫秒**。
本次所有秒值均为 `00`，不能由格式推断供应商具有秒级采样精度。
页面模板用 `updateTime.slice(5,-3)` 显示 `09-30 13:27`，没有时区转换。

接口未附时区。根据本次比赛 detail 中 `matchTime=2026-09-30 14:00:00` 与
`liveTime=2026-09-30T06:00:00Z` 的 +08 对齐关系，以及页面模板直接展示 `updateTime` 的行为，
暂以 `Asia/Shanghai` 作为候选解析假设。该假设仅用于 candidate cutoff 计算；
VIPC `updateTime` 自身的正式时区及 availability 语义尚未由来源文档确认。
例如上述原始时刻得到候选 `parsed_utc=2026-09-30T05:27:00Z`。
因此 `timezone=NULL`、`candidate_timezone=Asia/Shanghai`、`timezone_status=ASSUMED_FOR_CANDIDATE_ONLY`。
下面所有赛前计数和候选 UTC 均受这个假设约束，不是正式可用性时间。

UI 称“更新时间”，但没有文件证明这是 A 博彩公司生效、B VIPC 采集、C 页面记录更新、
还是 D 后补业务时间。本轮结论为 **E：无法确认**，
`AVAILABILITY_SEMANTICS_UNVERIFIED`；所有 `replay_available_at/availability_basis=NULL`。

历史 API 一次返回全部 `list`，JS 无分页/游标/更多历史请求。本轮保留它返回的全部记录，
不宣称已证明供应商从开盘起无缺漏、无截断或无事后回填。
严格按 `timestamp < kickoff` 分类 PREMATCH，等于及以后为 INPLAY_OR_POST_KICKOFF；
后者只留证，不进入任何 candidate 或赛前 Feature。三个候选均取 `timestamp <= cutoff` 的最近完整 1X2。
不存在正式 ResearchOddsSnapshot、ResearchImport、SEALED 或 Feature 写入。

同价格不同时间全部保留。相同时刻完全相同内容标记 `duplicate_observation_candidate`；
相同时刻不同价格标记 `TIMESTAMP_CONFLICT`，该截点不给 candidate、不回退掩盖冲突。
同价格但其他元数据相异也单独标记冲突待复核。

## 返还率及许可

用 Decimal 复算 `1/(1/HOME+1/DRAW+1/AWAY)`，乘 100 后四舍五入到两位小数，
与 `returnRatio` 比较；明细 UI 表头为“返奖率”，公司概览为“返还率”。
本次全部行匹配，最大差值低于 0.005 个百分点（显示舍入范围）。
该公式对三项排列对称，因此只能校验数值/抓取完整性，**不能单独证明 HOME 与 AWAY 没有调换**；
列顺序必须由上述 API→JS→UI 证据确定。

[关于我们](https://www.vipc.cn/about) 免责声明提到观赏、学习和研究用途，但不承诺准确性、完整性、时效性；
同页页脚明确限制未经许可复制、转载或以其他方式使用内容。
[robots.txt](https://www.vipc.cn/robots.txt) 明确 `Disallow: /i/*`（此次 API 所在路径）。
读取 robots 后已停止全部网络取数，后续只离线核验现有样本。
首页、关于页及已读取的公共脚本没有找到可明确授权自动抓取/复制/缓存/再分发的条款；
这不是声称不存在其他协议。一般研究用途说明不能覆盖这些限制。
**LICENSE_STATUS=RESTRICTED**，自动抓取、缓存/复制、再分发权限未获确认。

Gate A 仍 BLOCKED（无体彩官方 Raw 验证）；Gate B 仍 BLOCKED（时间可用性语义、时区、许可未完成准入）。
VIPC 可作为有条件的第二候选源：身份和 1X2 历史结构可取，但高频更新尤其集中在开球后，
不能只凭条数多或 HTTP 200 升级 ACCEPTED。当前不扩大数据规模。

## 离线复核

```powershell
.venv/Scripts/python.exe -m jc.research.vipc_evidence --input artifacts/research-probes/20261001-vipc-discovery --report docs/VIPC_SOURCE_REPORT.md
```

命令不联网，先复用 manifest 的原件哈希/secret/provenance 校验，再读取三份固定 URL 的业务 Raw，
生成本地逐行检查及下方统计。它不是正式 Provider，不改 D2A、research-replay-v1 或 LIVE。

验收收尾（2026-10-01）：仅修正时区依据措辞并离线核验，未发送新的 VIPC 网络请求。

| 完整回归 | 结果 |
|---|---|
| `pytest -q`（SQLite） | **857 passed、1 skipped**，138.28 秒 |
| `ruff check apps/api/src tests` | 通过 |
| `mypy apps/api/src` | 通过，50 个 source files |
| `pytest -q`（PostgreSQL） | **857 passed、1 skipped**，135.89 秒；PostgreSQL 17.11，127.0.0.1:55433，新建空库 `jc_vipc_acceptance_test` |

两套全量均显式设置 `RESEARCH_NETWORK_ENABLED=0`；唯一跳过项为 opt-in 真实网络测试，
各保留 1 条既有 Starlette/httpx 弃用警告。PG 测试结束后仅余空的 `alembic_version` 表。
日志保存在 ignored `artifacts/vipc-acceptance-sqlite-tests.txt`、`artifacts/vipc-acceptance-postgres-tests.txt`。
回归前后离线复核：下表全部统计、三个 candidate 及状态字段一致，23 个已保存文件的 SHA-256 均未变化。
`git diff --check` 通过；冻结模块无 diff。未新增功能、采集或准入结论。
测试使用明确的 synthetic 输入，默认不联网；真实统计仅来自本地已保存 Raw。
覆盖身份变化、offerId 缺失、display_name 不参与身份、Decimal/非法赔率、原始时间与 UI 显示、
开球前/等于/以后、含等号的三个 cutoff、不同时间同价格保留、重复与冲突时刻、返还率和 A/B 不自动通过。
另验证离线读取绑定三个固定 URL、原件篡改被拒绝。

<!-- BEGIN VIPC CANDIDATES -->

以下由已保存 Raw 离线计算；依据 detail 的 +08 对齐关系及页面直显 updateTime，暂以 Asia/Shanghai 作为仅用于 candidate cutoff 的解析假设；正式时区及 availability 语义未确认。

| 检查项 | 结果 |
|---|---|
| bookmaker_identity | vipc:432 |
| total_rows | 53 |
| prematch_rows | 15 |
| post_kickoff_rows | 38 |
| invalid_time_rows | 0 |
| earliest_time | 2026-09-29T07:21:00+00:00 |
| latest_prematch_time | 2026-09-30T05:53:00+00:00 |
| latest_overall_time | 2026-09-30T07:51:00+00:00 |
| return_rate_pass_rows | 53 |
| duplicate_timestamp_groups | 0 |
| timestamp_conflict_groups | 0 |
| license_status | RESTRICTED |
| source_decision | UNVERIFIED |
| gate_a | BLOCKED |
| gate_b | BLOCKED |

| candidate | 截点（北京时间） | 原始 updateTime | parsed_utc（候选） | HOME / DRAW / AWAY |
|---|---|---|---|---|
| candidate_T30 | 13:30 | 2026-09-30 13:27:00 | 2026-09-30T05:27:00+00:00 | 1.21 / 4.95 / 9.00 |
| candidate_T90 | 12:30 | 2026-09-30 12:28:00 | 2026-09-30T04:28:00+00:00 | 1.14 / 5.60 / 12.50 |
| candidate_T360 | 08:00 | 2026-09-30 04:46:00 | 2026-09-29T20:46:00+00:00 | 1.12 / 5.80 / 14.50 |

<!-- END VIPC CANDIDATES -->
