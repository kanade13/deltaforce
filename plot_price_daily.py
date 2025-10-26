# -*- coding: utf-8 -*-
"""
绘制指定物品在给定日期范围内的日均价曲线。
Daily average trend chart for items tracked in orzice/DeltaForcePrice.

示例：
    python plot_price_daily.py --repo . --item "盒装挂耳咖啡" --since 2025-08-20 --until 2025-10-26 --out avg.png
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import matplotlib
import pandas as pd

if "MPLBACKEND" not in os.environ:
    # 使用非交互式后端，方便在无显示环境下运行
    matplotlib.use("Agg")

import matplotlib.pyplot as plt

from plot_price import (
    ascii_fallback,
    ensure_cjk_font,
    is_ammo_item,
    list_price_json_commits,
    pick_price,
    read_price_json_at_commit,
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="按日平均价格绘制三角洲物品价格曲线（数据来自 price.json 的 Git 历史）"
    )
    parser.add_argument("--repo", required=True, help="DeltaForcePrice 仓库的本地路径")
    parser.add_argument(
        "--item",
        dest="items",
        action="append",
        required=True,
        help='物品全名，可重复提供多次（例：--item "盒装挂耳咖啡"）',
    )
    parser.add_argument("--since", default=None, help="起始日期，例如 2025-08-20（可选）")
    parser.add_argument("--until", default=None, help="结束日期，例如 2025-10-26（可选）")
    parser.add_argument(
        "--fuzzy",
        action="store_true",
        help="使用包含匹配而非精确匹配物品名，适用于名称部分记忆不清的情形",
    )
    parser.add_argument(
        "--ammo-bundle-size",
        type=int,
        default=60,
        help="若识别为子弹时的批量大小（默认 60 发），设为 1 可禁用自动缩放",
    )
    parser.add_argument("--out", default="price_daily.png", help="输出图片路径")
    parser.add_argument(
        "--csv",
        default=None,
        help="可选：导出日均价数据为 CSV 文件，编码为 UTF-8-SIG",
    )
    parser.add_argument(
        "--font",
        default=None,
        help="自定义中文字体（文件路径或字体族名），确保图表文字不乱码",
    )
    return parser.parse_args()


def collect_price_points(
    repo: Path,
    targets: List[str],
    since: Optional[str],
    until: Optional[str],
    fuzzy: bool,
    bundle_multipliers: Dict[str, int],
) -> Tuple[Dict[str, List[Tuple[pd.Timestamp, int]]], List[str]]:
    """
    Gather raw timestamped price records for each target item.

    Returns:
        records_map: item -> [(timestamp, price), ...]
        warnings: list of warning messages encountered during collection
    """
    warnings: List[str] = []
    print("扫描提交历史 ...")
    commits = list_price_json_commits(repo, since, until)
    if not commits:
        print("在指定时间范围内未找到 price.json 的提交。", file=sys.stderr)
        sys.exit(1)

    records_map: Dict[str, List[Tuple[pd.Timestamp, int]]] = {item: [] for item in targets}

    for sha, commit_time in commits:
        try:
            items = read_price_json_at_commit(repo, sha)
        except json.JSONDecodeError:
            warnings.append(f"[warn] {sha[:7]} 的 price.json JSON 解析失败，已跳过。")
            continue
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"[warn] {sha[:7]} 读取失败：{exc}")
            continue

        for item in targets:
            price = pick_price(items, item, exact=not fuzzy)
            if price is None:
                continue
            multiplier = bundle_multipliers.get(item, 1)
            scaled_price = int(price) * multiplier
            # commit_time 可能含时区，这里统一转换为 pandas 时间戳（UTC）
            ts = pd.to_datetime(commit_time, utc=True)
            records_map[item].append((ts, scaled_price))

    return records_map, warnings


def to_daily_average(
    records_map: Dict[str, List[Tuple[pd.Timestamp, int]]]
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Convert raw price records into a daily average DataFrame.

    Returns:
        df_daily: DataFrame indexed by date (Timestamp at midnight) with mean prices.
        missing_items: items that have no data at all.
    """
    available_series: List[pd.Series] = []
    missing_items: List[str] = []

    for item, points in records_map.items():
        if not points:
            missing_items.append(item)
            continue
        df_item = pd.DataFrame(points, columns=["ts", "price"]).drop_duplicates()
        df_item["ts"] = pd.to_datetime(df_item["ts"], utc=True).dt.tz_convert(None)
        df_item = df_item.sort_values("ts").set_index("ts")
        series = df_item["price"]
        series.name = item
        available_series.append(series)

    if not available_series:
        return pd.DataFrame(), missing_items

    df = pd.concat(available_series, axis=1).sort_index()
    # 以日为频率求平均
    df_daily = df.resample("1D").mean()
    return df_daily, missing_items


