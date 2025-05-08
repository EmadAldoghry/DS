# -*- coding: utf-8 -*-
import os
import time
from pathlib import Path

# Import functions from our step modules
from step1_compute_hull import compute_and_save_convex_hull
from step2a_fetch_wfs import fetch_clip_and_save_wfs
from step2b_fetch_osm import fetch_clip_and_save_osm_streets
from step3_analyze_gml import analyze_gml_and_sample_points
from step4_calculate_alpha_shape import calculate_and_save_alpha_shape
from step5_generate_texture import generate_texture_from_polygon
from step6_generate_cut_obj_model import generate_cut_obj_model
from step7_generate_nav2_map import generate_nav2_map

# --- Main Configuration ---
# Input Data
CSV_FILE = 'defect_coordinates.csv' # Make sure this file exists in the same directory or provide full path

# CRS Configuration
SOURCE_CRS = 'EPSG:4326'  # CRS of the input CSV coordinates
TARGET_CRS = 'EPSG:25832' # Target CRS for most processing (UTM 32N for NRW, Germany)

# Step 1: Convex Hull
BUFFER_METERS_FOR_HULL = 15
OUTPUT_HULL_GPKG = "convex_hull.gpkg" # Will be saved in OUTPUT_DIR

# Step 2: External Data Fetching
WFS_URL = 'https://www.wfs.nrw.de/geobasis/wfs_nw_alkis_aaa-modell-basiert'
WFS_FEATURE_TYPES = ['adv:AX_Strassenverkehr', 'adv:AX_Strassenverkehrsanlage']
OSM_OUTPUT_GPKG = "osm_streets_clipped.gpkg" # Will be saved in OUTPUT_DIR

# Step 3: GML Analysis (for a specific WFS layer)
# This will be constructed based on WFS_FEATURE_TYPES
# For example, if 'adv:AX_Strassenverkehrsanlage' is chosen:
# FEATURE_TYPE_TO_ANALYZE_STEM = "adv_AX_Strassenverkehrsanlage_clipped"
# GML_TO_ANALYZE_FILENAME = f"{FEATURE_TYPE_TO_ANALYZE_STEM}.gml"
ANALYSIS_OFFSET_METERS = 0.1
POINT_SAMPLE_INTERVAL_METERS = 5.0
SAMPLED_POINTS_CSV = "analyzed_gml_sampled_points.csv" # Output from GML analysis

# Step 4: Alpha Shape
ALPHA_SHAPE_PARAMETER = None
# ALPHA_DEFAULT_IF_OPTIMIZE_FAILS = 1000.0 # Old value, too large
ALPHA_DEFAULT_IF_OPTIMIZE_FAILS = 0.1  # New default: Corresponds to a radius of 1/0.05 = 20 units (meters)
                                        # You might need to tune this value based on typical point cloud density.
                                        # Try values like 0.1, 0.02, etc.
ALPHA_SHAPE_OUTPUT_GML = "calculated_alpha_shape.gml"

# -- Step 5 Config (Texture) --
TEXTURE_SOURCE_GML_KEY = 'adv:AX_Strassenverkehr'
OUTPUT_TEXTURE_FILENAME = "road_texture.png"
WMS_TEXTURE_URL = "https://www.wms.nrw.de/geobasis/wms_nw_dop"
WMS_TEXTURE_LAYER = "nw_dop_rgb"
WMS_TEXTURE_VERSION = '1.3.0'
WMS_TEXTURE_FORMAT = 'image/tiff'
WMS_TEXTURE_WIDTH = 2048
WMS_TEXTURE_HEIGHT = 2048
WMS_TEXTURE_TARGET_CRS = TARGET_CRS
WMS_BBOX_PADDING_METERS = 20.0
POLYGON_CRS_FALLBACK_FOR_TEXTURE = TARGET_CRS
TEXTURE_FILL_COLOR_RGB = [128, 128, 128]

