import arcpy
import os

arcpy.env.overwriteOutput = True

OUTPUT_GDB = r"C:\Users\jiaru\OneDrive\Desktop\calgary-bike-suitability\data\processed\calgary_bike.gdb"
ROADS = os.path.join(OUTPUT_GDB, "roads_projected")

# ── Width: number of car lanes assumed per class ──────────────────────────────
# excess_width = estimated_width - (car_lane_space + 3m for 2 bike lanes)
# Score: >=0 → 100, -1.5 to 0 → 50, -3 to -1.5 → 25, <-3 → 0
CAR_LANES_M = {
    "Residential Street":      7.0,   # 2 lanes × 3.5m
    "Collector":               7.0,
    "Industrial Street":       7.0,
    "Neighbourhood Boulevard": 7.0,
    "Activity Center Street":  7.0,
    "Parkway":                 7.0,
    "Primary Collector":       10.5,  # 3 lanes × 3.5m
    "Local Arterial":          10.5,
    "Arterial Street":         14.0,  # 4 lanes × 3.5m
    "Urban Boulevard":         14.0,
    "Industrial Arterial":     14.0,
}

def width_score(ctp_class, width_m):
    car_m = CAR_LANES_M.get(ctp_class, 7.0)
    excess = width_m - (car_m + 3.0)   # 3m = space for 2 bike lanes (1.5m each)
    if excess >= 0:
        return 100
    elif excess >= -1.5:
        return 50
    elif excess >= -3.0:
        return 25
    else:
        return 0

# ── Slope: based on North Bend paper grade categories ─────────────────────────
# 0-3.5% → 100 (flat, comfortable)
# 3.5-6.5% → 50 (manageable)
# >6.5% → 0 (too steep)
def slope_score(slope_pct):
    if slope_pct is None:
        return 50   # default to middle score if no data
    if slope_pct < 3.5:
        return 100
    elif slope_pct < 6.5:
        return 50
    else:
        return 0

# ── Speed: lower speed = safer for cyclists ───────────────────────────────────
# <=40 km/h → 100, 40-70 → 75, >70 → 50
# (No speed is a hard disqualifier — even fast roads can have protected lanes)
def speed_score(speed_kmh):
    if speed_kmh <= 40:
        return 100
    elif speed_kmh <= 70:
        return 75
    else:
        return 50

# ── Weights from North Bend Exponential Ranking 2 ────────────────────────────
# Width:Speed:Slope = 27:4:1 → 84% : 13% : 3%
W_WIDTH = 0.84
W_SLOPE = 0.13
W_SPEED = 0.03

# ── Add score fields ──────────────────────────────────────────────────────────
print("Adding score fields...")
existing = [f.name for f in arcpy.ListFields(ROADS)]
for field in ["w_score", "sl_score", "sp_score", "final_score"]:
    if field not in existing:
        arcpy.management.AddField(ROADS, field, "SHORT")

# ── Calculate scores ──────────────────────────────────────────────────────────
print("Calculating scores...")
fields = ["ctp_class", "width_m", "slope_pct", "speed_kmh",
          "w_score", "sl_score", "sp_score", "final_score"]

score_counts = {0: 0, 25: 0, 50: 0, 75: 0, 100: 0}
final_scores = []

with arcpy.da.UpdateCursor(ROADS, fields) as cursor:
    for row in cursor:
        ctp, width, slope, speed = row[0], row[1], row[2], row[3]

        ws  = width_score(ctp, width)
        sls = slope_score(slope)
        sps = speed_score(speed)
        fs  = round(ws * W_WIDTH + sls * W_SLOPE + sps * W_SPEED)

        row[4] = ws
        row[5] = sls
        row[6] = sps
        row[7] = fs
        cursor.updateRow(row)

        final_scores.append(fs)

print(f"  → {len(final_scores)} segments scored")

# ── Summary ───────────────────────────────────────────────────────────────────
print("\n--- Final Score Distribution ---")
buckets = {"81-100 (2 bike lanes)": 0, "42-80 (1 bike lane)": 0,
           "23-41 (partial)": 0, "0-22 (no room)": 0}
for s in final_scores:
    if s >= 81:
        buckets["81-100 (2 bike lanes)"] += 1
    elif s >= 42:
        buckets["42-80 (1 bike lane)"] += 1
    elif s >= 23:
        buckets["23-41 (partial)"] += 1
    else:
        buckets["0-22 (no room)"] += 1

for k, v in buckets.items():
    pct = v / len(final_scores) * 100
    print(f"  {k}: {v} segments ({pct:.1f}%)")

print(f"\n  Min score : {min(final_scores)}")
print(f"  Max score : {max(final_scores)}")
print(f"  Mean score: {sum(final_scores)/len(final_scores):.1f}")

print("\nDone. Output: roads_projected with w_score, sl_score, sp_score, final_score")
