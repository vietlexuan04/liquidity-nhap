"""
Sensitivity analysis on every confidence='Low' row in mapping/liquidity_mapping.csv.

For each such row, a plausible [low, high] bound is assigned to whichever factor column
it uses (hqla_haircut / lcr_outflow / lcr_inflow / nsfr_asf / nsfr_rsf), grounded in the
alternate Basel-permitted category the row could belong to (documented in BOUNDS below).

Two views are produced, both on the latest quarter (2026Q2):
  1. One-at-a-time (OAT): vary ONE row at a time, hold all others at baseline -> isolates
     how many points of LCR/NSFR that single assumption is worth.
  2. Combined extreme: push ALL Low-confidence rows simultaneously to whichever bound
     worsens (or improves) each ratio -> gives an outer envelope of "how much could the
     proxy move on model uncertainty alone", separate from any stress scenario.

B_TRADEL (trading liabilities, currently fully omitted from LCR outflow -- a known
*omission*, not a calibration choice) is tested separately, not blended into the Low-
confidence OAT/combined envelope, since omitting vs. estimating is a different kind of
uncertainty than "which Basel sub-category applies".
"""
import csv

WIDE_PATH = "data/processed/jpm_628_wide.csv"
MAPPING_PATH = "mapping/liquidity_mapping.csv"
OUT_PATH = "data/processed/sensitivity_results.csv"

mapping = list(csv.DictReader(open(MAPPING_PATH, encoding="utf-8")))
wide = list(csv.DictReader(open(WIDE_PATH, encoding="utf-8")))
latest = sorted(wide, key=lambda r: r["report_period"])[-1]  # 2026Q2


def line_value(row, definition):
    env = {k: (float(v) if v not in ("", None) else 0.0) for k, v in row.items() if k != "report_period"}
    env["min"] = min
    return eval(definition, {"__builtins__": {}}, env)


def compute(row, overrides=None):
    """overrides: {line_id: {field: value}} temporary factor overrides for this run only."""
    overrides = overrides or {}
    lnlsnet = float(row.get("LNLSNET") or 0)
    lnlsgr = float(row.get("LNLSGR") or 0)
    netting = lnlsnet / lnlsgr if lnlsgr else 1.0

    hqla = outflow = inflow = asf = rsf = 0.0
    for m in mapping:
        lid = m["line_id"]
        ov = overrides.get(lid, {})
        v = line_value(row, m["definition"])

        hl = m["hqla_level"].strip()
        if hl:
            hc = ov.get("hqla_haircut", float(m["hqla_haircut"] or 0))
            hqla += v * (1 - hc)

        def getf(col):
            raw = m[col]
            if col in ov:
                return ov[col]
            return float(raw) if raw not in ("", None) else None

        out_f = getf("lcr_outflow")
        if out_f is not None:
            outflow += v * out_f
        in_f = getf("lcr_inflow")
        if in_f is not None:
            inflow += v * in_f
        asf_f = getf("nsfr_asf")
        if asf_f is not None:
            asf += v * asf_f
        rsf_f = getf("nsfr_rsf")
        if rsf_f is not None:
            factor = netting if m["group"] == "loans" else 1.0
            rsf += v * rsf_f * factor

    net_out = max(outflow - inflow, outflow * 0.25)
    lcr = hqla / net_out * 100 if net_out else None
    nsfr = asf / rsf * 100 if rsf else None
    return lcr, nsfr


baseline_lcr, baseline_nsfr = compute(latest)
print(f"Baseline (2026Q2): LCR={baseline_lcr:.1f}%  NSFR={baseline_nsfr:.1f}%\n")

# ---- bounds for each Low-confidence row: (field, low_value, high_value, note) ----
# "low"/"high" are the FACTOR values (not necessarily low=worse); direction noted per row.
BOUNDS = {
    "A_CASH_FOREIGN": [
        ("hqla_haircut", 0.0, 1.0, "L1 reserve (0% haircut) vs ordinary correspondent balance, not HQLA (100% haircut)"),
        ("nsfr_rsf", 0.0, 0.15, "central-bank reserve (0% RSF) vs FI placement <6m (15% RSF)"),
    ],
    "A_CIPC": [("nsfr_rsf", 0.0, 1.0, "near-cash, clears fast (0%) vs conservative 'other asset' (100%, current)")],
    "S_MUNI": [
        ("hqla_haircut", 0.5, 1.0, "investment-grade GO muni, L2B (50%, current) vs non-investment-grade, not HQLA (100%)"),
        ("nsfr_rsf", 0.5, 0.85, "L2B RSF (50%) vs non-HQLA RSF (85%)"),
    ],
    "S_OTHDOM": [("nsfr_rsf", 0.65, 1.0, "eligible >=1y non-HQLA bond (65%) vs equity-like/unrated (100%, current more conservative end)")],
    "S_FOR": [("nsfr_rsf", 0.65, 1.0, "could include foreign sovereign eligible debt (65%) vs fully unrated (100%)")],
    "S_OTHER": [("nsfr_rsf", 0.65, 1.0, "mixed bag -- same bracket as above")],
    "A_TRADE": [("nsfr_rsf", 0.15, 1.0, "securities-like trading book (15%) vs derivative-like (100%)")],
    "A_REVREPO": [
        ("lcr_inflow", 0.0, 1.0, "no credit, current (0%) vs full secured-lending inflow credit (100%)"),
        ("nsfr_rsf", 0.10, 0.15, "L1-collateralized (10%) vs other collateral <6m (15%)"),
    ],
    "L_NBFI_SHORT": [("lcr_inflow", 0.0, 1.0, "no credit (0%) vs full 30d maturity credit (100%, current is 33%)")],
    "L_OTH_LE12": [("lcr_inflow", 0.0, 0.5, "no credit, current (0%) vs retail/SME 30d maturing credit (50%)")],
    "L_RECON": [("nsfr_rsf", 0.65, 1.0, "mostly performing, just unscheduled (65%) vs non-performing (100%)")],
    "D_DOM_FOR": [
        ("lcr_outflow", 0.4, 1.0, "if mostly govt/PSE non-operational (40%) vs FI, current (100%)"),
        ("nsfr_asf", 0.0, 0.5, "FI, current (0% ASF) vs govt/PSE (50% ASF)"),
    ],
    "D_FO_IPC": [("lcr_outflow", 0.25, 1.0, "operational corporate deposit (25%) vs non-bank FI (100%)")],
    "B_REPO": [("lcr_outflow", 0.0, 1.0, "fully L1-collateralized (0%) vs uncollateralized/other (100%)")],
    "B_OTHL": [("lcr_outflow", 0.0, 0.2, "pure accruals/payables (0%, current) vs some near-term funding mixed in (20%)")],
    "O_OTHER": [("lcr_outflow", 0.10, 0.50, "mostly corporate credit facility (10%) vs liquidity/FI facility mix (50%)")],
    "O_SBLC": [("lcr_outflow", 0.05, 0.20, "trade-related SBLC (5%, current) vs non-trade/financial guarantee (20%)")],
}

