# -*- coding: utf-8 -*-
"""
绘制指定物品在给定日期范围内的周均价曲线。
Weekly average trend chart for items tracked in orzice/DeltaForcePrice.

示例：
    python plot_price_weekly.py --repo . --item "盒装挂耳咖啡" --since 2025-08-20 --until 2025-10-26 --out avg_week.png
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

from plot_price import (
    ascii_fallback,
    is_ammo_item,
    list_price_json_commits,
    pick_price,
    read_price_json_at_commit,
)

CJK_FONT_CANDIDATES: List[Path] = [
    Path("/usr/share/fonts/truetype/wqy/wqy-microhei.ttc"),
    Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
    Path("/usr/share/fonts/truetype/arphic/ukai.ttc"),
    Path("/usr/share/fonts/truetype/arphic/uming.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    Path("/usr/share/fonts/opentype/noto/NotoSansSC-Regular.otf"),
    Path("/usr/local/share/fonts/NotoSansCJKsc-Regular.otf"),
    Path("/Library/Fonts/Songti.ttc"),
    Path("/Library/Fonts/STHeiti Light.ttc"),
    Path("/System/Library/Fonts/STHeiti Light.ttc"),
    Path("/System/Library/Fonts/PingFang.ttc"),
    Path("/mnt/c/Windows/Fonts/msyh.ttc"),
    Path("/mnt/c/Windows/Fonts/msyh.ttf"),
    Path("/mnt/c/Windows/Fonts/msyhbd.ttc"),
    Path("/mnt/c/Windows/Fonts/msyhbd.ttf"),
    Path("/mnt/c/Windows/Fonts/msjh.ttc"),
    Path("/mnt/c/Windows/Fonts/simhei.ttf"),
    Path("/mnt/c/Windows/Fonts/simsun.ttc"),
    Path("/mnt/c/Windows/Fonts/simkai.ttf"),
    Path("/mnt/c/Windows/Fonts/simfang.ttf"),
]

COLOR_PALETTE = [
    "#3366CC",
    "#DC3912",
    "#FF9900",
    "#109618",
    "#990099",
    "#0099C6",
    "#DD4477",
    "#66AA00",
    "#B82E2E",
    "#316395",
    "#994499",
    "#22AA99",
    "#AAAA11",
]


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments."""
    parser = argparse.ArgumentParser(
        description="按周平均价格绘制三角洲物品价格曲线（数据来自 price.json 的 Git 历史）"
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
    parser.add_argument("--out", default="price_weekly.png", help="输出图片路径")
    parser.add_argument(
        "--csv",
        default=None,
        help="可选：导出周均价数据为 CSV 文件，编码为 UTF-8-SIG",
    )
    parser.add_argument(
        "--font",
        default=None,
        help="自定义中文字体文件路径；如未提供则尝试自动查找常见 CJK 字体",
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
            ts = pd.to_datetime(commit_time, utc=True)
            records_map[item].append((ts, scaled_price))

    return records_map, warnings


def to_weekly_average(
    records_map: Dict[str, List[Tuple[pd.Timestamp, int]]]
) -> Tuple[pd.DataFrame, List[str]]:
    """
    Convert raw price records into a weekly average DataFrame.

    Returns:
        df_weekly: DataFrame indexed by week start (Monday) with mean prices.
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
    df_weekly = df.resample("W-MON", label="left", closed="left").mean()
    return df_weekly, missing_items


def apply_week_window(
    df_weekly: pd.DataFrame, since: Optional[str], until: Optional[str]
) -> pd.DataFrame:
    """Reindex to cover the requested weekly window."""
    if df_weekly.empty:
        return df_weekly

    start = df_weekly.index.min()
    end = df_weekly.index.max()

    if since:
        start = pd.to_datetime(since).normalize()
    if until:
        end = pd.to_datetime(until).normalize()

    if end < start:
        raise ValueError("until 早于 since，时间范围无效。")

    freq = df_weekly.index.inferred_freq or "W-MON"
    full_range = pd.date_range(start=start, end=end, freq=freq)
    return df_weekly.reindex(full_range)


def maybe_export_csv(df_weekly: pd.DataFrame, csv_path: Optional[str]) -> None:
    """Export weekly averages to CSV if requested."""
    if not csv_path:
        return
    export_df = df_weekly.copy()
    export_df.index.name = "week_start"
    export_df.reset_index().to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"已导出 CSV：{csv_path}")


def resolve_font_path(font_arg: Optional[str]) -> Optional[Path]:
    """Resolve a usable font path for Pillow rendering."""
    if font_arg:
        candidate = Path(font_arg).expanduser()
        if candidate.is_file():
            return candidate
        try:
            from matplotlib import font_manager  # type: ignore

            found = Path(font_manager.findfont(font_arg, fallback_to_default=False))
            if found.is_file():
                return found
        except Exception:
            pass

    fonts_dir = Path(__file__).resolve().parent / "fonts"
    if fonts_dir.is_dir():
        for pattern in ("*.ttf", "*.otf", "*.ttc"):
            for path in sorted(fonts_dir.glob(pattern)):
                if path.is_file():
                    return path

    for path in CJK_FONT_CANDIDATES:
        if path.is_file():
            return path
    return None


def text_dimensions(text: str, font: ImageFont.ImageFont) -> Tuple[int, int]:
    """Measure rendered text width and height."""
    bbox = font.getbbox(text)
    return bbox[2] - bbox[0], bbox[3] - bbox[1]


def paste_rotated_text(
    base_img: Image.Image,
    position: Tuple[float, float],
    text: str,
    font: ImageFont.ImageFont,
    angle: float,
    fill: str,
) -> None:
    """Draw rotated text onto the base image."""
    if not text:
        return
    bbox = font.getbbox(text)
    width = max(1, bbox[2] - bbox[0])
    height = max(1, bbox[3] - bbox[1])
    text_img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    text_draw = ImageDraw.Draw(text_img)
    text_draw.text((-bbox[0], -bbox[1]), text, font=font, fill=fill)
    rotated = text_img.rotate(angle, resample=Image.BICUBIC, expand=True)
    x = int(position[0] - rotated.width / 2)
    y = int(position[1] - rotated.height / 2)
    base_img.paste(rotated, (x, y), rotated)


def format_tick_value(value: float) -> str:
    """Format numeric tick labels."""
    if abs(value) >= 1000:
        return f"{value:,.0f}"
    if abs(value) >= 10:
        return f"{value:.1f}"
    return f"{value:.2f}"


def draw_weekly_chart(
    df_weekly: pd.DataFrame,
    out_path: Path,
    bundle_multipliers: Dict[str, int],
    font_path: Optional[Path],
) -> bool:
    """
    Render weekly average chart with Pillow.

    Returns:
        bool: True if a CJK-capable font was used; False if ASCII fallback was required.
    """
    out_path = out_path.expanduser()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    dates = list(df_weekly.index)
    if not dates:
        raise ValueError("缺少可绘制的日期索引。")

    flat_values = [
        float(v) for v in df_weekly.to_numpy().flatten() if pd.notna(v)
    ]
    if not flat_values:
        raise ValueError("缺少可绘制的价格数据。")

    y_min = min(flat_values)
    y_max = max(flat_values)
    if math.isclose(y_min, y_max):
        delta = max(abs(y_min) * 0.05, 1.0)
        y_min -= delta
        y_max += delta
    else:
        padding = max((y_max - y_min) * 0.05, 1.0)
        y_min -= padding
        y_max += padding

    width, height = 1280, 640
    plot_left, plot_right = 90, width - 80
    plot_top, plot_bottom = 90, height - 120
    plot_width = plot_right - plot_left
    plot_height = plot_bottom - plot_top

    if len(dates) == 1:
        x_positions = [plot_left + plot_width / 2]
    else:
        step = plot_width / (len(dates) - 1)
        x_positions = [plot_left + i * step for i in range(len(dates))]

    def value_to_y(value: float) -> float:
        return plot_bottom - (value - y_min) / (y_max - y_min) * plot_height

    image = Image.new("RGB", (width, height), "#FFFFFF")
    draw = ImageDraw.Draw(image)

    font_cache: Dict[int, ImageFont.ImageFont] = {}
    cjk_enabled = font_path is not None

    def get_font(size: int) -> ImageFont.ImageFont:
        nonlocal cjk_enabled
        if size not in font_cache:
            if font_path:
                try:
                    font_cache[size] = ImageFont.truetype(str(font_path), size)
                except Exception:
                    font_cache[size] = ImageFont.load_default()
                    cjk_enabled = False
            else:
                font_cache[size] = ImageFont.load_default()
                cjk_enabled = False
        return font_cache[size]

    # Background grid
    draw.rectangle(
        [(plot_left, plot_top), (plot_right, plot_bottom)],
        outline="#444444",
        width=2,
    )

    y_ticks = 6
    font_small = get_font(14)
    for i in range(y_ticks):
        if y_ticks == 1:
            level = y_min
        else:
            level = y_min + (y_max - y_min) * i / (y_ticks - 1)
        y = value_to_y(level)
        draw.line([(plot_left, y), (plot_right, y)], fill="#E6E6E6", width=1)
        label = format_tick_value(level)
        label = label if cjk_enabled else ascii_fallback(label)
        text_w, text_h = text_dimensions(label, font_small)
        draw.text(
            (plot_left - 14 - text_w, y - text_h / 2),
            label,
            fill="#333333",
            font=font_small,
        )

    legend_entries: List[Tuple[str, str]] = []

    for idx, column in enumerate(df_weekly.columns):
        color = COLOR_PALETTE[idx % len(COLOR_PALETTE)]
        multiplier = bundle_multipliers.get(column, 1)
        display_name = column
        if multiplier > 1:
            display_name = f"{column} (x{multiplier})"

        legend_label = display_name if cjk_enabled else ascii_fallback(display_name)
        legend_entries.append((legend_label, color))

        segment: List[Tuple[float, float]] = []
        markers: List[Tuple[float, float]] = []
        for x, raw in zip(x_positions, df_weekly[column].tolist()):
            if raw is None or pd.isna(raw):
                if len(segment) >= 2:
                    draw.line(segment, fill=color, width=2)
                segment = []
                continue
            y = value_to_y(float(raw))
            segment.append((x, y))
            markers.append((x, y))
        if len(segment) >= 2:
            draw.line(segment, fill=color, width=2)
        for x, y in markers:
            draw.ellipse((x - 3, y - 3, x + 3, y + 3), fill=color, outline=color)

    # X-axis ticks and labels
    for x, date in zip(x_positions, dates):
        draw.line([(x, plot_bottom), (x, plot_bottom + 6)], fill="#444444", width=1)
        label = date.strftime("%Y-%m-%d")
        label = label if cjk_enabled else ascii_fallback(label)
        paste_rotated_text(
            image,
            (x, plot_bottom + 38),
            label,
            font_small,
            angle=45,
            fill="#333333",
        )

    # Legend
    legend_font = get_font(16)
    legend_x = plot_left + 12
    legend_y = plot_top + 12
    legend_line_height = 22
    legend_col_width = 240
    for label, color in legend_entries:
        draw.rectangle(
            (legend_x, legend_y, legend_x + 16, legend_y + 16),
            fill=color,
            outline=color,
        )
        draw.text(
            (legend_x + 22, legend_y + 2),
            label,
            font=legend_font,
            fill="#1B1B1B",
        )
        legend_y += legend_line_height
        if legend_y > plot_top + 12 + legend_line_height * 6:
            legend_y = plot_top + 12
            legend_x += legend_col_width

    # Title and axis labels
    raw_title_items: List[str] = []
    for col in df_weekly.columns:
        multiplier = bundle_multipliers.get(col, 1)
        if multiplier > 1:
            raw_title_items.append(f"{col}×{multiplier}")
        else:
            raw_title_items.append(col)

    if cjk_enabled:
        title_text = "、".join(raw_title_items) + " 周均价走势"
        xlabel = "周起始日（周一）"
        ylabel = "周均价"
    else:
        title_text = ", ".join(ascii_fallback(item) for item in raw_title_items) + " weekly average price"
        xlabel = "Week start (Mon)"
        ylabel = "Average Price"

    title_font = get_font(28)
    axis_font = get_font(20)
    title_w, title_h = text_dimensions(title_text, title_font)
    draw.text(
        (plot_left, 30),
        title_text,
        font=title_font,
        fill="#111111",
    )
    xlabel_w, xlabel_h = text_dimensions(xlabel, axis_font)
    draw.text(
        ((plot_left + plot_right) / 2 - xlabel_w / 2, height - 70),
        xlabel,
        font=axis_font,
        fill="#111111",
    )
    paste_rotated_text(
        image,
        (plot_left - 70, (plot_top + plot_bottom) / 2),
        ylabel,
        axis_font,
        angle=90,
        fill="#111111",
    )

    image.save(out_path, format="PNG")
    return cjk_enabled


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

    df_weekly, missing_items = to_weekly_average(records_map)

    if missing_items:
        print(
            "[warn] 以下物品在指定时间范围内未找到价格数据："
            + ", ".join(missing_items),
            file=sys.stderr,
        )

    if df_weekly.empty:
        print("未找到可用于绘制的价格数据，请确认物品名称与日期范围。", file=sys.stderr)
        sys.exit(2)

    df_weekly = apply_week_window(df_weekly, args.since, args.until)

    maybe_export_csv(df_weekly, args.csv)

    font_path = resolve_font_path(args.font)

    cjk_enabled = draw_weekly_chart(
        df_weekly=df_weekly,
        out_path=Path(args.out),
        bundle_multipliers=bundle_multipliers,
        font_path=font_path,
    )

    if cjk_enabled and font_path:
        print(f"已启用中文字体文件：{font_path}")
    else:
        print(
            "[warn] 未找到可用中文字体文件，图表文字将使用 ASCII 回退显示。",
            file=sys.stderr,
        )

    print(f"已输出图片：{args.out}")


if __name__ == "__main__":
    main()

