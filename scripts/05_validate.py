import arcpy
import os

arcpy.env.overwriteOutput = True

RAW        = r"C:\Users\jiaru\OneDrive\Desktop\calgary-bike-suitability\data\raw"
OUTPUT_GDB = r"C:\Users\jiaru\OneDrive\Desktop\calgary-bike-suitability\data\processed\calgary_bike.gdb"
ROADS      = os.path.join(OUTPUT_GDB, "roads_projected")
BIKEWAYS   = os.path.join(RAW, "Calgary Bikeways_20260510",
                           "geo_export_b5f1d360-19bc-45e5-93cd-886489125a65.shp")

# ── Step 1: Filter to existing, non-decommissioned bikeways ──────────────────
print("Step 1: Filtering bikeways...")
bikeways_existing = os.path.join(OUTPUT_GDB, "bikeways_existing")
if arcpy.Exists(bikeways_existing):
    arcpy.management.Delete(bikeways_existing)

arcpy.analysis.Select(
    BIKEWAYS, bikeways_existing,
    "status = 'EXISTING' AND bicycle_cl <> 'DECOMMISSIONED' AND bicycle_cl <> 'TEMPORARY'"
)
count = int(arcpy.management.GetCount(bikeways_existing)[0])
print(f"  {count} existing bikeway segments kept")

# ── Step 2: Reproject bikeways to EPSG:3400 (same as roads) ─────────────────
print("Step 2: Reprojecting bikeways to EPSG:3400...")
bikeways_proj = os.path.join(OUTPUT_GDB, "bikeways_proj")
if arcpy.Exists(bikeways_proj):
    arcpy.management.Delete(bikeways_proj)
arcpy.management.Project(bikeways_existing, bikeways_proj, arcpy.SpatialReference(3400))
print("  Done")

# ── Step 3: Buffer bikeways by 20m ───────────────────────────────────────────
# We buffer so that nearby road segments (which may not perfectly overlap)
# are captured — accounts for slight geometry misalignment between datasets.
print("Step 3: Buffering bikeways by 20m...")
bikeways_buffer = os.path.join(OUTPUT_GDB, "bikeways_buffer")
if arcpy.Exists(bikeways_buffer):
    arcpy.management.Delete(bikeways_buffer)
arcpy.analysis.Buffer(bikeways_proj, bikeways_buffer, "20 Meters", dissolve_option="ALL")
print("  Done")

# ── Step 4: Tag roads that overlap existing bikeways ─────────────────────────
print("Step 4: Tagging roads with existing bikeways...")
if "has_bikeway" not in [f.name for f in arcpy.ListFields(ROADS)]:
    arcpy.management.AddField(ROADS, "has_bikeway", "SHORT")

arcpy.management.CalculateField(ROADS, "has_bikeway", "0")

roads_with_bikeway = os.path.join(OUTPUT_GDB, "roads_with_bikeway_temp")
if arcpy.Exists(roads_with_bikeway):
    arcpy.management.Delete(roads_with_bikeway)
arcpy.analysis.SpatialJoin(
    ROADS, bikeways_buffer, roads_with_bikeway,
    join_operation="JOIN_ONE_TO_ONE",
    match_option="INTERSECT"
)

tagged = 0
id_with_bikeway = set()
with arcpy.da.SearchCursor(roads_with_bikeway, ["segment_id", "Join_Count"]) as cursor:
    for row in cursor:
        if row[1] > 0:
            id_with_bikeway.add(int(row[0]))
            tagged += 1

with arcpy.da.UpdateCursor(ROADS, ["segment_id", "has_bikeway"]) as cursor:
    for row in cursor:
        if int(row[0]) in id_with_bikeway:
            row[1] = 1
            cursor.updateRow(row)

print(f"  {tagged} road segments overlap existing bikeways")

# ── Step 5: Compare scores ────────────────────────────────────────────────────
print("\nStep 5: Comparing scores...")
scores_with    = []
scores_without = []

with arcpy.da.SearchCursor(ROADS, ["has_bikeway", "final_score"]) as cursor:
    for row in cursor:
        if row[0] == 1:
            scores_with.append(row[1])
        else:
            scores_without.append(row[1])

avg_with    = sum(scores_with)    / len(scores_with)
avg_without = sum(scores_without) / len(scores_without)
avg_all     = (sum(scores_with) + sum(scores_without)) / (len(scores_with) + len(scores_without))

print(f"\n{'':=<55}")
print(f"  Roads WITH existing bike lanes  : {len(scores_with):>6} segments | avg score = {avg_with:.1f}")
print(f"  Roads WITHOUT existing bike lanes: {len(scores_without):>6} segments | avg score = {avg_without:.1f}")
print(f"  All roads (baseline)             : {len(scores_with)+len(scores_without):>6} segments | avg score = {avg_all:.1f}")
print(f"{'':=<55}")
print(f"  Score lift from model: +{avg_with - avg_without:.1f} points")

# ── Step 6: Distribution breakdown ───────────────────────────────────────────
print("\nScore distribution for roads WITH existing bike lanes:")
b = {"81-100 (High)": 0, "42-80 (Moderate)": 0, "23-41 (Low)": 0}
for s in scores_with:
    if s >= 81:   b["81-100 (High)"]    += 1
    elif s >= 42: b["42-80 (Moderate)"] += 1
    else:         b["23-41 (Low)"]      += 1
for k, v in b.items():
    print(f"  {k}: {v} ({v/len(scores_with)*100:.1f}%)")

print("\nScore distribution for ALL roads:")
b2 = {"81-100 (High)": 0, "42-80 (Moderate)": 0, "23-41 (Low)": 0}
for s in scores_with + scores_without:
    if s >= 81:   b2["81-100 (High)"]    += 1
    elif s >= 42: b2["42-80 (Moderate)"] += 1
    else:         b2["23-41 (Low)"]      += 1
for k, v in b2.items():
    total = len(scores_with) + len(scores_without)
    print(f"  {k}: {v} ({v/total*100:.1f}%)")

arcpy.management.Delete(roads_with_bikeway)
print("\nDone. Field 'has_bikeway' added to roads_projected (1=has bikeway, 0=none)")
