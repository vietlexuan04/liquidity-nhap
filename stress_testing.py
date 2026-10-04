"""
Stress testing engine -- LCR only (NSFR stress deferred, per decision).

Explicit assumption (stated, not implicit): NO management action / counterbalancing
capacity is modeled anywhere in this file. All results are "mechanical" outcomes of the
balance sheet as reported, under the stated shock -- a real bank would respond (drawing
contingency funding lines, selling non-HQLA assets, cutting new lending). That response is
deliberately excluded so the numbers show the *raw* balance-sheet sensitivity.

Every result is reported BOTH as an absolute LCR% and as a delta (pp and %) vs that same
quarter's OWN baseline -- never only the absolute number -- because this model's baseline
is already ~33pp below JPMorgan's disclosed LCR (see mapping_README.md benchmark section).
Reading the absolute stressed number alone would overstate how distressed the bank looks.
"""
import csv
import random

WIDE_PATH = "data/processed/jpm_628_wide.csv"
MAPPING_PATH = "mapping/liquidity_mapping.csv"

mapping_rows = list(csv.DictReader(open(MAPPING_PATH, encoding="utf-8")))
mapping = {m["line_id"]: m for m in mapping_rows}
wide = sorted(csv.DictReader(open(WIDE_PATH, encoding="utf-8")), key=lambda r: r["report_period"])
latest = wide[-1]


def line_value(row, definition):
    env = {k: (float(v) if v not in ("", None) else 0.0) for k, v in row.items() if k != "report_period"}
    env["min"] = min
    return eval(definition, {"__builtins__": {}}, env)


def compute_lcr(row, overrides=None):
    """Returns (HQLA, gross_outflow, inflow, net_outflow, LCR_pct)."""
    overrides = overrides or {}
    hqla = outflow = inflow = 0.0
    for m in mapping_rows:
        lid = m["line_id"]
        ov = overrides.get(lid, {})
        v = line_value(row, m["definition"])

        hl = m["hqla_level"].strip()
        if hl:
            hc = ov.get("hqla_haircut", float(m["hqla_haircut"] or 0))
            hqla += v * (1 - hc)

        out_f = ov.get("lcr_outflow", float(m["lcr_outflow"]) if m["lcr_outflow"] not in ("", None) else None)
        if out_f is not None:
            outflow += v * out_f
        in_f = ov.get("lcr_inflow", float(m["lcr_inflow"]) if m["lcr_inflow"] not in ("", None) else None)
        if in_f is not None:
            inflow += v * in_f

    net_out = max(outflow - inflow, outflow * 0.25)  # Basel LCR40.11 inflow cap
    lcr = hqla / net_out * 100 if net_out else None
    return hqla, outflow, inflow, net_out, lcr


def base_factor(line_id, field):
    v = mapping[line_id][field]
    return float(v) if v not in ("", None) else 0.0


# ---------------------------------------------------------------------------
# 1. Fixed scenarios
# ---------------------------------------------------------------------------
OFF_BS_LINES = ["O_CARD", "O_HELOC", "O_CRE", "O_OTHER", "O_SBLC"]

IDIOSYNCRATIC = {
    "D_INS_STABLE": {"lcr_outflow": 0.10},
    "D_INS_BRO": {"lcr_outflow": 0.25},
    "D_DOM_UNINS_OTH": {"lcr_outflow": 0.70},
    "D_FO_IPC": {"lcr_outflow": 0.70},
    **{lid: {"lcr_outflow": base_factor(lid, "lcr_outflow") * 1.5} for lid in OFF_BS_LINES},
}
MARKET_WIDE = {
    "S_GSE": {"hqla_haircut": 0.25},
    "S_MUNI": {"hqla_haircut": 0.65},
    "B_REPO": {"lcr_outflow": 0.50},
    # B_ST intentionally left unstressed: the brief gave no explicit number for it
    # (only "B_REPO / B_ST outflow" as a header, with values given for B_REPO only).
}
COMBINED = {**IDIOSYNCRATIC, **MARKET_WIDE}

SCENARIOS = {"idiosyncratic": IDIOSYNCRATIC, "market_wide": MARKET_WIDE, "combined": COMBINED}