# --- NEW: Step 6 Configuration (GML to OBJ Generation) ---
BASE_GML_KEY_FOR_CUT = 'adv:AX_Strassenverkehr'
TOOL_GML_FILENAME_FOR_CUT = ALPHA_SHAPE_OUTPUT_GML
BASE_EXTRUSION_CUT_M = -2.0
TOOL_EXTRUSION_CUT_M = -0.5
CUT_SIMPLIFY_TOLERANCE_M = 0.01
CUT_OBJ_OUTPUT_FILENAME = "final_cut_road_model.obj"
CUT_MTL_OUTPUT_FILENAME = "final_cut_road_model.mtl"
CUT_MODEL_OUTPUT_SUBDIR = "cut_model_output" # Subdir for final OBJ/MTL/PNG set
CONVERT_GENERATE_VT = True
CONVERT_Z_TOLERANCE = 0.01
CONVERT_MATERIAL_TOP = "RoadSurface"
CONVERT_MATERIAL_BOTTOM = "RoadBottom"
CONVERT_MATERIAL_SIDES = "RoadSides"

# --- NEW: Step 7 Configuration (Nav2 Map) ---
NAV2_MAP_SOURCE_GML_FILENAME = ALPHA_SHAPE_OUTPUT_GML # Use Alpha Shape GML
NAV2_MAP_OUTPUT_BASENAME = "alpha_shape_nav2_map"     # Basename for map.pgm/yaml
NAV2_MAP_RESOLUTION = 0.05                           # Meters per pixel
NAV2_MAP_PADDING_M = 5.0                             # Padding around GML extent
NAV2_MAP_OUTPUT_SUBDIR = "nav2_map_output"           # Subdirectory for map files

# General Output & Plotting
OUTPUT_DIR_BASE = 'output_project' # Main output directory
SHOW_PLOTS_ALL_STEPS = False # Master switch for showing plots (True for dev, False for batch)
SAVE_PLOTS_ALL_STEPS = True   # Master switch for saving plots
PLOT_DPI_ALL_STEPS = 150

