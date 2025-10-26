# Plot Price 用法速览

## 基础流程
1. 准备好本地 `DeltaForcePrice` 仓库路径，并确认 Git 可以访问提交历史。
2. 在激活好的 Python 环境中安装 `pandas`、`matplotlib`，必要时配置中文字体（可放入 `fonts/` 目录或使用 `--font`）。
3. 通过 `--item` 指定一个或多个物品名称，脚本会自动识别弹药并按 60 发/组换算价格（可用 `--ammo-bundle-size` 调整）。
4. 根据需要添加 `--since`、`--until` 时间范围、`--csv` 数据导出或 `--fuzzy` 模糊匹配等选项。

## 参数要点
- `--repo PATH`：目标仓库根目录，通常为 `/home/delta/DeltaForcePrice`。
- `--item NAME`：物品全名，可重复多次；弹药命名（如 `7.62x54R BT`）将自动按组计价。
- `--ammo-bundle-size N`：弹药组装数量，默认 60；设为 1 可回退到单发价格。
- `--resample ffill`：按 10 分钟节奏对齐并前向填补价格，适合观察连续走势。
- `--font FILE|FAMILY`：显式设定中文字体，避免图例或坐标轴出现方块字。
- `--csv OUTPUT.csv`：导出整理后的价格数据，便于进一步分析。

## 常用示例
```bash
# 单个物品（头盔）价格曲线
python plot_price.py --repo /home/delta/DeltaForcePrice --item "老式钢盔 (几乎全新)" --out helmet.png

# 子弹按 50 发/组计价，导出 CSV
python plot_price.py --repo /home/delta/DeltaForcePrice --item "6.8x51mm Hybrid" --ammo-bundle-size 50 --csv hybrid.csv --out hybrid.png

# 多物品对比（含多种弹药）
python plot_price.py --repo /home/delta/DeltaForcePrice \
  --item "盒装挂耳咖啡" \
  --item "6.8x51mm Hybrid" \
  --item "7.62x51mm M62" \
  --item "7.62x54R BT" \
  --item "9x19mm PBP" \
  --item "7.62x39mm AP" \
  --item "9x39mm BP" \
  --since 2025-08-20 --until 2025-10-26 \
  --out mix.png

# 模糊匹配与字体覆盖
python plot_price.py --repo /home/delta/DeltaForcePrice --item "Hybrid" --fuzzy --font /mnt/c/Windows/Fonts/msyh.ttc --out fuzzy.png
```

> 提示：如命令运行时出现 `MPLBACKEND` 或字体相关警告，可添加 `MPLBACKEND=Agg` 环境变量或检查字体配置。
