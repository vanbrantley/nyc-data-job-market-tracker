#!/usr/bin/env python3
"""Compute the headline "Early Signals" metrics, snapshot them, and print what
changed since the last snapshot.

Usage:
    python presentation/notebooks/generate_findings_snapshot.py

Writes presentation/notebooks/findings_snapshots/<today>.json and diffs it
against the most recent prior snapshot in that directory.
"""
import json
import math
import sys
from datetime import date
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import findings_lib as lib

SNAPSHOT_DIR = Path(__file__).parent / "findings_snapshots"


def build_headline_metrics(df, salary_df):
    snapshot = lib.top_level_snapshot(df, salary_df)
    role_counts = lib.postings_by_role(df)
    consistency = lib.title_vs_archetype(df)
    sal_by_role, _ = lib.salary_by_role(df, salary_df)
    ai_overall, ai_by_role = lib.ai_acknowledgment(df)
    _, degree_pct = lib.degree_requirements(df)
    seniority = lib.seniority_mismatch(df)
    enc_overall, _ = lib.encourages_applicants(df)

    return {
        "run_date": date.today().isoformat(),
        "dataset": {
            "total_postings": snapshot["total_postings"],
            "unique_companies": snapshot["unique_companies"],
            "sources": snapshot["sources"],
            "date_min": snapshot["date_min"],
            "date_max": snapshot["date_max"],
            "last_ingested": snapshot["last_ingested"],
            "salary_disclosed_rate": snapshot["salary_disclosed_rate"],
        },
        "postings_by_role": role_counts.to_dict(),
        "title_self_consistency": {
            "overall_rate": consistency["overall_agree_rate"],
            "by_role": consistency["by_role_rate"].to_dict(),
        },
        "median_salary_by_role": sal_by_role["median"].to_dict(),
        "ai_acknowledgment": {
            "overall_rate": ai_overall["rate"],
            "by_role": ai_by_role["rate"].to_dict(),
        },
        "masters_degree_rate_by_role": (
            degree_pct["masters"].to_dict() if "masters" in degree_pct.columns else {}
        ),
        "listed_vs_inferred_seniority_pct": {
            listed: row.dropna().to_dict() for listed, row in seniority["pivot_pct"].iterrows()
        },
        "encourages_applicants_overall_rate": enc_overall["rate"],
    }


def _sanitize(obj):
    """Recursively convert numpy/pandas scalars to native JSON-safe values, NaN -> None."""
    if isinstance(obj, dict):
        return {k: _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if math.isnan(f) else round(f, 4)
    if isinstance(obj, np.bool_):
        return bool(obj)
    return obj


def diff_metrics(old: dict, new: dict, path: str = "") -> list:
    lines = []
    for k in sorted(set(old) | set(new)):
        p = f"{path}.{k}" if path else k
        ov, nv = old.get(k), new.get(k)
        if isinstance(ov, dict) or isinstance(nv, dict):
            lines.extend(diff_metrics(ov or {}, nv or {}, p))
        elif ov != nv:
            lines.append(f"  {p}: {ov} -> {nv}")
    return lines


def main():
    SNAPSHOT_DIR.mkdir(exist_ok=True)

    conn = lib.connect()
    df, salary_df, n_excluded = lib.load_mart(conn)
    metrics = _sanitize(build_headline_metrics(df, salary_df))

    prior_candidates = sorted(p for p in SNAPSHOT_DIR.glob("*.json") if p.stem != metrics["run_date"])
    prior_path = prior_candidates[-1] if prior_candidates else None

    today_path = SNAPSHOT_DIR / f"{metrics['run_date']}.json"
    today_path.write_text(json.dumps(metrics, indent=2))
    print(f"Snapshot written: {today_path}")
    print(f"({metrics['dataset']['total_postings']} postings analyzed, {n_excluded} excluded as no_match title)")

    if prior_path:
        prior = json.loads(prior_path.read_text())
        changes = diff_metrics(prior, metrics)
        print(f"\n=== Changed since {prior['run_date']} ===")
        print("\n".join(changes) if changes else "  (no headline metric changed)")
    else:
        print("\nNo prior snapshot found — this is the first one.")


if __name__ == "__main__":
    main()
