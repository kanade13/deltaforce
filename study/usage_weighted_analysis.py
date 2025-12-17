from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from pathlib import Path

os.environ.setdefault("MKL_THREADING_LAYER", "GNU")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")

import numpy as np
import pandas as pd


_USAGE_HEADER_RE = re.compile(r"^#\s*枪械登场率与子弹\s*$")
_PERCENT_RE = re.compile(r"(?P<val>\d+(?:\.\d+)?)\s*%")


@dataclass(frozen=True)
class UsageRow:
    weapon: str
    usage_rate: float  # 0..1
    ammo: str


def _read_text_with_bom(path: Path) -> str:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return raw.decode("utf-16", errors="replace")
    if raw.count(b"\x00") > len(raw) // 10:
        return raw.decode("utf-16", errors="replace")
    return raw.decode("utf-8", errors="replace")


def _parse_weapon_usage_from_readme(readme_path: Path) -> pd.DataFrame:
    text = _read_text_with_bom(readme_path)
    lines = [ln.strip() for ln in text.splitlines()]

    start = None
    for i, ln in enumerate(lines):
        if _USAGE_HEADER_RE.match(ln):
            start = i + 1
            break
    if start is None:
        raise ValueError(f"Cannot find section header '# 枪械登场率与子弹' in {readme_path}")

    rows: list[UsageRow] = []
    for ln in lines[start:]:
        if not ln:
            continue
        if ln.startswith("#"):
            break
        if ln.startswith("枪械"):
            continue

        m = _PERCENT_RE.search(ln)
        if not m:
            continue
        usage_pct = float(m.group("val"))
        usage_rate = usage_pct / 100.0

        before = ln[: m.start()].strip()
        after = ln[m.end() :].strip()
        if not before or not after:
            continue

        # Format is expected: "<weapon> <pct>% <ammo name...>"
        rows.append(UsageRow(weapon=before, usage_rate=usage_rate, ammo=after))

    if not rows:
        raise ValueError(f"Found header but parsed no usage rows from {readme_path}")

    df = pd.DataFrame([r.__dict__ for r in rows])
    df = df.sort_values(["ammo", "weapon"]).reset_index(drop=True)
    return df


def _safe_corr(x: pd.Series, y: pd.Series) -> float:
    aligned = pd.concat([x, y], axis=1).dropna()
    if len(aligned) < 3:
        return float("nan")
    if aligned.iloc[:, 0].nunique(dropna=True) < 2:
        return float("nan")
    if aligned.iloc[:, 1].nunique(dropna=True) < 2:
        return float("nan")
    return float(aligned.iloc[:, 0].corr(aligned.iloc[:, 1]))


def _weighted_mean(values: pd.Series, weights: pd.Series) -> float:
    df = pd.concat([values, weights], axis=1).dropna()
    if df.empty:
        return float("nan")
    w = df.iloc[:, 1].to_numpy(dtype=float)
    v = df.iloc[:, 0].to_numpy(dtype=float)
    s = float(w.sum())
    if s <= 0:
        return float("nan")
    return float((v * w).sum() / s)


