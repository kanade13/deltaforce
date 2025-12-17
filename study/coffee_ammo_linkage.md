# 盒装挂耳咖啡 × 高级弹药：联动分析实验说明（固定版）

本说明用于“下次会话继续”时快速恢复上下文：包含实验设置、结论摘要、复现命令、代码结构指引与输出索引。

## 数据与范围

- 数据来源：本仓库 Git 历史中的 `price.json`（用提交时间 `%cI` 作为时间戳）。
- 数据文件位置（参考）：`DeltaForcePrice/DeltaForcePrice/price.json`（单文件只是一个快照；**实验使用 Git 历史**拼接时间序列）。
- 时间范围：`2025-08-20` ~ `2025-12-15`（可用 `--since/--until` 改）。
- 采样频率：10 分钟（与数据采集节奏一致）。

## 实验设置（重要参数）

脚本：`study/coffee_ammo_linkage.py`

- 目标物品：
  - 咖啡：`盒装挂耳咖啡`
  - 默认弹药列表（可 `--ammo` 覆盖）：`5.56x45mm M995`、`6.8x51mm Hybrid`、`7.62x39mm AP`、`7.62x51mm M62`、`7.62x54R BT`、`9x19mm PBP`、`9x39mm BP`
- 对齐与缺失处理：
  - `--freq 10min`
  - `--ffill-limit 6`（最多前向填充 6 个 10 分钟间隔=1 小时；更长断档保留缺失；`0` 表示禁用，`-1` 表示无限填充）
- 滚动相关：
  - `--rolling-window 144`（144×10min=1 天）
  - `--rolling-min-periods 96`
  - 或用 `--rolling-window-duration 7D` / `--rolling-min-periods-duration 5D` 这类“时长”参数（会按 `--freq` 自动换算成 intervals）
- 交叉相关（滞后分析）：
  - `--max-lag-intervals 144`（±144×10min=±24 小时；正滞后=咖啡领先）
  - 或用 `--max-lag 4D` 这类“时长”参数（会按 `--freq` 自动换算成 intervals）
- 格兰杰因果：
  - `--max-granger-lag 12`
  - 或用 `--max-granger-lag-duration 7D` 这类“时长”参数（会按 `--freq` 自动换算成 intervals）
  - 在 `log(价格).diff()` 上做检验（避免非平稳的趋势导致误判；若价格非正则退回 `diff()`）
  - 方向定义：
    - coffee→ammo：用咖啡过去值预测弹药未来值
    - ammo→coffee：反向检验用于对照
- 运行环境兼容性：
  - 由于某些环境下 OpenMP 共享内存不可用（会触发 `OMP: Error #179 Can't open SHM2`），脚本会默认设置：`MKL_THREADING_LAYER=GNU`，并将 `*_NUM_THREADS=1`。

## 可修改参数详解（会显著影响结论）

以下参数来自脚本 CLI（`study/coffee_ammo_linkage.py`），用于控制“取数范围/对齐方式/统计窗口/滞后搜索/格兰杰检验”。它们是下次复现实验时最需要关注与记录的部分。

- `--repo PATH`
  - 含义：从该 Git 仓库的 `price.json` **提交历史**构建时间序列（用提交时间 `%cI` 做时间戳），这是本实验默认/推荐的数据来源。
  - 影响：范围内提交越多，样本越多、运行越慢；结论也可能随时间窗口变化而变（建议做不同窗口的稳健性对照）。
  - 注意：不传 `--repo` 时会退回到 `--data` 的单文件快照；单文件通常不足以做时间序列联动分析（更适合调试脚本流程）。

- `--since YYYY-MM-DD` / `--until YYYY-MM-DD`
  - 含义：通过 `git log --since/--until` 过滤 `price.json` 的提交区间。
  - 影响：决定样本窗口与运行时长；也是最直接的“稳健性检验”维度。

- `--ammo NAME`（可重复）
  - 含义：指定要分析的弹药（或任意物品）名称；不传则使用脚本内置默认弹药列表。
  - 影响：决定输出哪些 `cross_corr__<item>.csv` / `granger__*.csv`，以及对比哪些序列。
  - 注意：本脚本使用**原始 price**，不会像 `plot_price.py` 那样按“60发/组”自动换算。

- `--fuzzy`
  - 含义：物品名用“子串包含”匹配替代精确匹配。
  - 风险：若子串能匹配多个物品，会命中列表中最先出现的结果，可能造成误配；严肃分析建议写全名并关闭 `--fuzzy`。

