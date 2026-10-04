"""
Reshape the raw FDIC BankFind "Customize a Report" export (wide, quarter-blocks-as-columns)
into:
  1. data/processed/jpm_628_long.csv   -- tidy long format: report_period, label, mnemonic, value
  2. data/processed/jpm_628_wide.csv   -- one row per quarter, one column per mnemonic (numeric)

Raw layout per data row:
  col0 = human-readable label
  col1 = '' (spacer)
  then repeating 3-col blocks per quarter: [mnemonic, value, spacer]
"""
import csv
import re

RAW_PATH = "data/raw/jpm_628_raw.csv"
LONG_PATH = "data/processed/jpm_628_long.csv"
WIDE_PATH = "data/processed/jpm_628_wide.csv"

with open(RAW_PATH, encoding="utf-8-sig") as f:
    rows = list(csv.reader(f))

HEADER_ROW_IDX = 3  # 0-based row with "Report Period" / date blocks
header_row = rows[HEADER_ROW_IDX]

# report periods sit at columns 3, 6, 9, ... (col2 == 'Report Period')
periods = []
col = 2
while col < len(header_row):
    if header_row[col] == "Report Period":
        periods.append(header_row[col + 1])
    col += 3
n_quarters = len(periods)
print(f"Detected {n_quarters} quarters: {periods}")


def clean_value(raw):
    if raw is None:
        return None
    v = raw.strip()
    if v in ("", "N/A", "NA"):
        return None
    neg = v.startswith("(") and v.endswith(")")
    v = v.strip("()")
    v = v.replace("$", "").replace(",", "").replace("%", "").strip()
    if v in ("", "-"):
        return None
    try:
        num = float(v)
        return -num if neg else num
    except ValueError:
        return raw.strip()  # keep as text (e.g. bank name, footnote markers)


long_records = []
for row in rows:
    if not row or not row[0].strip():
        continue
    label = row[0].strip()
    # skip pure footnote / narrative rows (start with a plain digit+dot but no mnemonic block),
    # and rows that don't have the expected mnemonic/value block structure
    if len(row) < 4:
        continue
    for i in range(n_quarters):
        base = 2 + i * 3
        if base + 1 >= len(row):
            break
        mnemonic = row[base].strip() if row[base] else ""
        raw_value = row[base + 1] if base + 1 < len(row) else ""
        if not mnemonic or mnemonic == "Report Period":
            continue
        value = clean_value(raw_value)
        long_records.append(
            {
                "report_period": periods[i],
                "label": label,
                "mnemonic": mnemonic,
                "value": value,
            }
        )

print(f"Parsed {len(long_records)} long-format records")

with open(LONG_PATH, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["report_period", "label", "mnemonic", "value"])
    w.writeheader()
    w.writerows(long_records)

# ---- pivot to wide: one row per report_period, one column per mnemonic ----
# keep only numeric mnemonics (drop text mnemonics like NAMEFULL for the numeric wide table,
# but keep a separate lookup of label per mnemonic for documentation)
mnemonic_labels = {}
wide = {p: {} for p in periods}
for rec in long_records:
    mnemonic_labels.setdefault(rec["mnemonic"], rec["label"])
    if isinstance(rec["value"], (int, float)):
        wide[rec["report_period"]][rec["mnemonic"]] = rec["value"]

all_mnemonics = sorted(mnemonic_labels.keys())
numeric_mnemonics = [m for m in all_mnemonics if any(m in wide[p] for p in periods)]

with open(WIDE_PATH, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["report_period"] + numeric_mnemonics)
    # sort periods ascending (oldest first) for time-series friendliness
    for p in sorted(periods):
        row = [p] + [wide[p].get(m, "") for m in numeric_mnemonics]
        w.writerow(row)

# also dump a data dictionary: mnemonic -> label
with open("data/processed/mnemonic_labels.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["mnemonic", "label"])
    for m in all_mnemonics:
        w.writerow([m, mnemonic_labels[m]])

print(f"Wrote {WIDE_PATH} with {len(numeric_mnemonics)} numeric columns x {n_quarters} quarters")
print(f"Wrote data dictionary with {len(all_mnemonics)} mnemonics")
