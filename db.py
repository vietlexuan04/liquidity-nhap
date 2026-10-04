"""
Build liquidity_risk.db (SQLite) from every CSV deliverable produced so far.
The CSVs in data/processed/ and mapping/ remain the source files -- this script is
re-runnable any time they change; it does not replace them, just aggregates them into
one file for SQL/Power BI (both can connect to a single .db file directly, no server).
"""
import csv
import os
import sqlite3

DB_PATH = "liquidity_risk.db"

TABLES = {
    "balance_sheet_wide": "data/processed/jpm_628_wide.csv",
    "mnemonic_labels": "data/processed/mnemonic_labels.csv",
    "liquidity_mapping": "mapping/liquidity_mapping.csv",
    "liquidity_mapping_long": "mapping/liquidity_mapping_long.csv",
    "nhnn_ratio_reference": "mapping/nhnn_ratio_reference.csv",
    "ratios_by_quarter": "data/processed/ratios_by_quarter.csv",
    "sensitivity_results": "data/processed/sensitivity_results.csv",
    "lcr_benchmark": "data/processed/lcr_benchmark.csv",
    "stress_scenarios_by_quarter": "data/processed/stress_scenarios_by_quarter.csv",
    "stress_montecarlo_2026q2": "data/processed/stress_montecarlo_2026Q2.csv",
    "stress_survival_horizon": "data/processed/stress_survival_horizon.csv",
    "stress_reverse_test": "data/processed/stress_reverse_test.csv",
}


def safe_col(name):
    return (name.strip().replace(" ", "_").replace("-", "_").replace("#", "num")
            .replace("%", "pct").replace("(", "").replace(")", "").replace("/", "_"))


def infer_type(values):
    for v in values:
        if v in ("", None):
            continue
        try:
            float(v)
        except ValueError:
            return "TEXT"
    return "REAL"


def load_csv_to_sqlite(conn, table, path):
    with open(path, encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)

    cols = []
    for i, col in enumerate(header):
        sample = [r[i] for r in rows[:100] if i < len(r)]
        cols.append((safe_col(col), infer_type(sample)))

    conn.execute(f'DROP TABLE IF EXISTS "{table}"')
    col_defs = ", ".join(f'"{c}" {t}' for c, t in cols)
    conn.execute(f'CREATE TABLE "{table}" ({col_defs})')

    cleaned = []
    for r in rows:
        vals = []
        for i, (c, t) in enumerate(cols):
            v = r[i] if i < len(r) else None
            if v == "":
                v = None
            elif t == "REAL" and v is not None:
                try:
                    v = float(v)
                except ValueError:
                    v = None
            vals.append(v)
        cleaned.append(vals)

    placeholders = ", ".join(["?"] * len(cols))
    conn.executemany(f'INSERT INTO "{table}" VALUES ({placeholders})', cleaned)
    print(f"  {table:32s} {len(cleaned):>4d} rows x {len(cols):>3d} cols   <- {path}")


def main():
    missing = [p for p in TABLES.values() if not os.path.exists(p)]
    if missing:
        raise FileNotFoundError(f"Missing source CSV(s), run the earlier pipeline steps first: {missing}")

    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    conn = sqlite3.connect(DB_PATH)

    print(f"Building {DB_PATH} from {len(TABLES)} CSV sources:\n")
    for table, path in TABLES.items():
        load_csv_to_sqlite(conn, table, path)
    conn.commit()

    print("\nSanity check -- LCR/NSFR baseline vs combined-scenario stress, joined by report_period:")
    cur = conn.execute("""
        SELECT r.report_period, r.LCR_pct AS baseline_LCR, s.combined_LCR_pct, s.combined_delta_pp
        FROM ratios_by_quarter r
        JOIN stress_scenarios_by_quarter s ON r.report_period = s.report_period
        ORDER BY r.report_period
    """)
    for row in cur.fetchall():
        print("   ", row)

    conn.close()
    size_kb = os.path.getsize(DB_PATH) / 1024
    print(f"\nWrote {DB_PATH} ({size_kb:,.0f} KB, {len(TABLES)} tables)")


if __name__ == "__main__":
    main()