- `--freq`（默认 `10min`）
  - 含义：把所有时间点对齐到固定频率（`resample(freq).last()`），也是后续“窗口/滞后/阶数”的单位基准。
  - 影响：改变 `--freq` 会改变“1 个 interval”代表的真实时间长度，因此通常要同步调整下列 3 个参数：`--ffill-limit`、`--rolling-window`、`--max-granger-lag`、`--max-lag-intervals`。
  - 换算：`interval_seconds = pd.Timedelta(freq).total_seconds()`；交叉相关输出的 `lag_hours` 将据此换算。

- `--ffill-limit`（默认 `6`；`-1` 表示无限填充）
  - 含义：对齐后用前值填充缺失的最大步数（按 interval 计数）。
  - `0`：禁用填充（保留缺失，让后续相关/格兰杰自动丢掉缺失段）。
  - 影响：`limit` 越大，序列越“连续”，但越容易把长断档硬连起来，从而抬高相关/交叉相关/格兰杰显著性（产生误判风险）。
  - 例：`freq=10min` 时 `6` 约等于填充 1 小时；若改成 `freq=30min` 仍想“最多填 1 小时”，应改为 `--ffill-limit 2`。

- `--rolling-window`（默认 `144`）与 `--rolling-min-periods`（默认 `96`）
  - 含义：滚动相关的窗口长度与最小有效样本数（都按 interval 计数）。
  - 影响：窗口越大越平滑但更滞后；窗口越小越敏感但噪声更大。
  - 例：`freq=10min` 时 `144` 约等于 1 天；若改为 `freq=30min` 且仍想 1 天窗口，应改为 `--rolling-window 48`（并相应调小 `--rolling-min-periods`）。

- `--max-lag-intervals`（默认 `144`）
  - 含义：交叉相关函数搜索范围 `[-N, +N]`（单位 interval）。
  - 解释约定：脚本计算 `corr(coffee(t), ammo(t + lag))`，因此 `lag > 0` 表示“咖啡领先弹药”。
  - 影响：范围过大更容易在窗口边界处出现“峰值”（样本数变少 + 趋势/周期效应更突出），不一定更可信；建议按业务关心的最大滞后设定（如 ±24h）。

- `--max-granger-lag`（默认 `12`）
  - 含义：格兰杰因果检验的最大阶数（单位 interval），在 `log(价格).diff()`（或 `diff()`）上做检验以降低非平稳趋势影响。
  - 影响：lag 越大越慢、越吃样本，也更容易出现偶然显著；lag 太小可能错过真实延迟效应。
  - 例：`freq=10min` 时 `12` 约等于 2 小时；若改 `freq=30min` 仍想 2 小时，应改为 `--max-granger-lag 4`。

## 复现命令

在仓库根目录（`/home/delta/DeltaForcePrice`）运行：

```bash
python -m study.coffee_ammo_linkage \
  --repo DeltaForcePrice \
  --since 2025-08-20 --until 2025-12-15 \
  --out-dir study_outputs/coffee_ammo_linkage
```

4 天滞后范围版本（用于检验“天级别滞后”）：

```bash
python -m study.coffee_ammo_linkage \
  --repo DeltaForcePrice \
  --since 2025-08-20 --until 2025-12-15 \
  --max-lag 4D \
  --out-dir study_outputs/coffee_ammo_linkage_lag_4d
```

7 天级别（本次要求：交叉相关/滚动相关/格兰杰都按 7 天配置；为避免 `10min` 下 lag=1008 过慢，建议将频率降到 `1H`）：

```bash
python -m study.coffee_ammo_linkage \
  --repo DeltaForcePrice \
  --since 2025-08-20 --until 2025-12-15 \
  --freq 1H --ffill-limit 1 \
  --max-lag 7D \
  --rolling-window-duration 7D --rolling-min-periods-duration 5D \
  --max-granger-lag-duration 7D \
  --out-dir study_outputs/coffee_ammo_linkage_all_7d
```

可选：仅跑某段时间（更快）：

```bash
python -m study.coffee_ammo_linkage \
  --repo DeltaForcePrice \
  --since 2025-12-10 --until 2025-12-15 \
  --out-dir study_outputs/coffee_ammo_linkage
```

## 结论摘要（以 `2025-08-20`~`2025-12-15` 全量为准）

结果以输出目录中的 CSV 为准：

- 整体相关（Pearson/Spearman）：`study_outputs/coffee_ammo_linkage/correlations.csv`
- 交叉相关峰值 + 格兰杰摘要：`study_outputs/coffee_ammo_linkage/lag_and_granger_summary.csv`

