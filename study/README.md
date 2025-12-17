# 盒装挂耳咖啡与高级弹药联动实验

参考 `盒装挂耳咖啡与高级弹药价格联动分析方案.docx` 的流程（对齐、缺失处理、整体/滚动相关、交叉相关、格兰杰因果检验），在本仓库的 `price.json` 数据上复现实验并输出结果文件。

## 运行

在 `/home/delta/DeltaForcePrice` 目录执行（数据仓库在子目录 `DeltaForcePrice/`）：

```bash
python -m study.coffee_ammo_linkage \
  --repo DeltaForcePrice \
  --since 2025-08-20 --until 2025-12-15 \
  --out-dir study_outputs/coffee_ammo_linkage
```

如需把交叉相关的滞后搜索扩展到“天级别”，可用 `--max-lag`（按 `--freq` 自动换算）：

```bash
python -m study.coffee_ammo_linkage \
  --repo DeltaForcePrice \
  --since 2025-08-20 --until 2025-12-15 \
  --max-lag 4D \
  --out-dir study_outputs/coffee_ammo_linkage_lag_4d
```

如需把交叉相关/滚动相关/格兰杰都提升到“7 天级别”，建议将对齐频率降到小时级（避免 `10min` 下 lag=1008 过慢）：

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

输出目录会生成 `report.md`、若干 `.csv` 以及 `.png` 图表文件。

## 示例：`g1_24h/` 目录里的文件从哪来

以 `DeltaForcePrice/study_outputs/coffee_ammo_grid_0922_1109/g1_24h/` 为例：

- 该目录由 `DeltaForcePrice/study/run_coffee_ammo_grid.py` 的 `SPECS` 中的 `g1_24h` 这一组参数生成：它会 `subprocess.run()` 调用 `python -m study.coffee_ammo_linkage ... --out-dir <out_root>/g1_24h`。
- 目录内的所有 `.csv/.png/report.md` 均由 `DeltaForcePrice/study/coffee_ammo_linkage.py` 的 `run_study()` → `run_study_from_wide()` 产出（`wide` 由 Git 历史构建并按 `--freq` 对齐后进入分析环节）。

`g1_24h/` 内典型文件与产出链路如下（“指标调用链”写到最底层函数）：

- `aligned_prices.csv`：`run_study_from_wide()` 直接将对齐后的 `wide` 写出。
- `correlations.csv`（整体相关：Pearson/Spearman）：
  - `run_study_from_wide()` → `_pairwise_corr(coffee, ammo)`
  - `_pairwise_corr()` → `scipy.stats.pearsonr(x, y)`（Pearson 相关系数与 p 值）
  - `_pairwise_corr()` → `scipy.stats.spearmanr(x, y)`（Spearman 相关系数与 p 值）
- `rolling_correlations.csv`（滚动相关）：
  - `run_study_from_wide()` → `_rolling_corr(coffee, ammo, window, min_periods)`
  - `_rolling_corr()` → `pandas.Series.rolling(...).corr(...)`
- `cross_corr__7.62x51mm M62.csv`（以及同类 `cross_corr__*.csv`，交叉相关明细）：
  - `run_study_from_wide()` → `_cross_correlation(coffee, ammo, max_lag_intervals, interval)`
  - `_cross_correlation()` → `ammo.shift(...)`（逐 lag 平移）→ `Series.corr(...)`（逐 lag 相关系数）
  - `_cross_correlation()` → 基于 `freq` 折算 `lag_hours`
- `cross_corr.png`（交叉相关叠图）：
  - `run_study_from_wide()` → `_plot_cross_corr(cross_corr_dict)`（数据来自各 `cross_corr__*.csv` 同源的 DataFrame）
- `granger__coffee_to__7.62x51mm M62.csv`（以及同类 `granger__coffee_to__*.csv`，咖啡→弹药格兰杰）：
  - `run_study_from_wide()` → `_granger_pvalues(target=ammo, cause=coffee, maxlag)`
  - `_granger_pvalues()` → `_prepare_for_granger()`（`log(price).diff()` 或 `diff()`）
  - `_granger_pvalues()` → `statsmodels.tsa.stattools.grangercausalitytests(...)` → 提取 `ssr_ftest` 的统计量与 p 值
- `granger__7.62x51mm M62_to__coffee.csv`（反向对照：弹药→咖啡格兰杰）：
  - 调用链同上，只是 `target/cause` 对调
- `granger__coffee_to__7.62x51mm M62.png`（格兰杰 p 值曲线图）：
  - `run_study_from_wide()` → `_plot_granger(granger_df)`
