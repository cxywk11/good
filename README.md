# 竞彩智研 / JC Football Intelligence

Phase 0–3 数据底座保持：体彩主比赛池、UUID 实体映射、只追加赔率、审核后台和历史曲线。已增加 Phase 4 的 P4-0～P4-3：赛后事实 Contract、不可变 Feature Snapshot、严格 cutoff 基础设施和仅消费冻结 Feature 的 Market Probability Baseline；P4-4A 增加显式 Decimal 参数的纯比分概率数学层。真实 lambda/rho 估计尚未实现，不能产生真实比赛预测，没有投注推荐。

**交付状态：可运行的 Mock 演示已打通真实 PostgreSQL；真实当日体彩与海外账号数据、完整 Docker/Redis 运行验收尚未完成。** 详见 [验收报告](docs/PHASE1_ACCEPTANCE.md)。

## 本次本机预览

- 网站：http://127.0.0.1:5173
- API 文档：http://127.0.0.1:8000/docs
- 演示数据库：本机 PostgreSQL 17，端口 55432，数据库 `jc_demo_pg`。
- 管理员邮箱和随机密码在本机 `.env` 的 `ADMIN_EMAIL` / `ADMIN_PASSWORD`，未写入代码。
- 顶部和比赛详情明确标识 MOCK，所有演示比赛与赔率均为合成数据。
- 本机未安装 Redis，`/ready` 会返回 503；`/health` 只验证进程。演示采集调度关闭。

## Docker Compose

1. 将 `.env.example` 复制为 `.env`，设置随机 `POSTGRES_PASSWORD`、不少于 32 字符的随机 `JWT_SECRET`、可选管理员邮箱/密码。不要覆盖已有配置。
2. 默认 `DEMO_MODE=false`；需要演示时设为 `true`，并使用单独数据库和 Compose 项目。
3. `docker compose up --build -d`，访问 http://localhost:8080。
4. `docker compose ps` 检查四个服务；`docker compose exec backend python -c "import urllib.request; print(urllib.request.urlopen('http://localhost:8000/ready').read().decode())"` 检查 PostgreSQL 与 Redis。

Compose 内置服务 DNS 会覆盖 DATABASE_URL/REDIS_URL，开启调度。启动顺序是 PG/Redis 健康 → Alembic 迁移 → bootstrap → API → Nginx。密码使用 URL 安全随机字符串，或者正确进行 URI 编码。生产模式拒绝 Mock 数据。本机没有 Docker，以上命令尚未实际执行。

## 本地开发

需要 Python 3.12+、Node 22+。PowerShell 示例：

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e '.[dev]'
# 配置 .env 后执行
.venv/Scripts/alembic.exe upgrade head
.venv/Scripts/python.exe -m jc.bootstrap
.venv/Scripts/python.exe -m uvicorn jc.main:app --host 127.0.0.1 --port 8000 --reload
# 另一个终端
cd apps/web
npm ci
npm run dev
```

Windows 快速演示：安装依赖后运行 `infra/start-local.ps1`。仅当 `.env` 不存在时，脚本才创建 SQLite Mock 开发配置；已有 PostgreSQL 配置会被保留。脚本后台启动进程，PID 和日志在 `.runtime`。重复启动前先停止已有对应进程，避免端口冲突。

本次本地便携 PostgreSQL 数据目录是 `.runtime/pgdata`；停止后可用 `.runtime/pgsql/bin/pg_ctl.exe -D .runtime/pgdata -l .runtime/postgres.log start` 重启。它是开发辅助环境，不代替 Compose 部署验收。

## 验证

```powershell
.venv/Scripts/pytest.exe -q
.venv/Scripts/ruff.exe check apps/api/src tests
.venv/Scripts/mypy.exe apps/api/src
.venv/Scripts/alembic.exe check
cd apps/web
npm run test
npm run build
```

PostgreSQL 集成测试：设置 `TEST_DATABASE_URL` 指向**空的独立测试数据库，名称必须以 `_test` 结尾**，再运行 `infra/test-postgres.ps1`。测试会迁移建表和降级清空，不可使用业务数据库。SQLite 快测与 PG 集成测试都执行相同核心用例。

## 文档

本机预检：`.venv/Scripts/python.exe infra/check_local.py`；备份恢复演练：`.venv/Scripts/python.exe infra/backup_restore_drill.py --pg-bin .runtime/pgsql/bin`。报告保存在 artifacts；预检遇到未满足条件会返回非零退出码。认证限流设置与复验范围见运维文档。

- [架构](docs/ARCHITECTURE.md)、[ER 与数据模型](docs/DATA_MODEL.md)
- [实际数据源与接入配置](docs/PROVIDERS.md)、[实体映射](docs/ENTITY_RESOLUTION.md)
- [赔率与时间语义](docs/ODDS_STORAGE.md)、[开发硬性规则](docs/CONSTITUTION.md)
- [验收报告](docs/PHASE1_ACCEPTANCE.md)、[运维](docs/OPERATIONS.md)、[待办与技术债](docs/BACKLOG.md)
- [Phase 4 范围、Feature / Market API、时间可见性及计算规则](docs/PHASE4_SPEC.md)

没有配置 Git 远端或发布外部网站；项目文件保存在当前工作区。
