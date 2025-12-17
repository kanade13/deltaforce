from __future__ import annotations

import argparse
import json
import os
import subprocess
import warnings
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

os.environ.setdefault("MKL_THREADING_LAYER", "GNU")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr
from statsmodels.tsa.stattools import grangercausalitytests


COFFEE_NAME = "盒装挂耳咖啡"
DEFAULT_AMMO_NAMES = (
    "5.56x45mm M995",
    "6.8x51mm Hybrid",
    "7.62x39mm AP",
    "7.62x51mm M62",
    "7.62x54R BT",
    "9x19mm PBP",
    "9x39mm BP",
)


@dataclass(frozen=True)
class StudyConfig:
    repo: Path | None
    data_path: Path
    out_dir: Path
    since: str | None
    until: str | None
    fuzzy: bool
    freq: str
    ffill_limit: int
    rolling_window: int
    rolling_min_periods: int
    max_lag_intervals: int
    max_granger_lag: int


def _intervals_from_duration(*, duration: str, freq: str) -> int:
    total = pd.Timedelta(duration)
    step = pd.Timedelta(freq)
    if total <= pd.Timedelta(0):
        raise ValueError(f"duration must be positive, got {duration!r}")
    if step <= pd.Timedelta(0):
        raise ValueError(f"freq must be positive, got {freq!r}")

    ratio = total / step
    intervals = int(round(float(ratio)))
    if intervals <= 0:
        raise ValueError(
            f"duration {duration!r} is smaller than freq {freq!r}; got {intervals} intervals"
        )
    if abs(float(ratio) - float(intervals)) > 1e-9:
        raise ValueError(
            f"duration {duration!r} is not an integer multiple of freq {freq!r} "
            f"(ratio={float(ratio)}); please adjust either one"
        )
    return intervals


def _run_git(repo: Path, args: list[str]) -> str:
    cmd = ["git", "-C", str(repo), *args]
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if res.returncode != 0:
        raise RuntimeError(f"git failed: {' '.join(cmd)}\n{res.stderr.strip()}")
    return res.stdout


def _list_price_json_commits(
    repo: Path, *, since: str | None, until: str | None
) -> list[tuple[str, datetime]]:
    args = ["log", "--reverse", "--format=%H|%cI"]
    if since:
        args.insert(1, f"--since={since}")
    if until:
        args.insert(1, f"--until={until}")
    args += ["--", "price.json"]

    out = _run_git(repo, args)
    commits: list[tuple[str, datetime]] = []
    for line in out.splitlines():
        if not line.strip():
            continue
        sha, iso = line.split("|", 1)
        t = pd.to_datetime(iso, utc=True).to_pydatetime()
        commits.append((sha, t))
    return commits


def _read_price_json_at_commit(repo: Path, sha: str) -> list[dict]:
    out = _run_git(repo, ["show", f"{sha}:price.json"])
    data = json.loads(out)
    if not isinstance(data, list):
        raise ValueError(f"price.json at {sha} is not a list")
    return data


def _pick_price(items: list[dict], query: str, *, fuzzy: bool) -> float | None:
    if not fuzzy:
        for it in items:
            if it.get("name") == query:
                price = it.get("price")
                return float(price) if price is not None else None
        return None

    for it in items:
        name = str(it.get("name", ""))
        if query in name:
            price = it.get("price")
            return float(price) if price is not None else None
    return None


def _load_price_records(path: Path) -> pd.DataFrame:
    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)
    df = pd.DataFrame(raw)
    expected = {"is_get_time", "name", "price"}
    missing = expected - set(df.columns)
    if missing:
        raise ValueError(f"{path} missing fields: {sorted(missing)}")

    df = df.loc[:, ["is_get_time", "name", "price"]].copy()
    df["time"] = pd.to_datetime(df["is_get_time"], unit="s", utc=True)
    df["price"] = pd.to_numeric(df["price"], errors="coerce")
    df = df.dropna(subset=["time", "name", "price"])
    df = df.loc[df["price"] > 0].copy()
    return df.loc[:, ["time", "name", "price"]]


