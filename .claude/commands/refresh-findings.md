---
description: Refresh the "Early Signals" numbers in the portfolio write-up from the latest pipeline data
---

Refresh the portfolio write-up's data-driven findings using the freshest data in `ANALYTICS_PROD.FCT_JOB_POSTINGS`.

1. Run `presentation/notebooks/generate_findings_snapshot.py` (activate `venv` first if needed — it needs `snowflake-connector-python`, `pandas`, `numpy`, `python-dotenv`). This writes a new dated snapshot to `presentation/notebooks/findings_snapshots/` and prints a diff against the most recent prior snapshot.
2. Read the new snapshot JSON and the printed diff. If nothing meaningful changed since last time, say so plainly rather than manufacturing a story.
3. If the user hasn't already pasted the current write-up text in this conversation, ask for it (or the relevant "Early Signals" section) — the write-up itself lives outside this repo, so there's no file to diff against directly.
4. Cross-reference each specific claim/number in the write-up's "Early Signals" section against the new snapshot. For each one that moved meaningfully:
   - Quote the old sentence
   - Propose the updated sentence with the new number(s)
   - Note briefly why it matters if the story itself changed (e.g. a role that was an outlier no longer is, or a new outlier emerged) — not just that a percentage ticked up or down
5. Flag anything that's genuinely new or surprising in the diff even if the current write-up doesn't mention it yet (e.g. a stat that's now stable enough to be worth a claim, or a prior claim that no longer holds at all).
6. If `presentation/notebooks/findings.ipynb` needs deeper investigation for something odd in the diff (not just a number update), use it interactively via `findings_lib.py` rather than guessing.

Do not edit the write-up anywhere — it isn't part of this repo. Output the proposed edits directly in the response for the user to paste into their site themselves.
