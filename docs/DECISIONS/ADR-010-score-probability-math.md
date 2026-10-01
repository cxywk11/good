# ADR-010: 显式进球参数的纯比分概率数学层

状态：接受。范围：P4-4A；2026-10-01。

## 边界与版本

`analysis/score_matrix.py` 只将显式 `lambda_home`、`lambda_away`、`rho` 转换为概率分布。三项均必填，接受有限 Decimal；lambda 非负，拒绝 float、字符串、bool、NaN 和 Infinity，不隐式转换。lambda 与 rho 的真实估计来源尚未实现，不能将测试参数视为真实比赛预测。引擎没有 DB、Feature/Odds/Market Snapshot、网络、时钟、随机数或 LLM 依赖。

`SCORE_ENGINE_VERSION="score-math-v1"`。Poisson、DC、截断、归一化、精度、尾部容差或盘口映射变化必须升级版本并保留旧发布工件。实现仅用 Python 标准库；不新增依赖、Prediction Snapshot 表、Migration、HTTP 预测接口或推荐。原 FeatureSnapshot 输入边界、analysis_cutoff、analysis_visibility 和 Market 不回查当前 Odds 的约束继续保留；未来参数估计器仍须通过冻结 Feature 边界。

## Decimal 与 Poisson

局部独立 Context：50 位有效数字、ROUND_HALF_EVEN、Emin=-999999、Emax=999999、capitals=1、clamp=0，显式固定 traps。外部 Context 的精度、舍入、指数范围、flags、traps 不影响结果，也不被修改。内部概率全为 Decimal，输出直接 `str(Decimal)` 保留全部计算精度，不量化到固定小数位；JSON 中没有核心 float。

递推 `p0=exp(-lambda)`，`p(k+1)=p(k)*lambda/(k+1)`；exp 使用 Decimal 能力，没有 factorial 重算或 float 转换。

`TAIL_TOLERANCE=1e-12` 为每侧边缘分布的尾部上界；`MAX_GOALS_CAP=30` 为最大保留进球数（含 30），不是默认截断点。至少保留 0 和 1 球，包括零 lambda 的 `[1, 0]`，确保整个 DC 修正块始终在矩阵内。对当前最大进球 K，当 `lambda < K+2` 时：

```text
first_omitted = p(K) * lambda / (K+1)
tail_bound = first_omitted / (1 - lambda/(K+2)) + 1e-45
```

后续 Poisson 项比值单调递减，上式几何级数给出保守尾部界；1e-45 是 50 位、最多 30 步运算的舍入保护余量。lambda=0 的尾部精确为 0。选择首个 K≥1 且 bound≤1e-12 的范围；两侧分别决定 K。例：lambda=0.1/1/2/5/6 对应 K=7/14/18/27/30；lambda=8 在 cap 内不能满足容差，抛 `TailToleranceError`。lambda>30 提前同样失败，避免计算无法通过 cap 的极大 exp。数值范围溢出/下溢显式报错，不静默产出矩阵。

## Dixon–Coles 与 rho 合法性

令 h=lambda_home、a=lambda_away：

```text
tau(0,0) = 1 - h*a*rho
tau(0,1) = 1 + h*rho
tau(1,0) = 1 + a*rho
tau(1,1) = 1 - rho
其他 tau = 1
P_raw(i,j) = Poisson(h,i) * Poisson(a,j) * tau(i,j)
```

