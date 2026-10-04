"""
Reshape mapping/liquidity_mapping.csv (wide, one row per balance-sheet line, all ratio
roles as columns) into mapping/liquidity_mapping_long.csv (tidy, one row per
line_id x ratio x category) -- easier to filter/join in SQL or load straight into Power BI
as a lookup/dimension table.

Kept as a *derived* export, not a second source of truth: the wide file in
liquidity_mapping.csv stays canonical (it's the one that's been reconciled to the
FDIC-reported totals); this script just reshapes it.
"""
import csv

SRC = "mapping/liquidity_mapping.csv"
WIDE_DATA = "data/processed/jpm_628_wide.csv"
OUT = "mapping/liquidity_mapping_long.csv"

rows = list(csv.DictReader(open(SRC, encoding="utf-8")))
latest = list(csv.DictReader(open(WIDE_DATA, encoding="utf-8")))[-1]  # most recent quarter


def num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def val(expr):
    env = {k: (float(v) if v not in ("", None) else 0.0) for k, v in latest.items() if k != "report_period"}
    env["min"] = min
    return eval(expr, {"__builtins__": {}}, env)


long_rows = []
for r in rows:
    base = dict(
        line_id=r["line_id"],
        side=r["side"],
        group=r["group"],
        definition=r["definition"],
        description=r["description"],
        latest_value_20260630=round(val(r["definition"]), 0),
        in_balance_sum=r["in_balance_sum"],
        confidence=r["confidence"],
        rationale=r["rationale"],
        source=r["source"],
    )
    emitted = False

    hl = r["hqla_level"].strip()
    if hl:
        hc = num(r["hqla_haircut"]) or 0.0
        long_rows.append({**base, "ratio": "LCR", "category": "HQLA", "subcategory": hl,
                           "factor_pct": round((1 - hc) * 100, 2)})
        emitted = True

    for col, ratio, category in [
        ("lcr_outflow", "LCR", "Outflow"),
        ("lcr_inflow", "LCR", "Inflow"),
        ("nsfr_asf", "NSFR", "ASF"),
        ("nsfr_rsf", "NSFR", "RSF"),
    ]:
        v = num(r[col])
        if v is not None:
            long_rows.append({**base, "ratio": ratio, "category": category, "subcategory": "",
                               "factor_pct": round(v * 100, 2)})
            emitted = True

    if not emitted:
        # balance-sheet-only line (e.g. contra-asset like A_ALLOW): no ratio role of its own,
        # keep it visible in the long file rather than silently dropping it
        long_rows.append({**base, "ratio": "BalanceSheet", "category": "Memo/contra", "subcategory": "",
                           "factor_pct": ""})

FIELDS = ["line_id", "side", "group", "ratio", "category", "subcategory", "factor_pct",
          "definition", "latest_value_20260630", "in_balance_sum", "confidence",
          "description", "rationale", "source"]
with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    for lr in long_rows:
        w.writerow(lr)

print(f"Wrote {OUT}: {len(long_rows)} rows from {len(rows)} wide lines")
