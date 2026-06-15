import arcpy
import os

arcpy.env.overwriteOutput = True

OUTPUT_GDB = r"C:\Users\jiaru\OneDrive\Desktop\calgary-bike-suitability\data\processed\calgary_bike.gdb"
ROADS = os.path.join(OUTPUT_GDB, "roads_projected")

# OAT (One-At-A-Time) sensitivity analysis:
# Each round fixes one factor and shifts 15pp between the other two.
# This ensures each comparison is fair — same perturbation magnitude, one factor locked.
#
# Baseline: width 84%, slope 13%, speed  3%
# Round 1 (speed fixed=3%):  shift 15pp from width to slope → 69/28/3
# Round 2 (slope fixed=13%): shift 15pp from width to speed → 69/13/18
# Round 3 (width fixed=84%): shift 10pp from slope to speed → 84/3/13
SCENARIOS = {
    "score_A": {"w_width": 0.84, "w_slope": 0.13, "w_speed": 0.03,
                "label": "Baseline       (84/13/ 3) original weights"},
    "score_B": {"w_width": 0.69, "w_slope": 0.28, "w_speed": 0.03,
                "label": "Round 1: speed fixed  (69/28/ 3) slope+, width-"},
    "score_C": {"w_width": 0.69, "w_slope": 0.13, "w_speed": 0.18,
                "label": "Round 2: slope fixed  (69/13/18) speed+, width-"},
    "score_D": {"w_width": 0.84, "w_slope": 0.03, "w_speed": 0.13,
                "label": "Round 3: width fixed  (84/ 3/13) speed+, slope-"},
}

# Add a score field for each scenario (skip A since it's already final_score)
print("Adding scenario fields...")
existing = [f.name for f in arcpy.ListFields(ROADS)]
for field in ["score_B", "score_C", "score_D"]:
    if field not in existing:
        arcpy.management.AddField(ROADS, field, "SHORT")

# Calculate scores for all scenarios
print("Calculating scores for all scenarios...")
fields = ["w_score", "sl_score", "sp_score", "final_score", "score_B", "score_C", "score_D"]
all_scores = {"score_A": [], "score_B": [], "score_C": [], "score_D": []}

with arcpy.da.UpdateCursor(ROADS, fields) as cursor:
    for row in cursor:
        ws, sls, sps = row[0], row[1], row[2]

        score_a = round(ws * 0.84 + sls * 0.13 + sps * 0.03)  # already in final_score
        score_b = round(ws * 0.69 + sls * 0.28 + sps * 0.03)  # speed fixed
        score_c = round(ws * 0.69 + sls * 0.13 + sps * 0.18)  # slope fixed
        score_d = round(ws * 0.84 + sls * 0.03 + sps * 0.13)  # width fixed

        row[4] = score_b
        row[5] = score_c
        row[6] = score_d
        cursor.updateRow(row)

        all_scores["score_A"].append(score_a)
        all_scores["score_B"].append(score_b)
        all_scores["score_C"].append(score_c)
        all_scores["score_D"].append(score_d)

print(f"  → {len(all_scores['score_A'])} segments scored across 4 scenarios\n")

# Compare distributions across scenarios
def distribution(scores):
    buckets = {"81-100": 0, "42-80": 0, "23-41": 0, "0-22": 0}
    for s in scores:
        if s >= 81:   buckets["81-100"] += 1
        elif s >= 42: buckets["42-80"]  += 1
        elif s >= 23: buckets["23-41"]  += 1
        else:         buckets["0-22"]   += 1
    total = len(scores)
    return {k: f"{v} ({v/total*100:.1f}%)" for k, v in buckets.items()}

print("=" * 65)
print(f"{'Scenario':<30} {'81-100':>10} {'42-80':>12} {'23-41':>12} {'Mean':>6}")
print("=" * 65)

for key, scenario in SCENARIOS.items():
    scores = all_scores[key]
    d = distribution(scores)
    mean = sum(scores) / len(scores)
    label = scenario["label"]
    # Extract just percentages for clean display
    p1 = d["81-100"].split("(")[1].rstrip(")")
    p2 = d["42-80"].split("(")[1].rstrip(")")
    p3 = d["23-41"].split("(")[1].rstrip(")")
    print(f"{label:<30} {p1:>10} {p2:>12} {p3:>12} {mean:>6.1f}")

print("=" * 65)

# Find roads where scenarios disagree most (top 10 most affected)
print("\nTop 10 road segments most affected by weight changes:")
fields_check = ["full_name", "ctp_class", "final_score", "score_B", "score_C", "score_D"]
seen = set()
diffs = []
with arcpy.da.SearchCursor(ROADS, fields_check) as cursor:
    for row in cursor:
        name, cls, sa, sb, sc, sd = row
        key = (name, cls)
        if key in seen:
            continue
        seen.add(key)
        spread = max(sa, sb, sc, sd) - min(sa, sb, sc, sd)
        diffs.append((spread, name or "Unnamed", cls, sa, sb, sc, sd))

diffs.sort(reverse=True)
print(f"{'Road':<25} {'Class':<22} {'A':>5} {'B':>5} {'C':>5} {'D':>5} {'Diff':>5}")
print("-" * 75)
for spread, name, cls, sa, sb, sc, sd in diffs[:10]:
    print(f"{name[:24]:<25} {cls[:21]:<22} {sa:>5} {sb:>5} {sc:>5} {sd:>5} {spread:>5}")

print("\nOAT Sensitivity Analysis complete.")
print("Fixed factor per round: B=speed fixed, C=slope fixed, D=width fixed")
print("In ArcGIS Pro: switch Symbology between final_score / score_B / score_C / score_D")