def apply_date_window(
    df_daily: pd.DataFrame, since: Optional[str], until: Optional[str]
) -> pd.DataFrame:
    """Reindex to cover the requested date window."""
    if df_daily.empty:
        return df_daily

    start = df_daily.index.min()
    end = df_daily.index.max()

    if since:
        start = pd.to_datetime(since).normalize()
    if until:
        end = pd.to_datetime(until).normalize()

    if end < start:
        raise ValueError("until 早于 since，时间范围无效。")

    full_range = pd.date_range(start=start, end=end, freq="D")
    return df_daily.reindex(full_range)


def maybe_export_csv(df_daily: pd.DataFrame, csv_path: Optional[str]) -> None:
    """Export daily averages to CSV if requested."""
    if not csv_path:
        return
    export_df = df_daily.copy()
    export_df.index.name = "date"
    export_df.reset_index().to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"已导出 CSV：{csv_path}")


def main() -> None:
    """CLI entry point."""
    args = parse_args()

    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print("repo 不是一个有效的 Git 仓库目录。", file=sys.stderr)
        sys.exit(3)

    targets: List[str] = []
    for raw in args.items:
        item = raw.strip()
        if not item:
            continue
        if item not in targets:
            targets.append(item)

    if not targets:
        print("请至少提供一个有效的物品名称。", file=sys.stderr)
        sys.exit(4)

    bundle_multipliers: Dict[str, int] = {}
    for item in targets:
        multiplier = args.ammo_bundle_size if is_ammo_item(item) else 1
        if multiplier < 1:
            multiplier = 1
        bundle_multipliers[item] = multiplier
        if multiplier > 1:
            print(f"已按 {multiplier} 发每组计价：{item}")

    records_map, warnings = collect_price_points(
        repo=repo,
        targets=targets,
        since=args.since,
        until=args.until,
        fuzzy=args.fuzzy,
        bundle_multipliers=bundle_multipliers,
    )
    for warn in warnings:
        print(warn, file=sys.stderr)

    df_daily, missing_items = to_daily_average(records_map)

    if missing_items:
        print(
            "[warn] 以下物品在指定时间范围内未找到价格数据："
            + ", ".join(missing_items),
            file=sys.stderr,
        )

    if df_daily.empty:
        print("未找到可用于绘制的价格数据，请确认物品名称与日期范围。", file=sys.stderr)
        sys.exit(2)

    df_daily = apply_date_window(df_daily, args.since, args.until)

    preferred_fonts: List[str] = []
    font_file: Optional[Path] = None
    if args.font:
        candidate = Path(args.font).expanduser()
        if candidate.is_file():
            font_file = candidate
        else:
            preferred_fonts.append(args.font)

    font_family = ensure_cjk_font(preferred=preferred_fonts, font_file=font_file)
    if font_family:
        print(f"已启用中文字体：{font_family}")
    else:
        print(
            "[warn] 未找到可用中文字体，图表中文字可能显示为方块，请安装 Noto Sans CJK、SimHei 等字体。",
            file=sys.stderr,
        )

    maybe_export_csv(df_daily, args.csv)

    plt.figure(figsize=(12, 5))
    for column in df_daily.columns:
        display_name = column
        multiplier = bundle_multipliers.get(column, 1)
        if multiplier > 1:
            display_name = f"{column} (x{multiplier})"
        label = display_name if font_family else ascii_fallback(display_name)
        plt.plot(
            df_daily.index,
            df_daily[column],
            lw=1.6,
            marker="o",
            markersize=3,
            label=label,
        )

    raw_title_items: List[str] = []
    for col in df_daily.columns:
        multiplier = bundle_multipliers.get(col, 1)
        if multiplier > 1:
            raw_title_items.append(f"{col}×{multiplier}")
        else:
            raw_title_items.append(col)

    if font_family:
        title_text = "、".join(raw_title_items) + " 日均价走势"
        xlabel = "日期"
        ylabel = "日均价"
    else:
        title_text = ", ".join(ascii_fallback(item) for item in raw_title_items) + " daily average price"
        xlabel = "Date"
        ylabel = "Average Price"

    plt.title(title_text)
    plt.xlabel(xlabel)
    plt.ylabel(ylabel)
    plt.grid(True, alpha=0.3)
    plt.legend(loc="best")
    plt.tight_layout()
    plt.gcf().autofmt_xdate()
    plt.savefig(args.out, dpi=160)
    print(f"已输出图片：{args.out}")


if __name__ == "__main__":
    main()