def _build_frame_from_git_history(
    *,
    repo: Path,
    items: list[str],
    since: str | None,
    until: str | None,
    fuzzy: bool,
) -> pd.DataFrame:
    commits = _list_price_json_commits(repo, since=since, until=until)
    if not commits:
        raise ValueError("No commits found for price.json in the given range.")

    rows: list[dict[str, float | datetime]] = []
    want = set(items)
    for sha, t in commits:
        snapshot = _read_price_json_at_commit(repo, sha)
        row: dict[str, float | datetime] = {"time": t}
        if fuzzy:
            for item in items:
                row[item] = _pick_price(snapshot, item, fuzzy=True)
        else:
            for it in snapshot:
                name = it.get("name")
                if name in want:
                    price = it.get("price")
                    row[str(name)] = float(price) if price is not None else None
            for item in items:
                row.setdefault(item, None)
        rows.append(row)

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    df = df.set_index("time").sort_index()
    return df


def _build_aligned_frame(
    records: pd.DataFrame,
    items: Iterable[str],
    *,
    freq: str,
    ffill_limit: int,
) -> pd.DataFrame:
    items = list(items)
    df = records.loc[records["name"].isin(items)].copy()
    if df.empty:
        raise ValueError("No matching items found in data.")

    df["time"] = df["time"].dt.round(freq)
    df = (
        df.sort_values(["time"])
        .groupby(["time", "name"], as_index=False)["price"]
        .last()
    )
    wide = df.pivot(index="time", columns="name", values="price").sort_index()

    full_index = pd.date_range(wide.index.min(), wide.index.max(), freq=freq, tz="UTC")
    wide = wide.reindex(full_index)
    if ffill_limit > 0:
        wide = wide.ffill(limit=ffill_limit)
    elif ffill_limit < 0:
        wide = wide.ffill()
    return wide


def _pairwise_corr(base: pd.Series, other: pd.Series) -> dict[str, float]:
    aligned = pd.concat([base, other], axis=1).dropna()
    if len(aligned) < 3:
        return {
            "n": float(len(aligned)),
            "pearson_r": np.nan,
            "pearson_p": np.nan,
            "spearman_r": np.nan,
            "spearman_p": np.nan,
        }
    x = aligned.iloc[:, 0].to_numpy()
    y = aligned.iloc[:, 1].to_numpy()
    pearson_r, pearson_p = pearsonr(x, y)
    spearman_r, spearman_p = spearmanr(x, y)
    return {
        "n": float(len(aligned)),
        "pearson_r": float(pearson_r),
        "pearson_p": float(pearson_p),
        "spearman_r": float(spearman_r),
        "spearman_p": float(spearman_p),
    }


def _rolling_corr(
    base: pd.Series, other: pd.Series, *, window: int, min_periods: int
) -> pd.Series:
    return base.rolling(window=window, min_periods=min_periods).corr(other)


def _cross_correlation(
    base: pd.Series,
    other: pd.Series,
    *,
    max_lag_intervals: int,
    interval: pd.Timedelta,
) -> pd.DataFrame:
    lags = range(-max_lag_intervals, max_lag_intervals + 1)
    rows: list[dict[str, float]] = []
    for lag in lags:
        shifted = other.shift(-lag)
        aligned = pd.concat([base, shifted], axis=1).dropna()
        corr = aligned.iloc[:, 0].corr(aligned.iloc[:, 1]) if len(aligned) >= 3 else np.nan
        rows.append(
            {
                "lag_intervals": float(lag),
                "corr": float(corr) if corr == corr else np.nan,
                "n": float(len(aligned)),
            }
        )
    out = pd.DataFrame(rows)
    seconds_per_interval = float(interval.total_seconds())
    out["lag_seconds"] = out["lag_intervals"] * seconds_per_interval
    out["lag_minutes"] = out["lag_seconds"] / 60.0
    out["lag_hours"] = out["lag_seconds"] / 3600.0
    return out


def _prepare_for_granger(df_pair: pd.DataFrame) -> pd.DataFrame:
    df_pair = df_pair.dropna().copy()
    if df_pair.empty:
        return df_pair
    if (df_pair <= 0).any().any():
        return df_pair.diff().dropna()
    return np.log(df_pair).diff().dropna()


