# SPORTTERY_SCHEDULE_TIME_V1

核验时间：2026-10-02T02:22:21Z。结论：**竞彩足球赛程开赛墙钟时间的 source-level timezone evidence 通过**。
这是根据一致的官方同页证据及官方前端字段映射作出的有限推断；不声称 API 每条记录自带 offset，
也不声称官网明文承诺所有时间字段使用同一时区。

## 官方同页证据

| 官方页面 | 赛程展示 | 同页北京时间说明 | 保存原文行号 |
|---|---|---|---|
| [2015 年竞彩对阵文章](https://www.sporttery.cn/football/jcqz/2015/0605/161970.html) | 2015-06-05 12:00 | 时间：北京时间6月5日12点 | 282 / 289 |
| [2020 年竞彩足球赛程文章](https://www.sporttery.cn/football/jcdj/2020/0804/608677.html) | 两场均为 2020-08-06 01:00 | 北京时间8月6日凌晨1点 | 70、77 / 65 |

两篇来自不同年份的官方页面，赛程时间均与正文明确标为北京时间的开赛时刻相同。
历史页面中的比赛只用于时间约定佐证，未增加 Dataset 比赛。
网页检索仅用于发现 URL；准入证据是本机普通 HTTPS 请求实际取得并先保存的 HTML，
均 HTTP 200、retention=UNCHANGED，无重试、跳转或验证绕过。

## 原件、抓取时间与 hash

以下均为原响应字节 SHA-256。完整本地路径、canonical Raw hash、HTTP 状态与定位信息见
[版本化机器清单](sporttery-schedule-time-v1.json)。时间均为 UTC。

| 证据 | 抓取时间 | SHA-256 |
|---|---|---|
| 2015 官方文章 | 2026-10-02T02:17:34.494099+00:00 | `ce4a05569287506eff63543b12c22bf2bb64093b29976860f7f861e03a76d366` |
| 2020 官方文章 | 2026-10-02T02:17:35.134522+00:00 | `b1f5bc5a890813bdcdf28a933b27c28ae8820881032ea6de75b607ef0ee04ea8` |
| 官方 zqdz.js | 2026-10-02T00:02:46.845155+00:00 | `4bf8a73a1fabff504371e93cf0ae107222d41a404416041ebf51e58065f0905b` |
| 官方 2041790 对阵页模板 | 2026-10-02T00:05:47.705227+00:00 | `928c56a2154458b7d074d853e05062eadaa06deb7cf61d53dd888e9f780d7fdf` |

[官方 zqdz.js](https://static.sporttery.cn/res_1_0/jcw/default/jc/zqdz.js) 第 77、79、85–87 行：
getMatchHeadV1 请求携带 sportteryMatchId，成功响应的 value 直接赋给 pageTitle。
[官方对阵页](https://www.sporttery.cn/jc/zqdz/index.html?showType=3&mid=2041790) 第 116、121、130、137 行：
相同比赛卡片展示竞彩编号、主客队及 pageTitle.matchDateTime.substring(0,16)，没有时区转换。
因此该 API 字段是官方赛程开赛墙钟的展示输入。

## 适用范围

唯一允许字段：`getMatchHeadV1.value.matchDateTime`。
接受当前已复核的 `YYYY-MM-DD HH:MM` naive 格式，按 `Asia/Shanghai` 解释并输出带时区时间及 UTC。
规则名及 evidence_version 均为 `SPORTTERY_SCHEDULE_TIME_V1`。
未登记任何额外 schedule kickoff 同义字段；新字段必须另有明确映射核验，不能凭名称套用。
已有 offset、日期不完整、秒级及其他未复核格式不会被该函数重解释。

**不适用**：updateDate、updateTime、lastUpdateTime、finished_at，以及所有其他 timestamp。
publication_timezone 继续 UNVERIFIED；published_at、replay_available_at、availability_basis 全部 NULL。
HTTP 抓取时钟、文章发布时间及用户采集时间均不用于推导业务发布时间。
ResearchMatch 仍必须接受 timezone-aware datetime；原 D2A、research-replay-v1、analysis_visibility 均不改。

## 当前唯一目标与 verifier 声明

2041790 原文：`2026-09-30 18:30` → `2026-09-30T18:30:00+08:00` → `2026-09-30T10:30:00Z`。
完整 raw_time、source_timezone_rule、normalized_time、UTC、evidence_version 见
[明确 source attestation](sporttery-2041790-gate-a-attestation.json)。

该声明由 Codex 在用户授权范围内逐项审阅后作出，明确记录 verifier；不冒称人类签名。
三份业务 Raw 的来源仍是用户导出的官方响应，不冒称本轮独立联网取得 API 正文。
VERIFIED 依据是已保留原件的 hash、URL/body、一致的比赛/球队/比分、官方池身份，
以及本版本 kickoff 时区证据，而非官方域名或 HTTP 成功本身。
原 intake 的 UNVERIFIED 决策作为历史记录保留；本次另建带 verifier、核验时间、原始 hashes/URLs
及 timezone evidence version 的声明，不改写原 intake。旧清单的 secret_scan 审计字段在新声明中
记作 input_scan，以通过既有 D2A 敏感字段名校验；未修改该校验。

D2A 将 ResearchMatch.kickoff_at 规范化为 UTC，因此 SPORTTERY_POOL 的四项
sporttery_pool_evidence 使用字符串 ID `2041790` / `2053` / `2060` 和
`2026-09-30T10:30:00+00:00`，逐项与 ResearchMatch 完全相等。
`+08:00` 原规范化表达单独保存在 kickoff_normalization，不能以字符串等价猜测替代 contract 校验。

HAD 18 条只保留为证据；results=()、odds=()。
缺 finished_at 使 Gate C 保持 BLOCKED；缺合格 external historical odds 使 Gate B 保持 BLOCKED。
T-360、T-90、T-30、T-15、T-5、LAST_PREMATCH 均保持 BLOCKED。
