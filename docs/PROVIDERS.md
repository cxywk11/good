# Providers

## 体彩

官方赛程页：https://www.sporttery.cn/jc/zqszsc/index.html
官网 JavaScript `jc_szsc_gz.js` 使用 `/gateway/uniform/football/getMatchListV1.qry?clientCode=3001`。
官方计算器 `dataTransfer.js` 使用 `/gateway/uniform/football/getMatchCalculatorV1.qry?channel=c`。
URL 与路径均通过环境变量配置，代码不固定域名。适配器只从体彩赛程建立主池。
本机首次探测数据接口返回 HTTP 567，官网 HTML/JS 可访问；未宣称取得线上比赛。
`tests/fixtures/sporttery.json` 是按照官网 JS 字段构建的合成样例，顶层 mock=true，不是实际比赛。

Raw 在独立事务落库后才解析。非 JSON 响应原文保存在 `_unparsed_body`，超时保存 transport_error。
有限指数退避；HTTP 429 尊重 Retry-After，结束本轮请求并在 Redis 设冷却，不在本轮反复请求。
空响应记 EMPTY/DEGRADED，结构变更或非法赔率整批回滚业务数据，Raw 保留。

## 海外

已实现 The Odds API v4 实时和历史 Adapter，依据官方文档：https://the-odds-api.com/liveapi/guides/v4/
配置 base URL、API Key、soccer sport keys、bookmakers 后可启用。实际公司与市场覆盖取决于订阅和返回结果。
当前没有提供密钥，没有进行真实账号调用；契约测试使用带 mock=true 的外层测试样例，不能视为线上验证。
文档返回事件 ID 但未提供稳定球队 ID，因此该源默认 UNMATCHED，由管理员逐场核实确认。
支持 1X2、亚洲让球、大小球；真实比分盘覆盖未验证，不编造数据。历史端点需要相应付费权限。

四家 Mock Provider（Pinnacle / Bet365 / Macau / WilliamHill）使用统一 SDK 的合成 fixture 格式，
不是这四家真实专有 API 格式。实体链接来自显式 `entity_links.json`，绝不通过中文/英文名称直接拼接。
演示和真实模式必须使用独立数据库。日志和 source_url 会隐藏 API Key。

## 配置与验证边界

真实模式启用 SPORTTERY_ENABLED=true，配置官方 base URL 与两个 path。字段映射依据官网赛程和计算器脚本，其中玩法 cbtValue=1 才表示开售，单关优先读 cbtSingle。尚未拿到真实 JSON，字段行为需用真实样例二次验收。

海外启用 ODDS_PROVIDER_ENABLED=true，配置 ODDS_PROVIDER_BASE_URL、ODDS_PROVIDER_API_KEY、ODDS_PROVIDER_SPORTS（soccer keys）与 ODDS_PROVIDER_BOOKMAKERS。真实 Adapter 通过事件 ID 识别比赛，缺少稳定球队 ID 时留空。后台确认事件映射后可重放其 Raw；其他外部比赛仍不进入体彩主池。

fetch_odds_history 能力已在 SDK 和 The Odds API 实现，可通过 Adapter 调用并走相同 Raw/解析管道；尚未提供任意日期历史回补后台任务，不把当前采集当完整历史。海外真实比分盘和供应商初/收盘元数据只在确有授权数据时接入。

参考：[体彩官方赛程](https://www.sporttery.cn/jc/zqszsc/index.html)、[官方赛程脚本](https://static.sporttery.cn/res_1_0/jcw/default/jc/szsc/jc_szsc_gz.js)、[官方计算器脚本](https://static.sporttery.cn/res_1_0/jcw/default/jc/jsq/dataTransfer.js)、[The Odds API v4 文档](https://the-odds-api.com/liveapi/guides/v4/)。验证日期：2026-09-30。