def _granger_pvalues(
    *,
    target: pd.Series,
    cause: pd.Series,
    maxlag: int,
) -> pd.DataFrame:
    data = pd.concat([target, cause], axis=1)
    data.columns = ["target", "cause"]
    data = _prepare_for_granger(data)
    if len(data) < (maxlag + 3):
        return pd.DataFrame(columns=["lag", "ssr_ftest_pvalue", "ssr_ftest_stat"])

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=FutureWarning,
            message="verbose is deprecated*",
        )
        results = grangercausalitytests(
            data[["target", "cause"]],
            maxlag=maxlag,
            verbose=False,
        )
    rows: list[dict[str, float]] = []
    for lag, detail in results.items():
        stat, pvalue, _, _ = detail[0]["ssr_ftest"]
        rows.append({"lag": float(lag), "ssr_ftest_pvalue": float(pvalue), "ssr_ftest_stat": float(stat)})
    return pd.DataFrame(rows).sort_values("lag")


def _plot_indexed_trends(wide: pd.DataFrame, *, out_path: Path, title: str) -> None:
    df = wide.dropna(how="all").copy()
    indexed = pd.DataFrame(index=df.index)
    for col in df.columns:
        s = df[col].dropna()
        if s.empty:
            indexed[col] = np.nan
            continue
        indexed[col] = df[col] / float(s.iloc[0]) * 100.0

    fig, ax = plt.subplots(figsize=(14, 6), constrained_layout=True)
    for col in indexed.columns:
        label = "coffee" if col == COFFEE_NAME else col
        ax.plot(indexed.index, indexed[col], label=label, linewidth=1.2)
    ax.set_title(title)
    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("Indexed Price (first=100)")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _plot_rolling_corr(
    rolling: pd.DataFrame, *, out_path: Path, title: str, threshold: float = 0.0
) -> None:
    fig, ax = plt.subplots(figsize=(14, 5), constrained_layout=True)
    for col in rolling.columns:
        label = "coffee" if col == COFFEE_NAME else col
        ax.plot(rolling.index, rolling[col], label=label, linewidth=1.1)
    if threshold:
        ax.axhline(threshold, color="black", linewidth=0.8, alpha=0.5)
        ax.axhline(-threshold, color="black", linewidth=0.8, alpha=0.5)
    ax.set_title(title)
    ax.set_xlabel("Time (UTC)")
    ax.set_ylabel("Rolling Correlation")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _plot_cross_corr(
    cross: dict[str, pd.DataFrame], *, out_path: Path, title: str
) -> None:
    fig, ax = plt.subplots(figsize=(14, 5), constrained_layout=True)
    for name, df in cross.items():
        ax.plot(df["lag_hours"], df["corr"], label=name, linewidth=1.1)
    ax.axvline(0.0, color="black", linewidth=0.8, alpha=0.5)
    ax.set_title(title)
    ax.set_xlabel("Lag (hours); + means coffee leads ammo")
    ax.set_ylabel("Pearson Corr")
    ax.grid(True, alpha=0.3)
    ax.legend(loc="best", fontsize=9)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def _plot_granger(
    granger: pd.DataFrame, *, out_path: Path, title: str, alpha: float = 0.05
) -> None:
    fig, ax = plt.subplots(figsize=(10, 4), constrained_layout=True)
    if not granger.empty:
        ax.plot(granger["lag"], granger["ssr_ftest_pvalue"], marker="o", linewidth=1.2)
    ax.axhline(alpha, color="red", linestyle="--", linewidth=1.0, alpha=0.8)
    ax.set_title(title)
    ax.set_xlabel("Lag (intervals)")
    ax.set_ylabel("Granger p-value (ssr_ftest)")
    ax.set_ylim(0.0, 1.0)
    ax.grid(True, alpha=0.3)
    fig.savefig(out_path, dpi=160)
    plt.close(fig)


