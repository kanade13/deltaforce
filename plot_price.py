# -*- coding: utf-8 -*-
"""
从 orzice/DeltaForcePrice 的 Git 历史中提取某物品价格，并绘制时间序列曲线。
依赖：Python 3.8+，git（命令行），pandas，matplotlib
安装：pip install pandas matplotlib
用法示例见文档或命令行提示。
"""
import argparse
import os
import re
import subprocess
import sys
import json
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional, Dict

import matplotlib
import pandas as pd
if "MPLBACKEND" not in os.environ:
    # 使用非交互式后端，避免在无显示环境下崩溃
    matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager, rcParams


def ensure_cjk_font(
    preferred: Optional[List[str]] = None,
    font_file: Optional[Path] = None,
) -> Optional[str]:
    """
    为 Matplotlib 设置可用的中文字体，避免图表中文字显示为方块。
    返回成功使用的字体名称，若未找到则返回 None。
    """
    preferred = preferred or []
    if font_file and font_file.exists():
        try:
            font_manager.fontManager.addfont(str(font_file))
            name = font_manager.FontProperties(fname=str(font_file)).get_name()
            if name:
                preferred.insert(0, name)
        except Exception:
            pass

    candidate_files: List[Path] = []

    fonts_dir = Path(__file__).resolve().parent / "fonts"
    if fonts_dir.is_dir():
        for pattern in ("*.ttf", "*.otf", "*.ttc"):
            candidate_files.extend(fonts_dir.glob(pattern))

    system_font_candidates = [
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
    for candidate in system_font_candidates:
        if candidate.exists():
            candidate_files.append(candidate)

    seen_files = set()
    unique_candidates: List[Path] = []
    for path in candidate_files:
        if path.exists():
            key = path.resolve()
            if key not in seen_files:
                seen_files.add(key)
                unique_candidates.append(path)

    for font_path in unique_candidates:
        try:
            font_manager.fontManager.addfont(str(font_path))
            name = font_manager.FontProperties(fname=str(font_path)).get_name()
            if name and name not in preferred:
                preferred.append(name)
        except Exception:
            continue

    preferred_families = preferred + [
        "Noto Sans CJK SC",
        "Source Han Sans CN",
        "Microsoft YaHei",
        "PingFang SC",
        "WenQuanYi Micro Hei",
        "SimHei",
        "Sarasa UI SC",
    ]
    available = {f.name for f in font_manager.fontManager.ttflist}
    for family in preferred_families:
        if family in available:
            current = list(rcParams.get("font.sans-serif", []))
            rcParams["font.sans-serif"] = [family] + [f for f in current if f != family]
            rcParams["font.family"] = ["sans-serif"]
            rcParams["axes.unicode_minus"] = False
            return family
    rcParams["axes.unicode_minus"] = False
    return None


def ascii_fallback(text: str) -> str:
    """将无法显示的字符串转为 ASCII 友好的表示。"""
    try:
        text.encode("ascii")
        return text
    except UnicodeEncodeError:
        return " ".join(f"U+{ord(ch):04X}" for ch in text)


AMMO_MM_PATTERN = re.compile(r"\d+(?:\.\d+)?x\d+(?:\.\d+)?(?:mm|m|r)", re.IGNORECASE)
AMMO_START_DOT_PATTERN = re.compile(r"^\.[0-9]")
AMMO_WORD_PATTERN = re.compile(r"\b(acp|ae|magnum|sp|hp|fmj|jhp|ap|bt|rip)\b", re.IGNORECASE)


def is_ammo_item(name: str) -> bool:
    """
    粗略判断物品是否为子弹，用来应用批量（如 60 发）价格。
    规则基于常见口径/Gauge 命名约定。
    """
    lowered = name.lower()
    if AMMO_MM_PATTERN.search(lowered):
        return True
    if "gauge" in lowered:
        return True
    if AMMO_START_DOT_PATTERN.search(lowered) and AMMO_WORD_PATTERN.search(lowered):
        return True
    if any(keyword in lowered for keyword in ("buckshot", "slug", "flechette")):
        return True
    return False

def run_git(repo: Path, args: List[str]) -> str:
    """在 repo 目录运行 git 命令并返回文本输出。"""
    cmd = ["git", "-C", str(repo)] + args
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        print(res.stderr.strip(), file=sys.stderr)
        raise RuntimeError(f"git 命令失败: {' '.join(cmd)}")
    return res.stdout

def list_price_json_commits(repo: Path, since: Optional[str], until: Optional[str]) -> List[Tuple[str, datetime]]:
    """
    列出在给定时间范围内改动过 price.json 的提交（按时间正序）。
    返回 [(sha, commit_time_utc), ...]
    """
    args = ["log", "--reverse", "--format=%H|%cI"]  # %cI = 提交者时间（ISO 8601）
    if since:
        args.insert(1, f"--since={since}")
    if until:
        args.insert(1, f"--until={until}")
    args += ["--", "price.json"]
    out = run_git(repo, args)
    commits = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, iso = line.split("|", 1)
        try:
            t = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except Exception:
            # 兜底解析
            t = pd.to_datetime(iso, utc=True).to_pydatetime()
        commits.append((sha, t))
    return commits

def read_price_json_at_commit(repo: Path, sha: str) -> List[dict]:
    """读取某次提交的 price.json 内容（JSON 数组）。"""
    out = run_git(repo, ["show", f"{sha}:price.json"])
    data = json.loads(out)
    if not isinstance(data, list):
        raise ValueError("price.json 不是数组")
    return data

def pick_price(items: List[dict], item_query: str, exact: bool = True) -> Optional[int]:
    """
    在该次提交的物品列表里找目标物品的价格。
    exact=True 用精确匹配 'name' 完整相等；False 为子串包含匹配（可能多命中取第一个）。
    """
    if exact:
        for it in items:
            if it.get("name") == item_query:
                return it.get("price")
    else:
        for it in items:
            if item_query in str(it.get("name", "")):
                return it.get("price")
    return None

def main():
    ap = argparse.ArgumentParser(description="绘制三角洲某物品的价格变化曲线（读取 Git 历史中的 price.json）")
    ap.add_argument("--repo", required=True, help="DeltaForcePrice 仓库的本地路径")
    ap.add_argument(
        "--item",
        dest="items",
        action="append",
        required=True,
        help="物品全名，可重复指定多次以比较多条曲线（如：--item \"老式钢盔 (几乎全新)\"）",
    )
    ap.add_argument("--since", default=None, help="起始日期，例如 2025-08-20（可省略）")
    ap.add_argument("--until", default=None, help="结束日期，例如 2025-10-26（可省略）")
    ap.add_argument("--fuzzy", action="store_true", help="用包含匹配而非精确匹配物品名")
    ap.add_argument("--resample", choices=["none", "ffill"], default="none",
                    help="是否按 10 分钟重采样；ffill 为前向填充缺口（设置适度 limit 防止跨大断档）")
    ap.add_argument("--out", default="price_plot.png", help="输出图片路径")
    ap.add_argument("--csv", default=None, help="可选：导出数据为 CSV 路径")
    ap.add_argument("--font", default=None,
                    help="自定义中文字体（文件路径或字体族名），用于避免图表中文字显示异常")
    ap.add_argument(
        "--ammo-bundle-size",
        type=int,
        default=60,
        help="当物品被识别为子弹时的批量大小（默认 60 发）；设为 1 可禁用自动放大。",
    )
    args = ap.parse_args()
    
    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        ap.error("repo 不是一个 Git 仓库目录")

    # 去重并保持顺序
    targets: List[str] = []
    for raw in args.items:
        item = raw.strip()
        if not item:
            continue
        if item not in targets:
            targets.append(item)

    if not targets:
        print("请至少提供一个有效的物品名称。", file=sys.stderr)
        sys.exit(3)

    bundle_multipliers: Dict[str, int] = {}
    for item in targets:
        multiplier = args.ammo_bundle_size if is_ammo_item(item) else 1
        if multiplier < 1:
            multiplier = 1
        bundle_multipliers[item] = multiplier
        if multiplier > 1:
            print(f"已按 {multiplier} 发每组计价：{item}")

    print("扫描提交历史 ...")
    commits = list_price_json_commits(repo, args.since, args.until)
    if not commits:
        print("在指定时间范围内未找到 price.json 的提交。", file=sys.stderr)
        sys.exit(1)

    records_map: dict[str, List[Tuple[datetime, int]]] = {item: [] for item in targets}
    # 遍历提交（已为时间升序）
    for sha, t in commits:
        try:
            items = read_price_json_at_commit(repo, sha)
            for item in targets:
                price = pick_price(items, item, exact=not args.fuzzy)
                if price is not None:
                    scaled_price = int(price) * bundle_multipliers.get(item, 1)
                    records_map[item].append((pd.to_datetime(t), scaled_price))
        except json.JSONDecodeError:
            # 某些提交可能是空或不完整，跳过
            continue
        except Exception as e:
            # 其它异常不影响整体
            print(f"[warn] {sha[:7]} 解析失败：{e}", file=sys.stderr)
            continue

    available_series: List[pd.Series] = []
    missing_items: List[str] = []
    for item, points in records_map.items():
        if not points:
            missing_items.append(item)
            continue
        df_item = (
            pd.DataFrame(points, columns=["ts", "price"])
            .drop_duplicates()
            .sort_values("ts")
            .set_index("ts")
        )
        series = df_item["price"]
        series.name = item
        available_series.append(series)

    if not available_series:
        msg = "未在任何提交中匹配到指定物品，请检查物品名（是否含成色/空格/括号）。"
        if missing_items:
            msg += " 未匹配到的物品：" + ", ".join(missing_items)
        print(msg, file=sys.stderr)
        sys.exit(2)

    if missing_items:
        print(
            "[warn] 以下物品在指定时间范围内未找到价格数据："
            + ", ".join(missing_items),
            file=sys.stderr,
        )

    df = pd.concat(available_series, axis=1).sort_index()

    if args.resample == "ffill":
        # 每 10 分钟重采样，限制前向填充的步数，避免跨长时间断档
        df = df.resample("10T").nearest()
        df = df.ffill(limit=6)  # 最多填 1 小时（6*10min），跨更久的缺口保持 NaN

    if args.csv:
        df.reset_index().to_csv(args.csv, index=False, encoding="utf-8-sig")
        print(f"已导出 CSV：{args.csv}")

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
        print("[warn] 未找到可用中文字体，图表中文字可能显示为方块，请安装 Noto Sans CJK、SimHei 等字体。", file=sys.stderr)

    # 绘图
    plt.figure(figsize=(11, 4.5))
    for column in df.columns:
        base_name = str(column)
        multiplier = bundle_multipliers.get(base_name, 1)
        display_name = base_name
        if multiplier > 1:
            display_name = f"{base_name} (x{multiplier})"
        label = display_name if font_family else ascii_fallback(display_name)
        plt.plot(df.index, df[column], lw=1, label=label)

    raw_title_items = []
    for col in df.columns:
        base_name = str(col)
        multiplier = bundle_multipliers.get(base_name, 1)
        if multiplier > 1:
            raw_title_items.append(f"{base_name}×{multiplier}")
        else:
            raw_title_items.append(base_name)
    if font_family:
        title_source = "、".join(raw_title_items)
        title_text = f"{title_source} 价格变化"
    else:
        title_source = ", ".join(ascii_fallback(item) for item in raw_title_items)
        title_text = f"{title_source} price trends"

    plt.title(title_text, fontproperties=None)
    plt.xlabel("时间" if font_family else "Time")
    plt.ylabel("价格" if font_family else "Price")
    plt.grid(True, alpha=0.3)
    plt.legend(loc="best")
    plt.tight_layout()
    plt.savefig(args.out, dpi=160)
    print(f"已输出图片：{args.out}")

if __name__ == "__main__":
    main()
