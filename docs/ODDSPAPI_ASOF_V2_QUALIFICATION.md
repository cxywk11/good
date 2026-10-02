# OddsPapi 2041790 · 独立 as-of V2 核验

## 先行语义审查（实现前）

结论：**VERIFIED，范围是供应商文档明确支持的 last-known outcome state 重建**。
这不把每条 createdAt 声称为一次真实价格变化，也不声称历史采录没有延迟。

- [官方 historical-odds 参考](https://oddspapi.io/en/docs/get-historical-odds)定义逐 outcome 的历史列表、createdAt、price、active；单独这份字段说明不足以证明持续性。
- [官方历史利润率教程](https://oddspapi.io/blog/bookmaker-margin-analytics-vig-trends/) Step 2 明确说明不同 outcome 独立更新，应将每条腿的最后已知价格延续至共同时间轴，计算任意时刻的市场；示例使用 createdAt <= t。这是允许异步 as-of 重建的直接供应商依据，不是根据时间排序或常见系统行为推断。
- [官方动态赔率教程](https://oddspapi.io/blog/dynamic-odds-price-movement-python/)定义 createdAt 为记录快照时间，并说明 active=false 表示暂停，价格在重新开放前不可用。
- 利润率教程示例先跳过 inactive，可能保留更老 active。**不采用这段过滤顺序**：用户要求更严格的 latest-state-first；先选最新状态，再验证 active/price，暂停一直阻塞直到后续 active 状态。
- [官方 JavaScript 教程](https://oddspapi.io/blog/javascript-odds-api-nodejs/)说明历史 feed 按采录节奏写入，价格可能重复。因此“每条记录必是价格变更”不成立；可采用的等价语义是文档明确支持的最后已知状态延续。
- [官方导出教程](https://oddspapi.io/blog/historical-odds-csv-excel-backtesting/)作为历史研究使用背景；不作为状态持续的独立证明。

所有文档本轮 HTTP 200，响应先保存到 ignored artifacts 再检查。下表为原 HTTP response bytes 的 SHA256；教程包含示例凭证变量，持久化文本经现有 secret guard 脱敏，`retention=REDACTED`，没有把脱敏文本 hash 冒充原响应 hash。

| 文档 | response SHA256 |
|---|---|
| Historical reference | `000c33dcc321927fdfe6f2a803dec78ac1876194bae63a27726a684dbf16fee4` |
| Margin timeline（决定性证据） | `81227bdc92a61dc6d22f39b0d03dba9c787b0a3402a3be54280b64e127aa8026` |
| Movement / suspension | `c5cc78924fec824f4e92fd54a076df1ebf472a5b98595ca5dea9b54ffa3e7fb5` |
| CSV / backtesting | `cd8c813e24ce448148ade4d705c8fae330f9563016c0438df04696b937d9d9b1` |
| Cadence / repeated observations | `07818ff39c0ac9147a6095bdf36a29d07debc21281aef82be8beff2a8f9c2457` |

已在实现前重读原六份 unchanged Historical Raw，逐份核验原响应 hash 和 canonical payload hash，共 12,782 条记录；真实字段是 createdAt / price / active / limit / exchangeMeta。未发起新的赔率请求。
三家公司分别保留身份；Betfair 三项均提供直接数值 price，exchangeMeta 均为 null。本轮只检查其原生 1X2 state，不能据此解释 back/lay、佣金或成交量。

## V2 规则

独立 policy：`oddspapi-asof-outcome-state-v2`。V1 adapter、policy、报告、Raw、三个 SEALED Dataset 及冻结 replay-v1 / D2A / visibility 保持原样。
V2 source 的 review note 保留了 V1 身份、时间、许可审查的历史文字，并追加独立 V2 审查；其中旧 same-instant 限制属于 V1，V2 的执行规则由新的 policy、semantics review 和 admission manifest 明确规定。

对每一 bookmaker / fixture / market / selection 取 max(createdAt <= cutoff)，保留 inactive 后再判断；三项必须 active=true、price>1、createdAt<kickoff。
同 selection 同瞬间的冲突状态阻塞，完全重复的行可去重但保留所有 Raw 引用；不以排序位置解决冲突。
market_state_asof 仅在 admission manifest 中表示 cutoff；derived quote 的 replay_available_at 仍为该 selection 原始 createdAt。
每次 reload 必须从完整 Raw 重新审查，校验 audit hash、normalized quote、source declaration 和 provenance 后再进入既有 feature / market 计算。


## 真实重建结果

V1 coverage **2/5**；V2 coverage **5/5**。Gate A PASS / Gate B PASS / Gate C BLOCKED。
三家公司独立处理，每家公司均通过五个 cutoff；每个 cutoff 的 external_consensus.source_count 为 3。
15 个 bookmaker-cutoff market state，共 45 个选中 outcome 引用，去重后正式导入 **37 条 external quotes**。
完整历史包含 45 条 inactive 记录；五个 cutoff 选中的 latest state 均为 active，inactive 阻塞数为 0。
同 selection 同时刻 conflicting state 组数 0，identical duplicate 行数 0。没有过滤掉 inactive 后寻找旧 active。

下表时间均为 2026-09-30 UTC；每格依次是 price / 原始 createdAt 的 UTC 时间 / active。完整原始时间字符串、source_raw_hash、source_raw_path、raw_references 保存在 Dataset admission manifest 和当前状态的 oddspapi_asof_v2.audit。

| Cutoff | Bookmaker | HOME | DRAW | AWAY | market_state_status |
|---|---|---|---|---|---|
| T-360 | bet365 | 4.5 / 04:17:18.564Z / true | 3.3 / 02:10:12.524Z / true | 1.69 / 04:17:18.564Z / true | PASS |
| T-360 | betfair-ex | 6.6 / 04:25:24.986Z / true | 3.8 / 04:27:47.575Z / true | 1.63 / 04:26:24.441Z / true | PASS |
| T-360 | pinnacle | 5.33 / 04:26:24.271Z / true | 3.85 / 04:26:24.271Z / true | 1.584 / 04:26:24.271Z / true | PASS |
| T-90 | bet365 | 7.0 / 08:02:35.989Z / true | 3.6 / 07:04:11.503Z / true | 1.47 / 08:02:35.989Z / true | PASS |
| T-90 | betfair-ex | 8.0 / 08:59:08.476Z / true | 4.3 / 08:59:25.504Z / true | 1.51 / 08:59:37.475Z / true | PASS |
| T-90 | pinnacle | 6.6 / 08:56:03.015Z / true | 3.91 / 08:56:29.858Z / true | 1.49 / 08:56:29.858Z / true | PASS |
| T-30 | bet365 | 6.5 / 09:17:57.868Z / true | 3.6 / 07:04:11.503Z / true | 1.47 / 08:02:35.989Z / true | PASS |
| T-30 | betfair-ex | 7.0 / 09:59:40.964Z / true | 4.1 / 09:59:06.077Z / true | 1.58 / 09:59:25.522Z / true | PASS |
| T-30 | pinnacle | 6.16 / 09:59:51.878Z / true | 3.73 / 09:59:51.878Z / true | 1.543 / 09:59:51.878Z / true | PASS |
| T-15 | bet365 | 6.5 / 09:17:57.868Z / true | 3.6 / 07:04:11.503Z / true | 1.47 / 08:02:35.989Z / true | PASS |
| T-15 | betfair-ex | 7.6 / 10:14:18.299Z / true | 4.1 / 10:14:01.154Z / true | 1.56 / 10:14:41.999Z / true | PASS |
| T-15 | pinnacle | 6.43 / 10:12:18.411Z / true | 3.76 / 10:12:18.411Z / true | 1.523 / 10:08:39.332Z / true | PASS |
| T-5 | bet365 | 6.5 / 09:17:57.868Z / true | 3.6 / 07:04:11.503Z / true | 1.47 / 08:02:35.989Z / true | PASS |
| T-5 | betfair-ex | 7.8 / 10:24:50.354Z / true | 4.1 / 10:24:52.744Z / true | 1.55 / 10:24:50.125Z / true | PASS |
| T-5 | pinnacle | 6.66 / 10:24:40.950Z / true | 3.82 / 10:22:03.602Z / true | 1.502 / 10:24:40.950Z / true | PASS |

## V1 与 V2 并列计算

概率显示为百分比，gap 显示为百分点；三项顺序为 HOME / DRAW / AWAY。机器结果保留原 Decimal 字符串。

| Cutoff | source_count V1 → V2 | V1 p_market | V2 p_market | V1 gap | V2 gap |
|---|---:|---|---|---|---|
| T-360 | 1 → 3 | 17.3934 / 24.0797 / 58.5270 | 17.3416 / 25.6014 / 57.0570 | +1.7269 / -0.0391 / -1.6878 | +1.6751 / +1.4827 / -3.1578 |
| T-90 | 0 → 3 | NULL | 13.0945 / 23.9172 / 62.9883 | NULL | -1.6607 / -0.2716 / +1.9324 |
| T-30 | 1 → 3 | 15.0519 / 24.8578 / 60.0904 | 14.2995 / 24.5866 / 61.1139 | +0.9907 / -0.8191 / -0.1716 | +0.2383 / -1.0902 / +0.8519 |
| T-15 | 0 → 3 | NULL | 13.7355 / 24.5487 / 61.7158 | NULL | -0.3257 / -1.1281 / +1.4538 |
| T-5 | 0 → 3 | NULL | 13.4572 / 24.4163 / 62.1265 | NULL | -0.6039 / -1.2605 / +1.8645 |

T-360 和 T-30 的 Pinnacle 三项原价格、原始时间逐项对照 V1，完全一致。
这两处 V2 consensus 的变化来自准入范围：Bet365 与 Betfair 现在可各自形成完整 as-of state，原先仅 Pinnacle 的单来源概率变为三个独立来源 no-vig 概率的等权平均。未改写 V1 已合法的 Pinnacle 结果。
gap 始终是 external_consensus − Sporttery HAD no-vig；这里只计算 market disagreement。

| Cutoff | Sporttery HAD no-vig（HOME / DRAW / AWAY，%） |
|---|---|
| T-360 | 15.6665 / 24.1187 / 60.2148 |
| T-90 | 14.7552 / 24.1888 / 61.0560 |
| T-30 | 14.0611 / 25.6769 / 60.2620 |
| T-15 | 14.0611 / 25.6769 / 60.2620 |
| T-5 | 14.0611 / 25.6769 / 60.2620 |

## 独立 Dataset 与冻结检查

- key：`jc-football-official-pilot`
- version：`2041790-external-1x2-asof-v2`；status：`SEALED`
- hash：`b89885738617d7a8f2b3fb51224cde0be33269a4a5714fa6fd4a7a70f38549dc`
- 内容：1 VERIFIED Sporttery target；54 HAD quotes；37 external quotes；0 Result；16 Raw artifacts。
- D2A load 后重新从完整历史 Raw 重建，audit、quotes、provenance、市场结果一致；重复导入幂等。
- 三个旧 Dataset 的 header 和每类成员 hash 均与本轮开始快照比较；V1 adapter、报告和原 artifacts 全目录文件哈希同时冻结。
- 未发起新的历史赔率请求。全部原历史 Raw 从 V1 封存内容复用，新增文档响应和验收输出在 ignored artifacts。

正式重放入口：`jc.research.oddspapi_asof.assess_oddspapi_asof_intake`。
它每次重建最新 outcome state 并按 cutoff 筛出合法的同公司三项，再调用未修改的 build_research_feature → build_market_data。
不能直接对整个 Dataset 调用裸 per-series replay 来证明 V2 准入，因为其他 cutoff 保留的旧 active quote 可能掩盖后来的暂停；同样不能使用 V1 whole-snapshot admission 来判定异步 V2。

当前 market_model_data_status = AVAILABLE_ALL_FIXED_CUTOFFS；market_evaluation_status = NOT_EVALUABLE。
下一唯一阻塞：Gate C 的正式 REGULATION Result / finished_at 尚未准入。本轮不处理该项。

## 检查覆盖

新增合成检查覆盖：状态持续、异步时钟、暂停与恢复、price<=1、未来与开球边界、cutoff equality、fixture/market/outcome/bookmaker 身份、clone、冲突与完全重复、naive time、Raw/quote/provenance/manifest/source 篡改、重载一致、版本不可覆盖、V1仍2/5、V2独立计算、不跨 bookmaker。
真实验收另行核对三个旧 Dataset 逐成员 hash；单测不嵌入真实 Raw。

## 完整回归结果

- SQLite `pytest -q`：1102 passed、1 skipped、1 warning，236.71 秒。
- 独立 PostgreSQL 17.11 `pytest -q`：1102 passed、1 skipped、1 warning，215.07 秒；测试库仅剩空 alembic_version，清理完成。
- `ruff check apps/api/src tests`：PASS；`mypy apps/api/src`：PASS，56 个源文件。
- 新增 26 项合成用例及 2 项状态检查；跳过项为 opt-in 网络测试，warning 为既有 Starlette/httpx 弃用提示。
- 本轮开始与结束快照一致：三个旧 Dataset 的 header 与所有成员 hash、V1 adapter、冻结代码、历史报告和原 Raw artifacts 文件 hash 均未变。
- 待提交文件 secret scan PASS；没有真实 Raw 或凭证加入 Git。