def run_study_from_wide(cfg: StudyConfig, *, wide: pd.DataFrame, ammo_names: Iterable[str]) -> None:
    cfg.out_dir.mkdir(parents=True, exist_ok=True)

    items = [COFFEE_NAME, *list(ammo_names)]
    interval = pd.Timedelta(cfg.freq)
    wide.to_csv(cfg.out_dir / "aligned_prices.csv", index_label="time_utc")

    coffee = wide[COFFEE_NAME] if COFFEE_NAME in wide.columns else pd.Series(dtype=float)
    correlation_rows: list[dict[str, float | str]] = []
    rolling_corr_df = pd.DataFrame(index=wide.index)
    cross_corr: dict[str, pd.DataFrame] = {}
    granger_rows: list[dict[str, float | str]] = []

    for ammo in ammo_names:
        if ammo not in wide.columns:
            continue
        series = wide[ammo]

        corr = _pairwise_corr(coffee, series)
        correlation_rows.append({"item": ammo, **corr})

        rolling_corr_df[ammo] = _rolling_corr(
            coffee,
            series,
            window=cfg.rolling_window,
            min_periods=cfg.rolling_min_periods,
        )

        max_lag = min(cfg.max_lag_intervals, max(1, len(wide) - 3))
        cross = _cross_correlation(
            coffee,
            series,
            max_lag_intervals=max_lag,
            interval=interval,
        )
        cross_corr[ammo] = cross
        cross.to_csv(cfg.out_dir / f"cross_corr__{ammo}.csv", index=False)

        best_pos = (
            cross.loc[cross["corr"].idxmax()] if cross["corr"].notna().any() else None
        )
        best_abs = (
            cross.loc[cross["corr"].abs().idxmax()] if cross["corr"].notna().any() else None
        )
        cross_positive = cross.loc[cross["lag_hours"] >= 0].copy()
        best_coffee_leads = (
            cross_positive.loc[cross_positive["corr"].idxmax()]
            if cross_positive["corr"].notna().any()
            else None
        )
        cross_negative = cross.loc[cross["lag_hours"] <= 0].copy()
        best_ammo_leads = (
            cross_negative.loc[cross_negative["corr"].idxmax()]
            if cross_negative["corr"].notna().any()
            else None
        )

        granger_coffee_to_ammo = _granger_pvalues(
            target=series,
            cause=coffee,
            maxlag=cfg.max_granger_lag,
        )
        granger_ammo_to_coffee = _granger_pvalues(
            target=coffee,
            cause=series,
            maxlag=cfg.max_granger_lag,
        )
        granger_coffee_to_ammo.to_csv(
            cfg.out_dir / f"granger__coffee_to__{ammo}.csv", index=False
        )
        granger_ammo_to_coffee.to_csv(
            cfg.out_dir / f"granger__{ammo}_to__coffee.csv", index=False
        )

        def summarize_granger(df: pd.DataFrame) -> tuple[float, float]:
            if df.empty or df["ssr_ftest_pvalue"].isna().all():
                return (np.nan, np.nan)
            best = df.loc[df["ssr_ftest_pvalue"].idxmin()]
            return (float(best["lag"]), float(best["ssr_ftest_pvalue"]))

        lag_ca, p_ca = summarize_granger(granger_coffee_to_ammo)
        lag_ac, p_ac = summarize_granger(granger_ammo_to_coffee)

        granger_rows.append(
            {
                "item": ammo,
                "coffee_to_ammo_best_lag": lag_ca,
                "coffee_to_ammo_best_p": p_ca,
                "ammo_to_coffee_best_lag": lag_ac,
                "ammo_to_coffee_best_p": p_ac,
                "cross_corr_best_lag_hours": float(best_pos["lag_hours"])
                if best_pos is not None
                else np.nan,
                "cross_corr_best_corr": float(best_pos["corr"]) if best_pos is not None else np.nan,
                "cross_corr_best_abs_lag_hours": float(best_abs["lag_hours"])
                if best_abs is not None
                else np.nan,
                "cross_corr_best_abs_corr": float(best_abs["corr"]) if best_abs is not None else np.nan,
                "cross_corr_best_coffee_leads_lag_hours": float(best_coffee_leads["lag_hours"])
                if best_coffee_leads is not None
                else np.nan,
                "cross_corr_best_coffee_leads_corr": float(best_coffee_leads["corr"])
                if best_coffee_leads is not None
                else np.nan,
                "cross_corr_best_ammo_leads_lag_hours": float(best_ammo_leads["lag_hours"])
                if best_ammo_leads is not None
                else np.nan,
                "cross_corr_best_ammo_leads_corr": float(best_ammo_leads["corr"])
                if best_ammo_leads is not None
                else np.nan,
            }
        )

        _plot_granger(
            granger_coffee_to_ammo,
            out_path=cfg.out_dir / f"granger__coffee_to__{ammo}.png",
            title=f"Granger (coffee -> {ammo}) on log-diff",
        )

    correlation_df = pd.DataFrame(correlation_rows).sort_values("item")
    correlation_df.to_csv(cfg.out_dir / "correlations.csv", index=False)

    rolling_corr_df.to_csv(cfg.out_dir / "rolling_correlations.csv", index_label="time_utc")

    granger_df = pd.DataFrame(granger_rows).sort_values("item")
    granger_df.to_csv(cfg.out_dir / "lag_and_granger_summary.csv", index=False)

    _plot_indexed_trends(
        wide.loc[:, [c for c in items if c in wide.columns]],
        out_path=cfg.out_dir / "indexed_trends.png",
        title="Coffee vs High-grade Ammo Indexed Trends (first=100)",
    )

    _plot_rolling_corr(
        rolling_corr_df,
        out_path=cfg.out_dir / "rolling_corr.png",
        title=f"Rolling Correlation vs coffee (window={cfg.rolling_window})",
    )

    _plot_cross_corr(
        cross_corr,
        out_path=cfg.out_dir / "cross_corr.png",
        title="Cross-correlation (coffee leads when lag > 0)",
    )

    report_lines = [
        "# 盒装挂耳咖啡与高级弹药价格联动分析结果",
        "",
        f"- Git 仓库：`{cfg.repo}`" if cfg.repo is not None else f"- 数据文件：`{cfg.data_path}`",
        f"- 时间范围：`{cfg.since}` ~ `{cfg.until}`" if cfg.repo is not None else "- 时间范围：N/A",
        f"- 时间频率：`{cfg.freq}`，缺失填充：`ffill(limit={cfg.ffill_limit})`",
        f"- 交叉相关最大滞后：`±{cfg.max_lag_intervals}` 个间隔（每间隔 `{cfg.freq}`）",
        f"- 格兰杰检验最大阶：`{cfg.max_granger_lag}`（在 log-diff 上）",
        "",
        "## 输出文件",
        "",
        "- `aligned_prices.csv`：对齐后的价格序列",
        "- `correlations.csv`：整体 Pearson/Spearman 相关",
        "- `rolling_correlations.csv`：滚动相关（每列一条弹药）",
        "- `cross_corr.png` / `cross_corr__<item>.csv`：交叉相关函数图与明细",
        "- `lag_and_granger_summary.csv`：交叉相关峰值与格兰杰检验摘要",
        "- `granger__coffee_to__<item>.png/.csv`：咖啡→弹药的格兰杰检验",
        "",
        "## 关键图",
        "",
        "- `indexed_trends.png`",
        "- `rolling_corr.png`",
        "- `cross_corr.png`",
    ]
    (cfg.out_dir / "report.md").write_text("\n".join(report_lines) + "\n", encoding="utf-8")


