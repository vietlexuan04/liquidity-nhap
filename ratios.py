"""
Compute LCR, NSFR and LDR for every quarter using:
  - data/processed/jpm_628_wide.csv   (one row per quarter, one column per FDIC mnemonic)
  - mapping/liquidity_mapping.csv     (one row per balance-sheet line, with LCR/NSFR roles)

Formulas (see mapping/mapping_README.md "Cach dung de tinh ratio"):

  HQLA          = sum(asset_value * (1 - haircut))                      [rows with hqla_level set]
  LCR outflow   = sum(value * lcr_outflow)                              [rows with lcr_outflow set: liabilities + off-bs commitments]
  LCR inflow    = sum(asset_value * lcr_inflow)                         [rows with lcr_inflow set]
  LCR           = HQLA / max(outflow - inflow, outflow * 25%)           [Basel LCR40.11: inflows capped at 75% of outflows]

  ASF           = sum(value * nsfr_asf)                                 [rows with nsfr_asf set: liabilities + equity]
  RSF           = sum(asset_value * nsfr_rsf * netting_factor)          [rows with nsfr_rsf set; netting_factor only for group=='loans']
  netting_factor(quarter) = LNLSNET / LNLSGR                            [nets the gross loan-maturity schedule down to carrying value]
  NSFR          = ASF / RSF

  LDR           = LNLSNET / DEP                                        [net loans / total deposits]
"""
import csv

WIDE_PATH = "data/processed/jpm_628_wide.csv"
MAPPING_PATH = "mapping/liquidity_mapping.csv"
OUT_PATH = "data/processed/ratios_by_quarter.csv"

mapping = list(csv.DictReader(open(MAPPING_PATH, encoding="utf-8")))
wide = list(csv.DictReader(open(WIDE_PATH, encoding="utf-8")))


def num(x):
    if x in (None, ""):
        return None
    try:
        return float(x)
    except ValueError:
        return None


def line_value(row, definition):
    """Evaluate a mapping 'definition' formula against one quarter's wide row."""
    env = {k: (float(v) if v not in ("", None) else 0.0) for k, v in row.items() if k != "report_period"}
    env["min"] = min
    return eval(definition, {"__builtins__": {}}, env)


def compute_quarter(row):
    lnlsnet = float(row.get("LNLSNET") or 0)
    lnlsgr = float(row.get("LNLSGR") or 0)
    netting_factor = lnlsnet / lnlsgr if lnlsgr else 1.0

    hqla = 0.0
    outflow = 0.0
    inflow = 0.0
    asf = 0.0
    rsf = 0.0

    for m in mapping:
        v = line_value(row, m["definition"])

        hl = m["hqla_level"].strip()
        if hl:
            haircut = num(m["hqla_haircut"]) or 0.0
            hqla += v * (1 - haircut)

        out_f = num(m["lcr_outflow"])
        if out_f is not None:
            outflow += v * out_f

        in_f = num(m["lcr_inflow"])
        if in_f is not None:
            inflow += v * in_f

        asf_f = num(m["nsfr_asf"])
        if asf_f is not None:
            asf += v * asf_f

        rsf_f = num(m["nsfr_rsf"])
        if rsf_f is not None:
            factor = netting_factor if m["group"] == "loans" else 1.0
            rsf += v * rsf_f * factor

    net_outflow = max(outflow - inflow, outflow * 0.25)  # Basel LCR40.11 inflow cap
    lcr = hqla / net_outflow if net_outflow else None
    nsfr = asf / rsf if rsf else None

    dep = float(row.get("DEP") or 0)
    ldr = lnlsnet / dep if dep else None

    return dict(
        report_period=row["report_period"],
        HQLA=round(hqla, 0),
        LCR_outflow_gross=round(outflow, 0),
        LCR_inflow=round(inflow, 0),
        LCR_net_outflow=round(net_outflow, 0),
        LCR_pct=round(lcr * 100, 2) if lcr is not None else None,
        NSFR_ASF=round(asf, 0),
        NSFR_RSF=round(rsf, 0),
        NSFR_pct=round(nsfr * 100, 2) if nsfr is not None else None,
        loan_netting_factor=round(netting_factor, 4),
        LDR_pct=round(ldr * 100, 2) if ldr is not None else None,
    )


results = [compute_quarter(row) for row in sorted(wide, key=lambda r: r["report_period"])]

FIELDS = list(results[0].keys())
with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(results)

print(f"Wrote {OUT_PATH} ({len(results)} quarters)\n")
header = f"{'quarter':10s} {'LCR%':>8s} {'NSFR%':>8s} {'LDR%':>8s} {'HQLA(B)':>10s} {'ASF(B)':>10s} {'RSF(B)':>10s}"
print(header)
for r in results:
    print(f"{r['report_period']:10s} {r['LCR_pct']:>8.1f} {r['NSFR_pct']:>8.1f} {r['LDR_pct']:>8.1f} "
          f"{r['HQLA']/1e6:>10,.1f} {r['NSFR_ASF']/1e6:>10,.1f} {r['NSFR_RSF']/1e6:>10,.1f}")