def analyze_grid(*, grid_root: Path, usage_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    grid_path = grid_root / "grid_summary.csv"
    if not grid_path.exists():
        raise FileNotFoundError(f"Missing {grid_path}")

    d = pd.read_csv(grid_path)
    for c in [
        "cross_corr_best_coffee_leads_lag_hours",
        "cross_corr_best_coffee_leads_corr",
        "coffee_to_ammo_best_p",
    ]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")

    d["max_lag_hours"] = d["max_lag"].map(lambda s: pd.Timedelta(s).total_seconds() / 3600)

    ammo_usage = (
        usage_df.groupby("ammo", as_index=False)["usage_rate"].sum().rename(columns={"ammo": "item"})
    )
    d = d.merge(ammo_usage, on="item", how="left")

    item_rows: list[dict[str, object]] = []
    for item, g in d.groupby("item"):
        item_rows.append(
            {
                "item": item,
                "usage_rate": float(g["usage_rate"].dropna().iloc[0]) if g["usage_rate"].notna().any() else np.nan,
                "n_experiments": int(g["experiment"].nunique()),
                "lag_mean_h": float(g["cross_corr_best_coffee_leads_lag_hours"].mean()),
                "lag_median_h": float(g["cross_corr_best_coffee_leads_lag_hours"].median()),
                "lag_std_h": float(g["cross_corr_best_coffee_leads_lag_hours"].std()),
                "corr_mean": float(g["cross_corr_best_coffee_leads_corr"].mean()),
                "corr_median": float(g["cross_corr_best_coffee_leads_corr"].median()),
                "share_peak_in_96_168h": float(
                    g["cross_corr_best_coffee_leads_lag_hours"].between(96, 168).mean()
                ),
                "share_granger_p_lt_0_05": float((g["coffee_to_ammo_best_p"] < 0.05).mean()),
                "corr_lag_vs_maxlag": _safe_corr(
                    g["cross_corr_best_coffee_leads_lag_hours"], g["max_lag_hours"]
                ),
            }
        )
    item_summary = pd.DataFrame(item_rows).sort_values(
        ["usage_rate", "item"], ascending=[False, True]
    )

    exp_rows: list[dict[str, object]] = []
    for exp, g in d.groupby("experiment"):
        exp_rows.append(
            {
                "experiment": exp,
                "freq": str(g["freq"].iloc[0]) if "freq" in g.columns else "",
                "max_lag": str(g["max_lag"].iloc[0]) if "max_lag" in g.columns else "",
                "n_items_total": int(g["item"].nunique()),
                "n_items_with_usage": int(g.loc[g["usage_rate"].notna(), "item"].nunique()),
                "usage_weighted_lag_mean_h": _weighted_mean(
                    g["cross_corr_best_coffee_leads_lag_hours"], g["usage_rate"]
                ),
                "usage_weighted_corr_mean": _weighted_mean(
                    g["cross_corr_best_coffee_leads_corr"], g["usage_rate"]
                ),
                "usage_weighted_share_peak_in_96_168h": _weighted_mean(
                    g["cross_corr_best_coffee_leads_lag_hours"].between(96, 168).astype(float),
                    g["usage_rate"],
                ),
            }
        )
    exp_summary = pd.DataFrame(exp_rows).sort_values("experiment")

    # Cross-sectional relationships (ammo-level)
    ammo_level = item_summary.dropna(subset=["usage_rate"]).copy()
    xsec = pd.DataFrame(
        [
            {
                "metric": "spearman(usage_rate, lag_median_h)",
                "value": float(ammo_level["usage_rate"].corr(ammo_level["lag_median_h"], method="spearman")),
                "n": int(len(ammo_level)),
            },
            {
                "metric": "spearman(usage_rate, corr_median)",
                "value": float(ammo_level["usage_rate"].corr(ammo_level["corr_median"], method="spearman")),
                "n": int(len(ammo_level)),
            },
            {
                "metric": "spearman(usage_rate, corr_lag_vs_maxlag)",
                "value": float(
                    ammo_level["usage_rate"].corr(ammo_level["corr_lag_vs_maxlag"], method="spearman")
                ),
                "n": int(len(ammo_level)),
            },
        ]
    )

    return item_summary, exp_summary, xsec


def main() -> None:
    p = argparse.ArgumentParser(
        description="Join weapon usage rates with grid experiments and compute usage-weighted summaries."
    )
    p.add_argument(
        "--readme",
        type=Path,
        default=Path("README.md"),
        help="README that contains the '# 枪械登场率与子弹' section (supports UTF-16 BOM).",
    )
    p.add_argument(
        "--grid-root",
        type=Path,
        action="append",
        required=True,
        help="Grid output root that contains grid_summary.csv (repeatable).",
    )
    args = p.parse_args()

    usage_df = _parse_weapon_usage_from_readme(args.readme)

    for grid_root in args.grid_root:
        item_summary, exp_summary, xsec = analyze_grid(grid_root=grid_root, usage_df=usage_df)
        out_dir = grid_root

        (out_dir / "usage_by_weapon.csv").write_text(
            usage_df.to_csv(index=False), encoding="utf-8"
        )
        item_summary.to_csv(out_dir / "usage_item_summary.csv", index=False)
        exp_summary.to_csv(out_dir / "usage_experiment_summary.csv", index=False)
        xsec.to_csv(out_dir / "usage_xsec_summary.csv", index=False)

        missing = item_summary.loc[item_summary["usage_rate"].isna(), "item"].tolist()

        md = [
            "# Usage-weighted analysis",
            "",
            f"- Grid root: `{grid_root}`",
            f"- README: `{args.readme}`",
            "",
            "## Weapon usage mapping (by weapon)",
            "",
            usage_df.to_markdown(index=False),
            "",
            "## Ammo-level summary (joined usage_rate by ammo)",
            "",
            item_summary.to_markdown(index=False),
            "",
            "## Experiment-level usage-weighted summary",
            "",
            exp_summary.to_markdown(index=False),
            "",
            "## Cross-sectional diagnostics",
            "",
            xsec.to_markdown(index=False),
        ]
        if missing:
            md += [
                "",
                "## Missing usage_rate for items",
                "",
                "- " + "\n- ".join(missing),
            ]

        (out_dir / "usage_analysis.md").write_text("\n".join(md) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