print("=== 1. Fixed scenarios across all 14 quarters ===\n")
scenario_rows = []
for row in wide:
    _, _, _, _, base_lcr = compute_lcr(row)
    rec = dict(report_period=row["report_period"], baseline_LCR_pct=round(base_lcr, 1))
    for name, ov in SCENARIOS.items():
        _, _, _, _, s_lcr = compute_lcr(row, ov)
        rec[f"{name}_LCR_pct"] = round(s_lcr, 1)
        rec[f"{name}_delta_pp"] = round(s_lcr - base_lcr, 1)
        rec[f"{name}_delta_pct_of_baseline"] = round((s_lcr - base_lcr) / base_lcr * 100, 1)
    scenario_rows.append(rec)

with open("data/processed/stress_scenarios_by_quarter.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(scenario_rows[0].keys()))
    w.writeheader()
    w.writerows(scenario_rows)

hdr = f"{'quarter':10s} {'baseline':>9s} {'idio':>9s}(Δpp) {'market':>9s}(Δpp) {'combined':>9s}(Δpp)"
print(hdr)
for r in scenario_rows:
    print(f"{r['report_period']:10s} {r['baseline_LCR_pct']:>9.1f} "
          f"{r['idiosyncratic_LCR_pct']:>9.1f}({r['idiosyncratic_delta_pp']:+.1f}) "
          f"{r['market_wide_LCR_pct']:>9.1f}({r['market_wide_delta_pp']:+.1f}) "
          f"{r['combined_LCR_pct']:>9.1f}({r['combined_delta_pp']:+.1f})")

# ---------------------------------------------------------------------------
# 2. Monte Carlo deposit run-off (2026Q2 only)
# ---------------------------------------------------------------------------
print("\n=== 2. Monte Carlo deposit run-off (2026Q2, 10,000 draws) ===\n")
print("Randomized: D_INS_STABLE, D_INS_BRO, D_DOM_UNINS_OTH, D_FO_IPC (Beta dist, mean = combined-")
print("scenario value, std = 20% of mean). Everything else held fixed at combined-scenario values.\n")

MC_LINES = ["D_INS_STABLE", "D_INS_BRO", "D_DOM_UNINS_OTH", "D_FO_IPC"]


def beta_params(mean, std):
    var = std ** 2
    common = mean * (1 - mean) / var - 1
    return mean * common, (1 - mean) * common


random.seed(42)  # reproducibility
N_DRAWS = 10_000
mc_lcrs = []
for _ in range(N_DRAWS):
    draw_overrides = dict(COMBINED)  # start from combined scenario's fixed parameters
    for lid in MC_LINES:
        mean = COMBINED[lid]["lcr_outflow"]
        std = 0.20 * mean
        a, b = beta_params(mean, std)
        draw_overrides = {**draw_overrides, lid: {**draw_overrides.get(lid, {}), "lcr_outflow": random.betavariate(a, b)}}
    _, _, _, _, lcr = compute_lcr(latest, draw_overrides)
    mc_lcrs.append(lcr)

mc_lcrs.sort()
_, _, _, _, base_lcr_latest = compute_lcr(latest)


def pct(p):
    idx = int(p / 100 * (N_DRAWS - 1))
    return mc_lcrs[idx]


percentiles = {p: pct(p) for p in [5, 25, 50, 75, 95]}
print(f"{'percentile':>12s} {'LCR_pct':>9s} {'delta_pp_vs_baseline':>22s}")
with open("data/processed/stress_montecarlo_2026Q2.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["percentile", "LCR_pct", "delta_pp_vs_baseline"])
    for p, v in percentiles.items():
        print(f"{'p'+str(p):>12s} {v:>9.1f} {v-base_lcr_latest:>22.1f}")
        w.writerow([p, round(v, 1), round(v - base_lcr_latest, 1)])

# ---------------------------------------------------------------------------
# 3. Survival horizon (2026Q2): days until cumulative outflow exceeds HQLA,
#    assuming uniform daily outflow = net_outflow / 30 (stated assumption)
# ---------------------------------------------------------------------------
print("\n=== 3. Survival horizon (2026Q2, uniform daily outflow assumption) ===\n")
survival_rows = []
for name, ov in {"baseline": {}, **SCENARIOS}.items():
    hqla, _, _, net_out, lcr = compute_lcr(latest, ov)
    daily = net_out / 30
    days = hqla / daily if daily else float("inf")
    days_capped = min(days, 30)
    survival_rows.append(dict(scenario=name, HQLA_B=round(hqla / 1e6, 1), net_outflow_30d_B=round(net_out / 1e6, 1),
                               LCR_pct=round(lcr, 1), survival_days=round(days_capped, 1),
                               survives_30d="Yes" if days >= 30 else "No"))
    print(f"{name:14s} HQLA={hqla/1e6:>8.1f}B  net_outflow_30d={net_out/1e6:>8.1f}B  "
          f"LCR={lcr:>6.1f}%  survival≈{days_capped:>5.1f} days  (>=30d: {'Yes' if days>=30 else 'No'})")

with open("data/processed/stress_survival_horizon.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(survival_rows[0].keys()))
    w.writeheader()
    w.writerows(survival_rows)

# ---------------------------------------------------------------------------
# 4. Reverse stress test (2026Q2): solve for stress intensity theta
#    (0 = baseline, 1 = full combined scenario, linear interpolation of each
#    factor, extrapolated beyond [0,1] if needed) that hits a target LCR.
#    NOTE: baseline LCR is already 85% (<100%) before any stress -- the
#    classic "shock needed to breach 100%" target is therefore solved for a
#    NEGATIVE theta (i.e. LESS stress than baseline), which is itself the
#    headline finding, not a bug.
# ---------------------------------------------------------------------------
print("\n=== 4. Reverse stress test (2026Q2) ===\n")


def factor_at_theta(lid, field, theta):
    base = base_factor(lid, field)
    target = COMBINED.get(lid, {}).get(field, base)
    return base + theta * (target - base)


def lcr_at_theta(theta):
    ov = {}
    for lid in COMBINED:
        for field in COMBINED[lid]:
            ov.setdefault(lid, {})[field] = factor_at_theta(lid, field, theta)
    return compute_lcr(latest, ov)[-1]


def solve_theta(target_lcr, lo=-1.0, hi=10.0, iters=60):
    # LCR is (weakly) decreasing in theta given COMBINED only worsens outflow/haircuts
    f_lo, f_hi = lcr_at_theta(lo), lcr_at_theta(hi)
    if not (f_hi <= target_lcr <= f_lo):
        return None  # target not reachable in [lo, hi]
    for _ in range(iters):
        mid = (lo + hi) / 2
        f_mid = lcr_at_theta(mid)
        if f_mid > target_lcr:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


reverse_rows = []
for target in [100, 75, 50]:
    theta = solve_theta(target)
    survival_at = None
    if theta is not None:
        ov = {lid: {f: factor_at_theta(lid, f, theta) for f in COMBINED[lid]} for lid in COMBINED}
        hqla, _, _, net_out, lcr_check = compute_lcr(latest, ov)
        daily = net_out / 30
        survival_at = min(hqla / daily, 30) if daily else 30
    reverse_rows.append(dict(target_LCR_pct=target, required_theta=round(theta, 3) if theta is not None else None,
                              interpretation=(f"{theta*100:.0f}% of the combined-scenario shock" if theta is not None and theta >= 0
                                              else (f"LESS stress than baseline by {abs(theta)*100:.0f}% of the combined-scenario gap"
                                                    if theta is not None else "not reachable in tested range"))))
    print(f"target LCR={target:>3d}%:  theta={theta}   -> {reverse_rows[-1]['interpretation']}")

theta_survival0 = solve_theta(1.0, lo=1.0, hi=100.0)  # approx: LCR -> ~0 as proxy for HQLA fully depleted
print(f"\ntheta for near-total HQLA depletion (LCR~0%): {theta_survival0}")
reverse_rows.append(dict(target_LCR_pct=0, required_theta=round(theta_survival0, 3) if theta_survival0 else None,
                          interpretation="stress intensity at which HQLA is ~fully depleted within 30 days"))

with open("data/processed/stress_reverse_test.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(reverse_rows[0].keys()))
    w.writeheader()
    w.writerows(reverse_rows)

print("\nWrote: stress_scenarios_by_quarter.csv, stress_montecarlo_2026Q2.csv, "
      "stress_survival_horizon.csv, stress_reverse_test.csv")