print(f"{'line_id':18s} {'field':14s} {'LCR@low':>9s} {'LCR@high':>9s} {'dLCR(pp)':>10s}   "
      f"{'NSFR@low':>9s} {'NSFR@high':>9s} {'dNSFR(pp)':>10s}")
oat_rows = []
for lid, specs in BOUNDS.items():
    for field, lo, hi, note in specs:
        lcr_lo, nsfr_lo = compute(latest, {lid: {field: lo}})
        lcr_hi, nsfr_hi = compute(latest, {lid: {field: hi}})
        d_lcr = lcr_hi - lcr_lo
        d_nsfr = (nsfr_hi - nsfr_lo) if (nsfr_hi and nsfr_lo) else 0.0
        print(f"{lid:18s} {field:14s} {lcr_lo:>9.1f} {lcr_hi:>9.1f} {d_lcr:>10.2f}   "
              f"{nsfr_lo:>9.1f} {nsfr_hi:>9.1f} {d_nsfr:>10.2f}")
        oat_rows.append(dict(line_id=lid, field=field, low=lo, high=hi, note=note,
                              LCR_at_low=round(lcr_lo, 1), LCR_at_high=round(lcr_hi, 1), delta_LCR_pp=round(d_lcr, 2),
                              NSFR_at_low=round(nsfr_lo, 1), NSFR_at_high=round(nsfr_hi, 1), delta_NSFR_pp=round(d_nsfr, 2)))

with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(oat_rows[0].keys()))
    w.writeheader()
    w.writerows(oat_rows)

# ---- combined extreme envelope: push every Low-confidence field toward whichever bound
#      worsens (or improves) EACH ratio, simultaneously ----
def extreme_for(metric_idx, direction):
    """metric_idx: 0=LCR, 1=NSFR. direction: 'worst' or 'best'."""
    overrides = {}
    for lid, specs in BOUNDS.items():
        overrides[lid] = {}
        for field, lo, hi, note in specs:
            r_lo = compute(latest, {lid: {field: lo}})[metric_idx]
            r_hi = compute(latest, {lid: {field: hi}})[metric_idx]
            if direction == "worst":
                overrides[lid][field] = lo if r_lo < r_hi else hi
            else:
                overrides[lid][field] = lo if r_lo > r_hi else hi
    return compute(latest, overrides)

lcr_worst, _ = extreme_for(0, "worst")
lcr_best, _ = extreme_for(0, "best")
_, nsfr_worst = extreme_for(1, "worst")
_, nsfr_best = extreme_for(1, "best")

print("\n--- Combined extreme envelope (ALL 19 Low-confidence rows pushed together, 2026Q2) ---")
print(f"LCR : worst={lcr_worst:.1f}%  baseline={baseline_lcr:.1f}%  best={lcr_best:.1f}%  "
      f"(range {lcr_best-lcr_worst:.1f}pp)")
print(f"NSFR: worst={nsfr_worst:.1f}%  baseline={baseline_nsfr:.1f}%  best={nsfr_best:.1f}%  "
      f"(range {nsfr_best-nsfr_worst:.1f}pp)")

# ---- B_TRADEL: separate test, this is a known OMISSION not a calibration bound ----
print("\n--- B_TRADEL (trading liabilities) currently fully omitted from LCR outflow ---")
for pct in [0.0, 0.20, 0.50, 1.0]:
    lcr_t, _ = compute(latest, {"B_TRADEL": {"lcr_outflow": pct}})
    print(f"  if trading-liability outflow rate = {pct*100:>5.0f}%:  LCR = {lcr_t:.1f}%  "
          f"(delta vs current omission: {lcr_t-baseline_lcr:+.1f}pp)")
