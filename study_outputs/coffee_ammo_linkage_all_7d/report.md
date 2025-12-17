# 盒装挂耳咖啡与高级弹药价格联动分析结果

- Git 仓库：`DeltaForcePrice`
- 时间范围：`2025-08-20` ~ `2025-12-15`
- 时间频率：`1H`，缺失填充：`ffill(limit=1)`
- 交叉相关最大滞后：`±168` 个间隔（每间隔 `1H`）
- 格兰杰检验最大阶：`168`（在 log-diff 上）

## 输出文件

- `aligned_prices.csv`：对齐后的价格序列
- `correlations.csv`：整体 Pearson/Spearman 相关
- `rolling_correlations.csv`：滚动相关（每列一条弹药）
- `cross_corr.png` / `cross_corr__<item>.csv`：交叉相关函数图与明细
- `lag_and_granger_summary.csv`：交叉相关峰值与格兰杰检验摘要
- `granger__coffee_to__<item>.png/.csv`：咖啡→弹药的格兰杰检验

## 关键图

- `indexed_trends.png`
- `rolling_corr.png`
- `cross_corr.png`