这是 [Dixon & Coles (1997) 的低比分修正](https://doi.org/10.1111/1467-9876.00065)。本阶段只使用显式 rho，不估计相关性。rho=0 时 tau 全为 1，使用同一代码路径退化为独立 Poisson。四个 tau 都必须非负，即使某格基准概率为零也验证；tau=0 合法。负 tau 拒绝输入，不 clamp、不 abs、不修改 rho。

计算 tau 时局部精度取 `max(50, 三项输入系数位数之和+1)`，保留乘积系数以检查边界符号，避免超长 Decimal 输入将微小负 tau 舍入成零而被接受。之后矩阵乘法、归一化及聚合仍固定 50 位。该验证规则同样随引擎版本固定。

四格修正的质量变化为 `-c,+c,+c,-c`，`c=exp(-h-a)*h*a*rho`，总和为零；完整保留四格使 DC 不改变截断区域外的概率。`tail_upper_bound=home.tail_upper_bound+away.tail_upper_bound`，使用联合上界，至多 2e-12；它描述归一化前遗漏的质量，不是 7+ 桶。

## 归一化与输出契约

先对 DC 后整个有限矩阵求和并记录 `pre_normalization_mass=M`，再记录 `normalization_factor=1/M`，所有格子统一乘以该因子。最终概率和允许绝对误差 `SUM_TOLERANCE=1e-45`；超出直接失败。没有末格残差桶，也不分别调整派生市场。有限支持上的条件归一化会对每格产生极小共同缩放，不能声称无限 Poisson 已被原样完整存储。

`ScoreMatrixResult` 为 JSON-ready TypedDict：

| 字段 | 类型 / 含义 |
| --- | --- |
| engine_version | 固定字符串 score-math-v1 |
| lambda_home / lambda_away / rho | 输入 Decimal 的字符串；零规范化为 0 |
| max_home_goals / max_away_goals | 各侧最大进球整数 |
| tail_upper_bound | 归一化前联合尾部上界，Decimal 字符串 |
| pre_normalization_mass / normalization_factor | 实际质量与统一缩放因子，Decimal 字符串 |
| matrix | 二维字符串数组，matrix[主队进球][客队进球]，包含所有范围内格子及零概率 |
| one_x_two | HOME / DRAW / AWAY → Decimal 字符串 |
| total_goals | 0 至 max_home_goals+max_away_goals 的每个整数键 → Decimal 字符串 |
| sporttery_ttg | 0 / 1 / 2 / 3 / 4 / 5 / 6 / 7+ → Decimal 字符串 |
| handicap | 请求的整数线字符串 → HOME / DRAW / AWAY 分布 |

## 同一矩阵的派生分布

`three_way_handicap(matrix, home_handicap)` 消费引擎输出矩阵，比较 `home_goals+home_handicap` 与 `away_goals`，逐格加到 HOME/DRAW/AWAY。1X2 直接调用 line=0，因此 HHAD(0) 与 1X2 连序列化字符串都严格一致。

HHAD 是体彩整数三项盘口。Python contract 仅接受 `int`（不含 bool）；小数、Decimal、float、字符串形式的 line 均拒绝。仅计算调用者给出的 lines，去重后数值升序输出，不修改输入对象；省略 lines 得到空 handicap。没有亚洲盘 quarter line、push、half win/half loss 或 EV 结算。

total_goals 对 i+j 相等的格子求和；TTG 0～6 分别求和，7+ 显式累加矩阵中所有 i+j≥7 的格子，不用尾部上界或未归一化残差代替。各分布和在 1e-45 内为 1。total_goals 表示整数进球数分布，不是大小球赔率定价或结算。

`top_scores(result,n)` 仅作展示，按 probability DESC、home ASC、away ASC 排序；n 为非负 int，0 返回空列表，超出格数返回全部。不修改原矩阵。没有竞彩比分“其他”选项映射。

## 验证与限制

数学测试使用更高精度（80 位）的确定性 factorial 公式及已知参数 Golden Cases 交叉验证，包括尾部界、cap 失败、四个 tau、零 lambda、对称性、统一归一化、各玩法守恒、排序、Context 隔离和 JSON 字符串契约。SQLite 与独立 PostgreSQL 全量回归继续验证原 Feature、Market、Odds、Results、analysis_visibility；结果记录在 PHASE4_SPEC。

cap=30 是明确的计算能力上限，较高 lambda 会被拒绝，不能把拒绝改为静默裁剪。若将来真实参数确需更大支持范围，先评估资源与精度、升级版本再扩展。真实 lambda/rho 来源、球队强度、训练与时间拆分回测均留给评审后的 P4-4B；本轮没有实施它们，也没有 P_model/P_final、Edge、EV、confidence 或推荐。