def main():
    print("--- Orchestrator Script Start ---")
    start_time_script = time.time()

    output_dir = Path(OUTPUT_DIR_BASE)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"All outputs will be saved in: {output_dir.resolve()}")

    # --- Step 1: Compute Convex Hull ---
    hull_gpkg_path = None
    try:
        print("\n=== STEP 1: Computing Convex Hull ===")
        hull_gpkg_path = compute_and_save_convex_hull(
            csv_path_str=CSV_FILE,
            source_crs_str=SOURCE_CRS,
            target_crs_str=TARGET_CRS,
            buffer_m=BUFFER_METERS_FOR_HULL,
            output_hull_gpkg_str=str(output_dir / OUTPUT_HULL_GPKG)
        )
        if not hull_gpkg_path: raise Exception("Hull computation failed to return a path.")
        print(f"Convex Hull GPKG: {hull_gpkg_path}")
    except Exception as e:
        print(f"FATAL ERROR in Step 1 (Convex Hull): {e}")
        return # Exit if hull fails

    # --- Step 2: Fetch External Data ---
    fetched_wfs_gml_paths = {}
    fetched_osm_gpkg_path = None
    if hull_gpkg_path:
        print("\n=== STEP 2a: Fetching WFS Data ===")
        try:
            fetched_wfs_gml_paths = fetch_clip_and_save_wfs(
                hull_polygon_gpkg_path_str=hull_gpkg_path,
                wfs_url=WFS_URL,
                feature_types=WFS_FEATURE_TYPES,
                target_crs_str=TARGET_CRS,
                out_dir_str=str(output_dir)
            )
            print("Fetched WFS GML paths:", fetched_wfs_gml_paths)
        except Exception as e:
            print(f"ERROR in Step 2a (WFS Fetch): {e}")

        print("\n=== STEP 2b: Fetching OSM Data ===")
        try:
            fetched_osm_gpkg_path = fetch_clip_and_save_osm_streets(
                hull_polygon_gpkg_path_str=hull_gpkg_path,
                target_crs_str=TARGET_CRS,
                out_dir_str=str(output_dir)
            )
            if fetched_osm_gpkg_path: print(f"Fetched OSM GPKG: {fetched_osm_gpkg_path}")
            else: print("OSM fetching did not return a path (likely failed).")
        except Exception as e:
            print(f"ERROR in Step 2b (OSM Fetch): {e}")
    else:
        print("Skipping External Data fetch due to missing hull.")

    # --- Step 3: Analyze GML (e.g., the first WFS feature type if available) ---
    sampled_points_list = None # Will be a list of Shapely Point objects
    gml_to_analyze_path = None
    gml_to_analyze_stem = None

    # Decide which GML to analyze (e.g., 'adv:AX_Strassenverkehrsanlage')
    # FEATURE_TYPE_TO_ANALYZE = 'adv:AX_Strassenverkehrsanlage' # As per original
    FEATURE_TYPE_TO_ANALYZE = WFS_FEATURE_TYPES[1] if len(WFS_FEATURE_TYPES) > 1 else (WFS_FEATURE_TYPES[0] if WFS_FEATURE_TYPES else None)


    if FEATURE_TYPE_TO_ANALYZE and FEATURE_TYPE_TO_ANALYZE in fetched_wfs_gml_paths:
        gml_to_analyze_path = fetched_wfs_gml_paths[FEATURE_TYPE_TO_ANALYZE]
        gml_to_analyze_stem = Path(gml_to_analyze_path).stem
        print(f"\nSelected for GML Analysis: {gml_to_analyze_path}")
    elif FEATURE_TYPE_TO_ANALYZE:
        # Fallback: construct path and check if it exists (e.g. from a previous run)
        constructed_path = output_dir / f"{FEATURE_TYPE_TO_ANALYZE.replace(':', '_').replace('/', '_')}_clipped.gml"
        if constructed_path.exists():
            gml_to_analyze_path = str(constructed_path)
            gml_to_analyze_stem = constructed_path.stem
            print(f"\nUsing existing GML for Analysis: {gml_to_analyze_path}")
        else:
            print(f"Warning: GML file for {FEATURE_TYPE_TO_ANALYZE} not found for analysis.")
    else:
        print("Warning: No WFS feature type specified or fetched for GML analysis.")


    if gml_to_analyze_path and hull_gpkg_path:
        print("\n=== STEP 3: Analyzing GML and Sampling Points ===")
        try:
            sampled_points_list = analyze_gml_and_sample_points(
                gml_file_path_str=gml_to_analyze_path,
                hull_polygon_gpkg_path_str=hull_gpkg_path,
                output_dir_str=str(output_dir),
                gml_filename_stem_for_plots=gml_to_analyze_stem, # For plot filenames
                analysis_offset=ANALYSIS_OFFSET_METERS,
                sample_interval=POINT_SAMPLE_INTERVAL_METERS,
                show_plots=SHOW_PLOTS_ALL_STEPS,
                save_plots=SAVE_PLOTS_ALL_STEPS,
                plot_dpi=PLOT_DPI_ALL_STEPS
            )
            if sampled_points_list:
                print(f"GML Analysis generated {len(sampled_points_list)} sampled points.")
                # The analysis function already saves points to a CSV, we can use that path or the list directly
            else:
                print("GML Analysis did not return sampled points.")
        except Exception as e:
            print(f"ERROR in Step 3 (GML Analysis): {e}")
    else:
        print("Skipping GML Analysis: Missing GML file to analyze or hull polygon.")

    # --- Step 4: Calculate Alpha Shape ---
    alpha_shape_gml_path = None
    # Use the CSV path saved by analyze_gml_and_sample_points or the list
    points_input_for_alpha = None
    if gml_to_analyze_stem: # Check if GML analysis was attempted
        potential_csv_path = output_dir / f"{gml_to_analyze_stem}_sampled_points.csv"
        if potential_csv_path.exists():
            points_input_for_alpha = str(potential_csv_path)
            print(f"Using CSV for alpha shape: {points_input_for_alpha}")
        elif sampled_points_list: # Use the list if CSV not found but list exists
            points_input_for_alpha = sampled_points_list
            print("Using in-memory list of points for alpha shape.")

    if points_input_for_alpha:
        print("\n=== STEP 4: Calculating Alpha Shape ===")
        try:
            alpha_shape_gml_path = calculate_and_save_alpha_shape(
                sampled_points_input=points_input_for_alpha,
                target_crs_str=TARGET_CRS,
                output_dir_str=str(output_dir),
                output_filename_stem=Path(ALPHA_SHAPE_OUTPUT_GML).stem,
                alpha_parameter=ALPHA_SHAPE_PARAMETER,
                # optimize_alpha_factor=ALPHA_OPTIMIZE_FACTOR, # <<<< REMOVE THIS ARGUMENT
                default_alpha_if_optimize_fails=ALPHA_DEFAULT_IF_OPTIMIZE_FAILS,
                show_plots=SHOW_PLOTS_ALL_STEPS,
                save_plots=SAVE_PLOTS_ALL_STEPS,
                plot_dpi=PLOT_DPI_ALL_STEPS
            )
            if alpha_shape_gml_path: print(f"Alpha Shape GML: {alpha_shape_gml_path}")
        except Exception as e:
            print(f"ERROR in Step 4 (Alpha Shape): {e}")
            # Print traceback for unexpected errors during the call itself
            import traceback
            traceback.print_exc()
    else:
        print("Skipping Alpha Shape: No sampled points available from GML analysis.")

     # --- Determine Paths for Step 5 & 6 ---
    # Directory where the final OBJ, MTL, and Texture will be saved
    final_model_output_dir = output_dir / CUT_MODEL_OUTPUT_SUBDIR
    final_model_output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nFinal model outputs (OBJ/MTL/PNG) will be in: {final_model_output_dir.resolve()}")

    # Path for the GML providing the footprint for the texture map
    gml_for_texture_footprint_path = fetched_wfs_gml_paths.get(TEXTURE_SOURCE_GML_KEY)

    # Paths for the GMLs used in the boolean cut
    base_gml_for_cut_path = fetched_wfs_gml_paths.get(BASE_GML_KEY_FOR_CUT)
    tool_gml_for_cut_path = alpha_shape_gml_path # This comes from Step 4 result


    # --- Step 5: Generate Texture (Save to final model directory) ---
    final_texture_path = None # Path to the generated PNG
    if gml_for_texture_footprint_path and Path(gml_for_texture_footprint_path).exists():
        print(f"\n=== STEP 5: Generating Texture (based on {Path(gml_for_texture_footprint_path).name}) ===")
        try:
            # Pass the *final* output directory to Step 5
            final_texture_path = generate_texture_from_polygon(
                polygon_gml_path_str=gml_for_texture_footprint_path,
                output_dir_str=str(final_model_output_dir), # <<< Save PNG here
                output_texture_filename=OUTPUT_TEXTURE_FILENAME, # Just the filename
                wms_url=WMS_TEXTURE_URL, wms_layer=WMS_TEXTURE_LAYER,
                wms_version=WMS_TEXTURE_VERSION, wms_format=WMS_TEXTURE_FORMAT,
                wms_width=WMS_TEXTURE_WIDTH, wms_height=WMS_TEXTURE_HEIGHT,
                target_wms_crs_str=WMS_TEXTURE_TARGET_CRS,
                wms_bbox_padding=WMS_BBOX_PADDING_METERS,
                polygon_crs_fallback_str=TARGET_CRS,
                fill_color_rgb=TEXTURE_FILL_COLOR_RGB,
                show_plots=SHOW_PLOTS_ALL_STEPS, save_plots=SAVE_PLOTS_ALL_STEPS, plot_dpi=PLOT_DPI_ALL_STEPS
            )
            if final_texture_path: print(f"Texture PNG Saved: {final_texture_path}")
            else: print("Texture generation failed.")
        except Exception as e: print(f"ERROR in Step 5 (Texture Generation): {e}"); import traceback; traceback.print_exc()
    else:
        print(f"Skipping Texture Generation: Source GML '{TEXTURE_SOURCE_GML_KEY}' not found.")

    # --- Step 6: Generate Textured Cut OBJ Model ---
    cut_model_generated = False
    # Check inputs needed for cut model (Base GML, Tool GML, Texture PNG)
    base_gml_for_cut_path = fetched_wfs_gml_paths.get(BASE_GML_KEY_FOR_CUT)
    tool_gml_for_cut_path_step6 = alpha_shape_gml_path # Use result from Step 4
    inputs_valid_for_cut = True
    if not (base_gml_for_cut_path and Path(base_gml_for_cut_path).exists()): print(f"ERROR Step 6 Input: Base GML '{BASE_GML_KEY_FOR_CUT}' not found."); inputs_valid_for_cut = False
    if not (tool_gml_for_cut_path_step6 and Path(tool_gml_for_cut_path_step6).exists()): print(f"ERROR Step 6 Input: Tool GML (Alpha Shape) '{TOOL_GML_FILENAME_FOR_CUT}' not found."); inputs_valid_for_cut = False
    if not final_texture_path: print(f"ERROR Step 6 Input: Texture file was not generated in Step 5."); inputs_valid_for_cut = False

    if inputs_valid_for_cut:
        print("\n=== STEP 6: Generating Textured Cut OBJ Model ===")
        try:
            success = generate_cut_obj_model(
                base_gml_path_str=str(base_gml_for_cut_path),
                tool_gml_path_str=str(tool_gml_for_cut_path_step6),
                output_dir_str=str(final_model_output_dir), # Use final model dir
                target_crs=TARGET_CRS,
                base_extrusion_height=BASE_EXTRUSION_CUT_M,
                tool_extrusion_height=TOOL_EXTRUSION_CUT_M,
                simplify_tolerance=CUT_SIMPLIFY_TOLERANCE_M,
                output_obj_filename=CUT_OBJ_OUTPUT_FILENAME,
                output_mtl_filename=CUT_MTL_OUTPUT_FILENAME,
                texture_filename=Path(final_texture_path).name, # Relative texture name
                material_top=CONVERT_MATERIAL_TOP, material_bottom=CONVERT_MATERIAL_BOTTOM, material_sides=CONVERT_MATERIAL_SIDES,
                generate_vt=CONVERT_GENERATE_VT, z_tolerance=CONVERT_Z_TOLERANCE,
                show_plots=SHOW_PLOTS_ALL_STEPS, save_plots=SAVE_PLOTS_ALL_STEPS, plot_dpi=PLOT_DPI_ALL_STEPS
            )
            if success: cut_model_generated = True; print(f"Textured Cut OBJ generated: {final_model_output_dir / CUT_OBJ_OUTPUT_FILENAME}")
            else: print("Textured Cut OBJ generation failed.")
        except Exception as e_cut_obj: print(f"ERROR Step 6: {e_cut_obj}"); import traceback; traceback.print_exc()
    else: print("Skipping Step 6: Missing inputs.")

    # --- NEW: Step 7: Generate Nav2 Map from Alpha Shape ---
    nav2_map_generated = False
    nav2_map_output_dir = output_dir / NAV2_MAP_OUTPUT_SUBDIR
    # Use the alpha_shape_gml_path determined in Step 4
    gml_for_nav2_map_path = alpha_shape_gml_path

    if gml_for_nav2_map_path and Path(gml_for_nav2_map_path).exists():
        print("\n=== STEP 7: Generating Nav2 Map Files ===")
        nav2_map_output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Nav2 map output directory: {nav2_map_output_dir.resolve()}")
        try:
            success = generate_nav2_map(
                gml_input_path_str=str(gml_for_nav2_map_path),
                output_dir_str=str(nav2_map_output_dir),
                output_map_basename=NAV2_MAP_OUTPUT_BASENAME,
                map_resolution=NAV2_MAP_RESOLUTION,
                map_padding_m=NAV2_MAP_PADDING_M
            )
            if success:
                nav2_map_generated = True
                print(f"Nav2 map files generated in: {nav2_map_output_dir}")
            else:
                print("Nav2 map generation failed.")
        except Exception as e_nav_map:
            print(f"ERROR during Step 7 (Nav2 Map Generation): {e_nav_map}")
            import traceback
            traceback.print_exc()
    else:
        print("Skipping Step 7 (Nav2 Map Generation): Alpha shape GML file not found.")

    end_time_script = time.time()
    print(f"\n--- Orchestrator Script Complete ---")
    print(f"Total execution time: {end_time_script - start_time_script:.2f} seconds")
    print(f"Main output directory: {output_dir.resolve()}")
    if cut_model_generated: print(f"Textured Cut OBJ model output directory: {final_model_output_dir.resolve()}")
    if nav2_map_generated: print(f"Nav2 Map output directory: {nav2_map_output_dir.resolve()}")

if __name__ == '__main__':
    # Create a dummy CSV_FILE if it doesn't exist for testing
    if not Path(CSV_FILE).exists():
        import pandas as pd
        print(f"Creating dummy '{CSV_FILE}' for testing.")
        # dummy_data = {'latitude': [50.9413, 50.9371, 50.9352], # Cologne area
        #               'longitude': [6.9583, 6.9531, 6.9602]}
        dummy_data = {'latitude': [51.87101360965492], # Cologne area
                      'longitude': [7.286309500176276]}
        pd.DataFrame(dummy_data).to_csv(CSV_FILE, index=False)
    main()