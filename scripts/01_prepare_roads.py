import arcpy
import os

RAW = r"C:\Users\jiaru\OneDrive\Desktop\calgary-bike-suitability\data\raw"
PROCESSED = r"C:\Users\jiaru\OneDrive\Desktop\calgary-bike-suitability\data\processed"

ROADS_SHP = os.path.join(RAW, "Street Centreline_20260507",
                         "geo_export_28982756-b519-47c5-85ae-01913e9160fe.shp")
OUTPUT_GDB = os.path.join(PROCESSED, "calgary_bike.gdb")

# Width and speed estimates by road class (Calgary road design standards)
CTP_LOOKUP = {
    "Residential Street":      {"width_m": 8.5,  "speed_kmh": 40},
    "Collector":               {"width_m": 11.0, "speed_kmh": 50},
    "Primary Collector":       {"width_m": 13.0, "speed_kmh": 50},
    "Arterial Street":         {"width_m": 15.0, "speed_kmh": 60},
    "Urban Boulevard":         {"width_m": 16.0, "speed_kmh": 60},
    "Industrial Arterial":     {"width_m": 14.0, "speed_kmh": 60},
    "Industrial Street":       {"width_m": 10.0, "speed_kmh": 50},
    "Neighbourhood Boulevard": {"width_m": 10.0, "speed_kmh": 40},
    "Activity Center Street":  {"width_m": 11.0, "speed_kmh": 40},
    "Local Arterial":          {"width_m": 13.0, "speed_kmh": 60},
    "Parkway":                 {"width_m": 13.0, "speed_kmh": 70},
}

# Step 1: Create output geodatabase
print("Step 1: Creating geodatabase...")
if not arcpy.Exists(OUTPUT_GDB):
    arcpy.management.CreateFileGDB(PROCESSED, "calgary_bike.gdb")
    print("  → Created calgary_bike.gdb")
else:
    print("  → GDB already exists, continuing")

# Step 2: Filter to built roads and relevant classes
print("\nStep 2: Filtering roads...")
roads_filtered = os.path.join(OUTPUT_GDB, "roads_filtered")
if arcpy.Exists(roads_filtered):
    arcpy.management.Delete(roads_filtered)

exclude = "('Lanes (Alleys)', 'Skeletal Road', 'Access Route', 'Historic Road Allowance')"
arcpy.analysis.Select(
    ROADS_SHP,
    roads_filtered,
    f"built_stat = 'Built' AND ownership = 'Corporate' AND ctp_class NOT IN {exclude}"
)
count = int(arcpy.management.GetCount(roads_filtered)[0])
print(f"  → {count} road segments kept")

# Step 3: Reproject to EPSG:3400 (NAD83 / Alberta 3TM 114W)
print("\nStep 3: Reprojecting to EPSG:3400...")
roads_proj = os.path.join(OUTPUT_GDB, "roads_projected")
if arcpy.Exists(roads_proj):
    arcpy.management.Delete(roads_proj)

arcpy.management.Project(
    roads_filtered,
    roads_proj,
    arcpy.SpatialReference(3400)
)
print("  → Reprojection complete")

# Step 4: Add width and speed fields from lookup table
print("\nStep 4: Adding width_m and speed_kmh fields...")
arcpy.management.AddField(roads_proj, "width_m",   "DOUBLE")
arcpy.management.AddField(roads_proj, "speed_kmh", "SHORT")

updated = 0
with arcpy.da.UpdateCursor(roads_proj, ["ctp_class", "width_m", "speed_kmh"]) as cursor:
    for row in cursor:
        cls = row[0]
        if cls in CTP_LOOKUP:
            row[1] = CTP_LOOKUP[cls]["width_m"]
            row[2] = CTP_LOOKUP[cls]["speed_kmh"]
            cursor.updateRow(row)
            updated += 1

print(f"  → {updated} segments updated")

# Step 5: Delete columns we don't need
print("\nStep 5: Removing unused fields...")
drop_fields = ["built_stat", "numeric_pr", "name", "street_typ",
               "plan_statu", "ownership", "date_creat", "time_creat",
               "date_modif", "time_modif", "date_mod_2", "time_mod_2"]
existing = [f.name for f in arcpy.ListFields(roads_proj)]
to_drop = [f for f in drop_fields if f in existing]
arcpy.management.DeleteField(roads_proj, to_drop)
print(f"  → Dropped {len(to_drop)} fields")
print(f"  → Remaining fields: {[f.name for f in arcpy.ListFields(roads_proj)]}")

# Summary check
print("\n--- Summary: CTP class → (width_m, speed_kmh) ---")
seen = {}
with arcpy.da.SearchCursor(roads_proj, ["ctp_class", "width_m", "speed_kmh"]) as cursor:
    for row in cursor:
        if row[0] not in seen:
            seen[row[0]] = (row[1], row[2])
for k in sorted(seen):
    print(f"  {k}: width={seen[k][0]}m, speed={seen[k][1]}km/h")

print("\nDone. Output:", roads_proj)