- `lag_and_granger_summary.csv`（每个弹药的“交叉相关峰值 + 格兰杰最小 p 值”摘要）：
  - `run_study_from_wide()` 在每个弹药循环里汇总：交叉相关峰值（含正/负滞后拆分峰值）+ 格兰杰最小 p 值与对应 lag
- `indexed_trends.png`（标准化趋势图，首个点=100）：
  - `run_study_from_wide()` → `_plot_indexed_trends(wide_subset)`
- `rolling_corr.png`（滚动相关可视化）：
  - `run_study_from_wide()` → `_plot_rolling_corr(rolling_corr_df)`
- `report.md`（本次运行的参数摘要与输出索引）：
  - `run_study_from_wide()` 直接生成。

## Mermaid 框架图

下面分别为 `study/` 下三个脚本的框架图（强调主要函数调用过程），并在图中标注关键指标（Pearson/Spearman/滚动相关/交叉相关/格兰杰）的调用链。

### 1) `coffee_ammo_linkage.py`

```mermaid
graph TD
  A[main] --> B[_parse_args argparse]
  B --> C[parse duration args]
  C --> C1[_intervals_from_duration]
  C1 --> D[StudyConfig]
  D --> E[run_study]

  E --> F[build wide time series]
  F --> F1[cfg repo set]
  F1 --> G[_build_frame_from_git_history]
  F1 --> H[_load_price_records data file]
  G --> G1[_list_price_json_commits then _run_git git log]
  G --> G2[_read_price_json_at_commit then _run_git git show]
  G --> G3[_pick_price]
  H --> H1[_build_aligned_frame]

  G --> I[wide dataframe]
  H1 --> I
  I --> I1[resample last]
  I1 --> I2[ffill with limit]
  I2 --> J[run_study_from_wide]

  J --> K[loop ammo names]

  K --> P[_pairwise_corr]
  P --> P1[scipy pearsonr outputs r p]
  P --> P2[scipy spearmanr outputs r p]

  K --> R[_rolling_corr]
  R --> R1[pandas rolling corr]

  K --> X[_cross_correlation]
  X --> X1[pandas shift]
  X1 --> X2[pandas series corr per lag]
  X2 --> X3[convert lag to hours by freq]

  K --> GRA[_granger_pvalues]
  GRA --> GRA1[_prepare_for_granger log diff or diff]
  GRA1 --> GRA2[statsmodels grangercausalitytests]
  GRA2 --> GRA3[extract ssr ftest stat pvalue]

  J --> O1[write aligned prices csv]
  J --> O2[write correlations csv pearson spearman]
  J --> O3[write rolling correlations csv]
  K --> O4[write cross corr csv per item]
  K --> O5[write granger csv and granger png]
  J --> O6[write lag and granger summary csv]
  J --> V1[write png plots trends rolling cross]
  J --> RPT[write report md]
```

### 2) `run_coffee_ammo_grid.py`

```mermaid
graph TD
  A[main] --> B[argparse read args]
  B --> C[select ammo names]
  C --> D[loop SPECS]
  D --> E[build cmd call coffee_ammo_linkage]
  E --> F[subprocess run]
  F --> G[success]
  G --> H[read lag_and_granger_summary csv]
  H --> I[add experiment metadata]
  I --> J[append to summary rows]
  F --> K[failure]
  K --> K1[record stdout stderr]
  J --> L[write grid_summary csv]
  K --> M[write grid_failures csv]
```

### 3) `usage_weighted_analysis.py`

```mermaid
graph TD
  A[main] --> B[argparse read args]

  B --> C[_parse_weapon_usage_from_readme]
  C --> C1[_read_text_with_bom]
  C1 --> C2[regex parse section header]
  C2 --> U[usage_df]

  B --> D[loop grid_root]
  D --> E[analyze_grid]

  E --> F[read grid_summary csv]
  F --> F1[coerce numeric fields]
  F1 --> F2[compute max_lag_hours]
  U --> F3[sum usage_rate by ammo]
  F2 --> F4[merge usage_rate by item]

  F4 --> I1[item_summary groupby item]
  I1 --> I2[aggregate lag corr share metrics]
  I2 --> I3[_safe_corr uses pandas corr]

  F4 --> E1[exp_summary groupby experiment]
  E1 --> E2[_weighted_mean]

  I1 --> XSEC[xsec spearman cross section]
  XSEC --> X1[pandas corr method spearman]

  E --> O1[write usage_by_weapon csv]
  E --> O2[write usage_item_summary csv]
  E --> O3[write usage_experiment_summary csv]
  E --> O4[write usage_xsec_summary csv]
  E --> O5[write usage_analysis md]
```