def run_study(cfg: StudyConfig, *, ammo_names: Iterable[str]) -> None:
    items = [COFFEE_NAME, *list(ammo_names)]
    if cfg.repo is not None:
        wide = _build_frame_from_git_history(
            repo=cfg.repo,
            items=items,
            since=cfg.since,
            until=cfg.until,
            fuzzy=cfg.fuzzy,
        )
        wide = wide.resample(cfg.freq).last()
        if cfg.ffill_limit > 0:
            wide = wide.ffill(limit=cfg.ffill_limit)
        elif cfg.ffill_limit < 0:
            wide = wide.ffill()
    else:
        records = _load_price_records(cfg.data_path)
        wide = _build_aligned_frame(
            records,
            items,
            freq=cfg.freq,
            ffill_limit=cfg.ffill_limit,
        )

    run_study_from_wide(cfg, wide=wide, ammo_names=ammo_names)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Study linkage between coffee and high-grade ammo prices.",
    )
    p.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Git repo path that contains price.json history (preferred).",
    )
    p.add_argument("--since", default="2025-08-20", help="Start date (YYYY-MM-DD).")
    p.add_argument("--until", default="2025-12-15", help="End date (YYYY-MM-DD).")
    p.add_argument(
        "--fuzzy",
        action="store_true",
        help="Use substring match instead of exact item name match.",
    )
    p.add_argument(
        "--data",
        type=Path,
        default=Path("DeltaForcePrice/price.json"),
        help="Path to price.json (list of {is_get_time,name,price}).",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=Path("study_outputs/coffee_ammo_linkage"),
        help="Directory to write results.",
    )
    p.add_argument("--freq", default="10min", help="Align frequency (e.g. 10min).")
    p.add_argument(
        "--ffill-limit",
        type=int,
        default=6,
        help="Forward-fill limit in intervals; use 0 to disable, -1 for unlimited.",
    )
    p.add_argument(
        "--rolling-window",
        type=int,
        default=144,
        help="Rolling window length in aligned intervals (default: 144 = 1 day).",
    )
    p.add_argument(
        "--rolling-window-duration",
        default=None,
        help="Rolling window as a duration (e.g. 7D, 168h); overrides --rolling-window.",
    )
    p.add_argument(
        "--rolling-min-periods",
        type=int,
        default=96,
        help="Min periods for rolling correlation.",
    )
    p.add_argument(
        "--rolling-min-periods-duration",
        default=None,
        help="Rolling min periods as a duration (e.g. 5D, 120h); overrides --rolling-min-periods.",
    )
    p.add_argument(
        "--max-lag-intervals",
        type=int,
        default=144,
        help="Cross-correlation lag range in aligned intervals.",
    )
    p.add_argument(
        "--max-lag",
        default=None,
        help="Cross-correlation lag range as a duration (e.g. 4D, 96h); overrides --max-lag-intervals.",
    )
    p.add_argument(
        "--max-granger-lag",
        type=int,
        default=12,
        help="Max lag for Granger causality tests.",
    )
    p.add_argument(
        "--max-granger-lag-duration",
        default=None,
        help="Max lag for Granger as a duration (e.g. 7D, 168h); overrides --max-granger-lag.",
    )
    p.add_argument(
        "--ammo",
        action="append",
        default=[],
        help="Ammo item name (repeatable). Defaults to a built-in list.",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    ammo = args.ammo or list(DEFAULT_AMMO_NAMES)

    rolling_window = args.rolling_window
    if args.rolling_window_duration is not None:
        rolling_window = _intervals_from_duration(
            duration=args.rolling_window_duration, freq=args.freq
        )

    rolling_min_periods = args.rolling_min_periods
    if args.rolling_min_periods_duration is not None:
        rolling_min_periods = _intervals_from_duration(
            duration=args.rolling_min_periods_duration, freq=args.freq
        )

    max_lag_intervals = args.max_lag_intervals
    if args.max_lag is not None:
        max_lag_intervals = _intervals_from_duration(duration=args.max_lag, freq=args.freq)

    max_granger_lag = args.max_granger_lag
    if args.max_granger_lag_duration is not None:
        max_granger_lag = _intervals_from_duration(
            duration=args.max_granger_lag_duration, freq=args.freq
        )

    cfg = StudyConfig(
        repo=args.repo if args.repo is not None else None,
        data_path=args.data,
        out_dir=args.out_dir,
        since=args.since,
        until=args.until,
        fuzzy=args.fuzzy,
        freq=args.freq,
        ffill_limit=args.ffill_limit,
        rolling_window=rolling_window,
        rolling_min_periods=rolling_min_periods,
        max_lag_intervals=max_lag_intervals,
        max_granger_lag=max_granger_lag,
    )
    run_study(cfg, ammo_names=ammo)


if __name__ == "__main__":
    main()