关键结论（当前一次跑出的结果）：

1. **整体相关性显著**：咖啡与多数弹药呈显著正相关，最强的是 `7.62x51mm M62`（Pearson 约 0.70）；`9x19mm PBP` 与咖啡呈显著负相关（Pearson 约 -0.25）。
2. **“咖啡领先”不稳定**：交叉相关的峰值在不同弹药上出现于不同滞后（有的在正滞后，有的在负滞后，部分在窗口边界 ±24h），说明领先关系易受共同趋势/周期影响，需要结合更多稳健性检验。
3. **格兰杰结果不普遍**：在本参数设置下，并未出现“咖啡普遍格兰杰导致所有弹药”的一致证据；其中 `7.62x54R BT` 在 coffee→ammo 方向出现显著（best p≈0.000402，lag=5），其余多数不显著或方向不一致。

本次结果摘要表（便于下次会话快速对照；更完整/可追溯数据以 CSV 为准）：

| 弹药 | n | Pearson r | Spearman r | 交叉相关峰值 lag(h) | 峰值 corr | coffee→ammo 最小 p (lag) | ammo→coffee 最小 p (lag) |
|---|---:|---:|---:|---:|---:|---:|---:|
| 5.56x45mm M995 | 13069 | 0.424530 | 0.229130 | 7.333333 | 0.464235 | 0.734816 (1) | 0.569259 (2) |
| 6.8x51mm Hybrid | 13069 | 0.522757 | 0.322916 | -16.833333 | 0.566432 | 0.206613 (7) | 0.035346 (4) |
| 7.62x39mm AP | 13069 | 0.379924 | 0.356943 | 24.000000 | 0.432425 | 0.070053 (2) | 0.045808 (3) |
| 7.62x51mm M62 | 13069 | 0.697919 | 0.448584 | 7.166667 | 0.731442 | 0.437229 (6) | 0.617448 (11) |
| 7.62x54R BT | 13069 | 0.405736 | 0.327960 | 24.000000 | 0.478686 | 0.000402 (5) | 0.969103 (5) |
| 9x19mm PBP | 13069 | -0.246017 | -0.242638 | -23.833333 | -0.236330 | 0.076900 (11) | 0.663167 (7) |
| 9x39mm BP | 13069 | 0.488212 | 0.256241 | 6.000000 | 0.509237 | 0.873135 (11) | 0.898695 (1) |

## 代码结构指引（便于下次改动）

入口与主流程：

- CLI 入口：`study/coffee_ammo_linkage.py` 的 `main()` / `run_study()`
- 数据构建：
  - 优先从 Git 历史构建：`_list_price_json_commits()` + `_read_price_json_at_commit()` + `_build_frame_from_git_history()`
  -（备用）从单文件快照构建：`_load_price_records()` + `_build_aligned_frame()`（注意：单文件快照不足以做时间序列分析）
- 分析核心：
  - 整体相关：`_pairwise_corr()`
  - 滚动相关：`_rolling_corr()`
  - 交叉相关：`_cross_correlation()`（正滞后表示“咖啡领先”）
  - 格兰杰：`_granger_pvalues()`（在 log-diff 上）
- 绘图输出：
  - 趋势：`_plot_indexed_trends()`（用“首个点=100”标准化，避免不同量级影响阅读）
  - 滚动相关：`_plot_rolling_corr()`
  - 交叉相关：`_plot_cross_corr()`
  - 格兰杰 p 值：`_plot_granger()`

## 输出文件索引（`study_outputs/coffee_ammo_linkage/`）

- `report.md`：本次运行的参数摘要与输出清单
- `aligned_prices.csv`：对齐后的价格序列（index=time_utc，columns=物品名）
- `correlations.csv`：整体 Pearson/Spearman 相关（含样本量 n）
- `rolling_correlations.csv`：滚动相关序列（每列一条弹药）
- `indexed_trends.png`：标准化后的价格趋势对比图（首点=100）
- `rolling_corr.png`：滚动相关图
- `cross_corr.png`：所有弹药的交叉相关曲线叠图
- `cross_corr__<item>.csv`：单个弹药的交叉相关明细（lag/corr/n）
- `granger__coffee_to__<item>.csv/.png`：coffee→ammo 的格兰杰检验（各 lag 的 p 值）
- `granger__<item>_to__coffee.csv`：ammo→coffee 的对照检验
- `lag_and_granger_summary.csv`：每个弹药的交叉相关峰值与格兰杰最佳 p 值摘要
