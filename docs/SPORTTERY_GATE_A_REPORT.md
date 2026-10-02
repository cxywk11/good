# 2041790 Gate A 核验结果

| # | 项目 | 结果 |
|---|---|---|
| 1 | timezone evidence | 通过；两篇官方同页赛程/北京时间对应证据及官方 JS→页面字段映射，详见 [V1 证据文档](SPORTTERY_SCHEDULE_TIME_V1.md) |
| 2 | evidence version | `SPORTTERY_SCHEDULE_TIME_V1`；仅 `getMatchHeadV1.value.matchDateTime` |
| 3 | kickoff raw | `2026-09-30 18:30` |
| 4 | normalized kickoff | `2026-09-30T18:30:00+08:00`；UTC `2026-09-30T10:30:00Z` |
| 5 | source verification | `OFFICIAL_SPORTTERY_HISTORY / sporttery / VERIFIED`；[明确核验声明](sporttery-2041790-gate-a-attestation.json)，含 verified_at、verification_note、3 份 Raw hashes/URLs、时区证据版本；Codex 核验，不冒称人类签名 |
| 6 | SPORTTERY_POOL artifact | `b43ff1e0-ea55-4b6b-9a2d-3a9e132d8895`；原 Match Head payload 的 canonical hash `f0e91dcb65434a1fe328cd59705448df0d4518937ee748f3813b5f370301d87a`；metadata 四项与 ResearchMatch 完全一致 |
| 7 | VERIFIED Target | `2041790`，唯一 Target；主客队 Sporttery ID `2053` / `2060`；无额外比赛 |
| 8 | Gate A | **PASS**；实际调用 ResearchMatch → SportteryVerificationInput(VERIFIED) → validate_import → import_research_dataset → seal_dataset，封存后通过 load_research_dataset 和 verified_sporttery_targets 回读。全量 pytest：SQLite、PostgreSQL 17.11 各 896 passed / 1 skipped（联网 opt-in）；ruff、mypy（51 源文件）通过。保留既有 Starlette 弃用警告 |
| 9 | Gate C | **BLOCKED**；缺真实 finished_at，results=()；原 1:1 只保留为证据 |
| 10 | Gate B | **BLOCKED**；无合格 external historical odds，odds=()；官方 HAD 18 条、18 条完整，全部 evidence-only，导入 0 条 |
| 11 | Dataset 是否创建 | 是，`jc-football-official-pilot`；实际存于 PostgreSQL `jc_demo_pg` 的独立 research 表，非测试库中的模拟成功 |
| 12 | Dataset 是否 SEALED | 是，`2026-10-02T10:26:13.706310+08:00`；1 Match、1 VERIFIED Target、0 Result、0 Odds、7 Raw；UUID `df92834a-fb62-4836-a86e-806d77c1ea78` |
| 13 | dataset version/hash | `2041790-gate-a-v1` / `2e7efbcc160e182b975c5918bcdea9ffefd9364d4aaf83529f4a1864a23f1e89` |
| 14 | publication timezone 状态 | `UNVERIFIED`；published_at / replay_available_at / availability_basis 全部 NULL。T-360、T-90、T-30、T-15、T-5、LAST_PREMATCH 均 BLOCKED；无 Replay Run |
| 15 | 是否修改 frozen contract | 否；research-replay-v1、ResearchMatch timezone-aware requirement、D2A contracts 和 analysis_visibility 均保持原样；原文件 hash 已复验 |

[机器结果](sporttery-gate-a-result.json) ·
[时区 URL/hash/抓取时间清单](sporttery-schedule-time-v1.json) ·
[保存的完整 ResearchImport](../artifacts/research-probes/20261002-sporttery-gate-a/research-import.json) ·
[SPORTTERY_POOL envelope](../artifacts/research-probes/20261002-sporttery-gate-a/sporttery-pool.json) ·
[SQLite 测试日志](../artifacts/research-probes/20261002-sporttery-gate-a/pytest-sqlite.txt) ·
[PostgreSQL 测试日志](../artifacts/research-probes/20261002-sporttery-gate-a/pytest-postgresql.txt)

核验源声明限于本次材料。三份 API 原件的 provenance 来自用户导出；原 intake 的 UNVERIFIED
记录继续原样保留，新声明并非仅凭官方域名自动升级。时区推断及适用边界见 V1 文档。

复验和幂等导入（使用现有 `.env` 的数据库；不会覆盖旧版本）：

```powershell
$env:RESEARCH_NETWORK_ENABLED='0'
$env:PYTHONIOENCODING='utf-8'
.venv/Scripts/python.exe artifacts/research-probes/20261002-sporttery-gate-a/import_pilot.py
```

脚本先复验保存原件、来源 URL、采集时间、hash、同页时间证据、三 Raw 身份及明确声明，
再使用未修改的 D2A importer。它保留原始文章/JSON/JS；测试中的模拟 attestation 不计入真实证据。
