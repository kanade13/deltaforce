from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
from dataclasses import dataclass

import pandas as pd

from .coffee_ammo_linkage import (
    DEFAULT_AMMO_NAMES,
)


@dataclass(frozen=True)
class ExperimentSpec:
    name: str
    freq: str
    ffill_limit: int
    max_lag: str
    rolling_window: str
    rolling_min_periods: str
    max_granger_lag: str


SPECS: tuple[ExperimentSpec, ...] = (
    ExperimentSpec(
        name="g1_24h",
        freq="1H",
        ffill_limit=1,
        max_lag="24h",
        rolling_window="24h",
        rolling_min_periods="18h",
        max_granger_lag="24h",
    ),
    ExperimentSpec(
        name="g2_2d",
        freq="1H",
        ffill_limit=1,
        max_lag="2D",
        rolling_window="2D",
        rolling_min_periods="36h",
        max_granger_lag="2D",
    ),
    ExperimentSpec(
        name="g3_3d",
        freq="1H",
        ffill_limit=1,
        max_lag="3D",
        rolling_window="3D",
        rolling_min_periods="2D",
        max_granger_lag="3D",
    ),
    ExperimentSpec(
        name="g4_5d_granger3d",
        freq="1H",
        ffill_limit=1,
        max_lag="5D",
        rolling_window="5D",
        rolling_min_periods="3D",
        max_granger_lag="3D",
    ),
    ExperimentSpec(
        name="g5_7d_ffill0_granger3d",
        freq="1H",
        ffill_limit=0,
        max_lag="7D",
        rolling_window="7D",
        rolling_min_periods="5D",
        max_granger_lag="3D",
    ),
    ExperimentSpec(
        name="g6_7d_ffill3_granger3d",
        freq="1H",
        ffill_limit=3,
        max_lag="7D",
        rolling_window="7D",
        rolling_min_periods="5D",
        max_granger_lag="3D",
    ),
    ExperimentSpec(
        name="g7_freq2h_7d_granger3d",
        freq="2H",
        ffill_limit=1,
        max_lag="7D",
        rolling_window="7D",
        rolling_min_periods="5D",
        max_granger_lag="3D",
    ),
    ExperimentSpec(
        name="g8_freq6h_14d_granger3d",
        freq="6H",
        ffill_limit=1,
        max_lag="14D",
        rolling_window="14D",
        rolling_min_periods="10D",
        max_granger_lag="3D",
    ),
)


def _prepare_wide(raw: pd.DataFrame, *, freq: str, ffill_limit: int) -> pd.DataFrame:
    wide = raw.resample(freq).last()
    if ffill_limit > 0:
        wide = wide.ffill(limit=ffill_limit)
    elif ffill_limit < 0:
        wide = wide.ffill()
    return wide


def main() -> None:
    p = argparse.ArgumentParser(description="Run a grid of coffee-ammo experiments.")
    p.add_argument(
        "--repo",
        type=Path,
        default=Path("DeltaForcePrice"),
        help="Git repo path that contains price.json history.",
    )
    p.add_argument(
        "--coffee",
        default="盒装挂耳咖啡",
        help="Coffee item name (used to filter out from --item/--ammo list).",
    )
    p.add_argument("--since", default="2025-09-22", help="Start date (YYYY-MM-DD).")
    p.add_argument("--until", default="2025-11-09", help="End date (YYYY-MM-DD).")
    p.add_argument(
        "--out-root",
        type=Path,
        default=Path("study_outputs/coffee_ammo_grid_0922_1109"),
        help="Directory to write all experiment outputs.",
    )
    p.add_argument(
        "--fuzzy",
        action="store_true",
        help="Use substring match instead of exact item name match.",
    )
    p.add_argument(
        "--ammo",
        action="append",
        default=[],
        help="Ammo item name (repeatable). Defaults to built-in list.",
    )
    p.add_argument(
        "--item",
        action="append",
        default=[],
        help="Alias of --ammo; accepts a list copied from other scripts.",
    )
    args = p.parse_args()

    requested = [*args.ammo, *args.item]
    if requested:
        ammo_names = [name for name in requested if name != args.coffee]
    else:
        ammo_names = list(DEFAULT_AMMO_NAMES)

    args.out_root.mkdir(parents=True, exist_ok=True)

    summary_rows: list[dict[str, object]] = []
    failures: list[dict[str, object]] = []

    for spec in SPECS:
        out_dir = args.out_root / spec.name
        cmd = [
            sys.executable,
            "-m",
            "study.coffee_ammo_linkage",
            "--repo",
            str(args.repo),
            "--since",
            args.since,
            "--until",
            args.until,
            "--freq",
            spec.freq,
            "--ffill-limit",
            str(spec.ffill_limit),
            "--max-lag",
            spec.max_lag,
            "--rolling-window-duration",
            spec.rolling_window,
            "--rolling-min-periods-duration",
            spec.rolling_min_periods,
            "--max-granger-lag-duration",
            spec.max_granger_lag,
            "--out-dir",
            str(out_dir),
        ]
        if args.fuzzy:
            cmd.append("--fuzzy")
        for ammo in ammo_names:
            cmd.extend(["--ammo", ammo])
        try:
            subprocess.run(cmd, check=True, capture_output=True, text=True, encoding="utf-8")
        except subprocess.CalledProcessError as e:
            failures.append(
                {
                    "experiment": spec.name,
                    "returncode": e.returncode,
                    "stdout": (e.stdout or "")[-2000:],
                    "stderr": (e.stderr or "")[-2000:],
                }
            )
            continue

        summary_path = out_dir / "lag_and_granger_summary.csv"
        if summary_path.exists():
            df = pd.read_csv(summary_path)
            df.insert(0, "experiment", spec.name)
            df.insert(1, "freq", spec.freq)
            df.insert(2, "ffill_limit", spec.ffill_limit)
            df.insert(3, "max_lag", spec.max_lag)
            df.insert(4, "rolling_window", spec.rolling_window)
            df.insert(5, "rolling_min_periods", spec.rolling_min_periods)
            df.insert(6, "max_granger_lag", spec.max_granger_lag)
            summary_rows.extend(df.to_dict(orient="records"))

    if summary_rows:
        pd.DataFrame(summary_rows).to_csv(args.out_root / "grid_summary.csv", index=False)
    pd.DataFrame(failures).to_csv(args.out_root / "grid_failures.csv", index=False)


if __name__ == "__main__":
    main()
