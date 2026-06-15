import arcpy
from arcpy.sa import *
import os
import statistics

arcpy.CheckOutExtension("Spatial")
arcpy.env.overwriteOutput = True

RAW       = r"C:\Users\jiaru\OneDrive\Desktop\calgary-bike-suitability\data\raw"
PROCESSED = r"C:\Users\jiaru\OneDrive\Desktop\calgary-bike-suitability\data\processed"
OUTPUT_GDB = os.path.join(PROCESSED, "calgary_bike.gdb")

DEM_PATH      = os.path.join(RAW, "25m_Raster.gdb", "AlbertaProvincial25MetreRaster")
BOUNDARY_SHP  = os.path.join(RAW, "City Boundary_20260507",
                              "geo_export_8b3121e1-ca3c-4f60-be90-4672cbe64710.shp")
ROADS         = os.path.join(OUTPUT_GDB, "roads_projected")

arcpy.env.workspace = OUTPUT_GDB

# Step 1: Check DEM coordinate system
print("Step 1: Checking DEM coordinate system...")
dem_sr = arcpy.Describe(DEM_PATH).spatialReference
print(f"  → DEM CRS: {dem_sr.name}")
print(f"  → Linear unit: {dem_sr.linearUnitName}")

# Step 2: Reproject city boundary to match DEM coordinate system
# (so we can use it to clip the DEM)
print("\nStep 2: Reprojecting Calgary boundary to match DEM...")
boundary_dem_crs = os.path.join(OUTPUT_GDB, "boundary_dem_crs")
if arcpy.Exists(boundary_dem_crs):
    arcpy.management.Delete(boundary_dem_crs)
arcpy.management.Project(BOUNDARY_SHP, boundary_dem_crs, dem_sr)
print("  → Done")

# Step 3: Clip DEM to Calgary boundary
# ExtractByMask cuts the 4.6GB Alberta raster down to just Calgary
print("\nStep 3: Clipping DEM to Calgary boundary (may take a few minutes)...")
dem_calgary = ExtractByMask(DEM_PATH, boundary_dem_crs)
dem_calgary_path = os.path.join(OUTPUT_GDB, "dem_calgary")
dem_calgary.save(dem_calgary_path)
print("  → DEM clipped and saved")

# Step 4: Calculate slope in percent rise
# "Percent rise" means: for every 100m horizontal, how many meters gain in elevation
# e.g. 5% slope = 5m rise over 100m horizontal distance
print("\nStep 4: Calculating slope (percent rise)...")
dem_sr_type = dem_sr.type  # "Geographic" or "Projected"
if dem_sr_type == "Geographic":
    # DEM is in degrees, need z-factor to convert vertical (meters) to match horizontal (degrees)
    # z-factor for ~51°N latitude: approximately 0.00001141
    z_factor = 0.00001141
    print(f"  → Geographic CRS detected, using z-factor={z_factor}")
    slope_raster = Slope(dem_calgary_path, "PERCENT_RISE", z_factor)
else:
    print("  → Projected CRS, no z-factor needed")
    slope_raster = Slope(dem_calgary_path, "PERCENT_RISE")

slope_path = os.path.join(OUTPUT_GDB, "slope_calgary")
slope_raster.save(slope_path)
print("  → Slope raster saved")

# Step 5: Reproject slope raster to EPSG:3400 (same as roads)
print("\nStep 5: Reprojecting slope raster to EPSG:3400...")
slope_proj_path = os.path.join(OUTPUT_GDB, "slope_proj")
arcpy.management.ProjectRaster(
    slope_path, slope_proj_path,
    arcpy.SpatialReference(3400),
    "BILINEAR", 25
)
print("  → Slope reprojected to EPSG:3400")

# Step 6: Buffer roads by 15m so we can run zonal statistics on line features
# (Zonal statistics needs polygon zones, not lines)
print("\nStep 6: Buffering roads by 15m...")
roads_buffer = os.path.join(OUTPUT_GDB, "roads_buffer")
if arcpy.Exists(roads_buffer):
    arcpy.management.Delete(roads_buffer)
arcpy.analysis.Buffer(ROADS, roads_buffer, "15 Meters", dissolve_option="NONE")
print("  → Buffer complete")

# Step 7: Zonal statistics — get mean slope for each road buffer
# This answers: "what is the average slope along this road segment?"
print("\nStep 7: Extracting mean slope per road segment (zonal statistics)...")
slope_table = os.path.join(OUTPUT_GDB, "slope_stats")
if arcpy.Exists(slope_table):
    arcpy.management.Delete(slope_table)
ZonalStatisticsAsTable(roads_buffer, "segment_id", slope_proj_path,
                       slope_table, "DATA", "MEAN")
print("  → Zonal statistics complete")

# Step 8: Join slope values back to roads feature class
print("\nStep 8: Joining slope to roads...")
arcpy.management.AddField(ROADS, "slope_pct", "DOUBLE")

slope_dict = {}
with arcpy.da.SearchCursor(slope_table, ["segment_id", "MEAN"]) as cursor:
    for row in cursor:
        slope_dict[int(row[0])] = row[1]

updated = 0
with arcpy.da.UpdateCursor(ROADS, ["segment_id", "slope_pct"]) as cursor:
    for row in cursor:
        seg_id = int(row[0])
        if seg_id in slope_dict:
            row[1] = slope_dict[seg_id]
            cursor.updateRow(row)
            updated += 1

print(f"  → Slope joined for {updated} of {len(slope_dict)} segments")

# Step 9: Summary statistics
print("\n--- Slope Summary (% rise) ---")
slopes = list(slope_dict.values())
print(f"  Min    : {min(slopes):.1f}%")
print(f"  Max    : {max(slopes):.1f}%")
print(f"  Mean   : {statistics.mean(slopes):.1f}%")
print(f"  Median : {statistics.median(slopes):.1f}%")

arcpy.CheckInExtension("Spatial")
print("\nDone. slope_pct field added to roads_projected.")
