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
from step6b_transform_obj import transform_obj_file # <<< NEW IMPORT
from step7_generate_nav2_map import generate_nav2_map
from step8_generate_gazebo_world import create_gazebo_model_and_world

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
ANALYSIS_OFFSET_METERS = 0.1
POINT_SAMPLE_INTERVAL_METERS = 5.0
SAMPLED_POINTS_CSV = "analyzed_gml_sampled_points.csv" # Output from GML analysis

# Step 4: Alpha Shape
ALPHA_SHAPE_PARAMETER = None
ALPHA_DEFAULT_IF_OPTIMIZE_FAILS = 0.1
ALPHA_SHAPE_OUTPUT_GML = "calculated_alpha_shape.gml"

# -- Step 5 Config (Texture) --
TEXTURE_SOURCE_GML_KEY = 'adv:AX_Strassenverkehr'
OUTPUT_TEXTURE_FILENAME = "road_texture.png" # This is the texture image file, e.g. road_texture.png
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

# --- Step 6 Configuration (GML to OBJ Generation) ---
BASE_GML_KEY_FOR_CUT = 'adv:AX_Strassenverkehr'
TOOL_GML_FILENAME_FOR_CUT = ALPHA_SHAPE_OUTPUT_GML
BASE_EXTRUSION_CUT_M = -2.0
TOOL_EXTRUSION_CUT_M = -0.5
CUT_SIMPLIFY_TOLERANCE_M = 0.01
CUT_OBJ_OUTPUT_FILENAME = "final_cut_road_model.obj" # Intermediate OBJ before transformation
CUT_MTL_OUTPUT_FILENAME = "final_cut_road_model.mtl" # MTL for the intermediate OBJ
CUT_MODEL_OUTPUT_SUBDIR = "cut_model_output"
CONVERT_GENERATE_VT = True
CONVERT_Z_TOLERANCE = 0.01
CONVERT_MATERIAL_TOP = "RoadSurface"
CONVERT_MATERIAL_BOTTOM = "RoadBottom"
CONVERT_MATERIAL_SIDES = "RoadSides"

# --- NEW: Step 6b Configuration (OBJ Transformation) ---
TRANSFORM_Z_ADDITIONAL_OFFSET = 0.0  # Additional Z offset for the transformed OBJ
TRANSFORMED_OBJ_OUTPUT_FILENAME = "model.obj" # Final OBJ name after transformation by Step 6b

# --- Step 7 Configuration (Nav2 Map) ---
NAV2_MAP_SOURCE_GML_FILENAME = ALPHA_SHAPE_OUTPUT_GML
NAV2_MAP_OUTPUT_BASENAME = "alpha_shape_nav2_map"
NAV2_MAP_RESOLUTION = 0.05
NAV2_MAP_PADDING_M = 5.0
NAV2_MAP_OUTPUT_SUBDIR = "nav2_map_output"

# --- NEW: Step 8 Configuration (Gazebo World) ---
GAZEBO_OUTPUT_SUBDIR = "gazebo_output"             # Subdirectory for all Gazebo files
GAZEBO_MODEL_NAME = "pipeline_road_model"          # Name of the model directory for Gazebo
GAZEBO_WORLD_FILENAME = "pipeline_generated.world" # Name of the .world file

# General Output & Plotting
OUTPUT_DIR_BASE = 'output_project'
SHOW_PLOTS_ALL_STEPS = False
SAVE_PLOTS_ALL_STEPS = True
PLOT_DPI_ALL_STEPS = 150

def main():
    print("--- Orchestrator Script Start ---")
    start_time_script = time.time()

    output_dir = Path(OUTPUT_DIR_BASE)
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"All outputs will be saved in: {output_dir.resolve()}")

    # ... (Steps 1 to 5 remain the same) ...
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
        return

    # --- Step 2: Fetch External Data ---
    fetched_wfs_gml_paths = {}
    # ... (WFS/OSM fetching logic) ...
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
    # ...

    # --- Step 3: Analyze GML ---
    sampled_points_list = None
    gml_to_analyze_path = None
    gml_to_analyze_stem = None
    # ... (GML analysis logic) ...
    FEATURE_TYPE_TO_ANALYZE = WFS_FEATURE_TYPES[1] if len(WFS_FEATURE_TYPES) > 1 else (WFS_FEATURE_TYPES[0] if WFS_FEATURE_TYPES else None)
    if FEATURE_TYPE_TO_ANALYZE and FEATURE_TYPE_TO_ANALYZE in fetched_wfs_gml_paths:
        gml_to_analyze_path = fetched_wfs_gml_paths[FEATURE_TYPE_TO_ANALYZE]
        gml_to_analyze_stem = Path(gml_to_analyze_path).stem
    # ...

    if gml_to_analyze_path and hull_gpkg_path:
        print("\n=== STEP 3: Analyzing GML and Sampling Points ===")
        # ... (call analyze_gml_and_sample_points) ...
        try:
            sampled_points_list = analyze_gml_and_sample_points(
                gml_file_path_str=gml_to_analyze_path,
                hull_polygon_gpkg_path_str=hull_gpkg_path,
                output_dir_str=str(output_dir),
                gml_filename_stem_for_plots=gml_to_analyze_stem,
                analysis_offset=ANALYSIS_OFFSET_METERS,
                sample_interval=POINT_SAMPLE_INTERVAL_METERS,
                show_plots=SHOW_PLOTS_ALL_STEPS,
                save_plots=SAVE_PLOTS_ALL_STEPS,
                plot_dpi=PLOT_DPI_ALL_STEPS
            )
        except Exception as e: print(f"ERROR in Step 3 (GML Analysis): {e}")
    # ...

    # --- Step 4: Calculate Alpha Shape ---
    alpha_shape_gml_path = None
    # ... (Alpha shape logic) ...
    points_input_for_alpha = None
    if gml_to_analyze_stem:
        potential_csv_path = output_dir / f"{gml_to_analyze_stem}_sampled_points.csv"
        if potential_csv_path.exists(): points_input_for_alpha = str(potential_csv_path)
        elif sampled_points_list: points_input_for_alpha = sampled_points_list

    if points_input_for_alpha:
        print("\n=== STEP 4: Calculating Alpha Shape ===")
        # ... (call calculate_and_save_alpha_shape) ...
        try:
            alpha_shape_gml_path = calculate_and_save_alpha_shape(
                sampled_points_input=points_input_for_alpha,
                target_crs_str=TARGET_CRS,
                output_dir_str=str(output_dir),
                output_filename_stem=Path(ALPHA_SHAPE_OUTPUT_GML).stem,
                alpha_parameter=ALPHA_SHAPE_PARAMETER,
                default_alpha_if_optimize_fails=ALPHA_DEFAULT_IF_OPTIMIZE_FAILS,
                show_plots=SHOW_PLOTS_ALL_STEPS,
                save_plots=SAVE_PLOTS_ALL_STEPS,
                plot_dpi=PLOT_DPI_ALL_STEPS
            )
        except Exception as e: print(f"ERROR in Step 4 (Alpha Shape): {e}")
    # ...

    # --- Setup for Step 5, 6, 6b, 8 ---
    final_model_output_dir = output_dir / CUT_MODEL_OUTPUT_SUBDIR # e.g. output_project/cut_model_output/
    final_model_output_dir.mkdir(parents=True, exist_ok=True)
    print(f"\nModel outputs (OBJ/MTL/PNG) will be in: {final_model_output_dir.resolve()}")

    gml_for_texture_footprint_path = fetched_wfs_gml_paths.get(TEXTURE_SOURCE_GML_KEY)

    # --- Step 5: Generate Texture ---
    final_texture_path = None # Full path to the generated texture PNG
    # ... (Texture generation logic) ...
    if gml_for_texture_footprint_path and Path(gml_for_texture_footprint_path).exists():
        print(f"\n=== STEP 5: Generating Texture (based on {Path(gml_for_texture_footprint_path).name}) ===")
        try:
            final_texture_path = generate_texture_from_polygon(
                polygon_gml_path_str=gml_for_texture_footprint_path,
                output_dir_str=str(final_model_output_dir), # Texture saved here
                output_texture_filename=OUTPUT_TEXTURE_FILENAME,
                # ... other texture params
                wms_url=WMS_TEXTURE_URL, wms_layer=WMS_TEXTURE_LAYER,
                wms_version=WMS_TEXTURE_VERSION, wms_format=WMS_TEXTURE_FORMAT,
                wms_width=WMS_TEXTURE_WIDTH, wms_height=WMS_TEXTURE_HEIGHT,
                target_wms_crs_str=WMS_TEXTURE_TARGET_CRS,
                wms_bbox_padding=WMS_BBOX_PADDING_METERS,
                polygon_crs_fallback_str=TARGET_CRS,
                fill_color_rgb=TEXTURE_FILL_COLOR_RGB,
                show_plots=SHOW_PLOTS_ALL_STEPS, save_plots=SAVE_PLOTS_ALL_STEPS, plot_dpi=PLOT_DPI_ALL_STEPS
            )
        except Exception as e: print(f"ERROR in Step 5 (Texture Generation): {e}")
    # ...
    if final_texture_path: print(f"Texture PNG Saved: {final_texture_path}")


    # --- Step 6: Generate Textured Cut OBJ Model (Intermediate) ---
    cut_model_generated_step6 = False
    # This is the path to the UNTRANSFORMED OBJ, e.g., .../cut_model_output/final_cut_road_model.obj
    intermediate_obj_path_step6 = final_model_output_dir / CUT_OBJ_OUTPUT_FILENAME
    # This is the path to its MTL, e.g., .../cut_model_output/final_cut_road_model.mtl
    intermediate_mtl_path_step6 = final_model_output_dir / CUT_MTL_OUTPUT_FILENAME

    base_gml_for_cut_path = fetched_wfs_gml_paths.get(BASE_GML_KEY_FOR_CUT)
    tool_gml_for_cut_path_step6 = alpha_shape_gml_path
    inputs_valid_for_cut = True
    # ... (input validation for step 6) ...
    if not (base_gml_for_cut_path and Path(base_gml_for_cut_path).exists()): inputs_valid_for_cut = False
    if not (tool_gml_for_cut_path_step6 and Path(tool_gml_for_cut_path_step6).exists()): inputs_valid_for_cut = False
    if not (final_texture_path and Path(final_texture_path).exists()): inputs_valid_for_cut = False


    if inputs_valid_for_cut:
        print("\n=== STEP 6: Generating Textured Cut OBJ Model (Intermediate) ===")
        # ... (call generate_cut_obj_model) ...
        try:
            texture_file_name_for_mtl = Path(final_texture_path).name
            success_step6 = generate_cut_obj_model(
                base_gml_path_str=str(base_gml_for_cut_path),
                tool_gml_path_str=str(tool_gml_for_cut_path_step6),
                output_dir_str=str(final_model_output_dir),
                target_crs=TARGET_CRS,
                base_extrusion_height=BASE_EXTRUSION_CUT_M,
                tool_extrusion_height=TOOL_EXTRUSION_CUT_M,
                simplify_tolerance=CUT_SIMPLIFY_TOLERANCE_M,
                output_obj_filename=CUT_OBJ_OUTPUT_FILENAME,
                output_mtl_filename=CUT_MTL_OUTPUT_FILENAME,
                texture_filename=texture_file_name_for_mtl,
                # ... other params for step 6
                material_top=CONVERT_MATERIAL_TOP, material_bottom=CONVERT_MATERIAL_BOTTOM, material_sides=CONVERT_MATERIAL_SIDES,
                generate_vt=CONVERT_GENERATE_VT, z_tolerance=CONVERT_Z_TOLERANCE,
                show_plots=SHOW_PLOTS_ALL_STEPS, save_plots=SAVE_PLOTS_ALL_STEPS, plot_dpi=PLOT_DPI_ALL_STEPS
            )
            if success_step6:
                cut_model_generated_step6 = True
                print(f"Intermediate Textured Cut OBJ generated: {intermediate_obj_path_step6}")
            else: print("Intermediate Textured Cut OBJ generation failed.")
        except Exception as e_cut_obj: print(f"ERROR Step 6: {e_cut_obj}")

    # --- Step 6b: Transform OBJ Model ---
    # This is the path to the TRANSFORMED OBJ, e.g., .../cut_model_output/model.obj
    transformed_obj_path_step6b = final_model_output_dir / TRANSFORMED_OBJ_OUTPUT_FILENAME
    transformed_obj_created = False # Flag to track if step6b produced output

    if cut_model_generated_step6 and intermediate_obj_path_step6.exists():
        print("\n=== STEP 6b: Transforming OBJ Model ===")
        try:
            success_step6b = transform_obj_file(
                input_obj_path_str=str(intermediate_obj_path_step6),    # <--- CORRECTED
                output_obj_path_str=str(transformed_obj_path_step6b), # <--- CORRECTED
                z_additional_offset_val=TRANSFORM_Z_ADDITIONAL_OFFSET
            )
            if success_step6b and transformed_obj_path_step6b.exists():
                transformed_obj_created = True
                print(f"OBJ transformation successful. Final Output: {transformed_obj_path_step6b}")
            else: print(f"ERROR: OBJ Transformation in Step 6b failed or output file not created.")
        except Exception as e_transform_obj: print(f"ERROR during Step 6b (OBJ Transformation): {e_transform_obj}")
    else:
        print("Skipping Step 6b (OBJ Transformation): Input OBJ from Step 6 not found or Step 6 failed.")

    # --- Step 7: Generate Nav2 Map from Alpha Shape ---
    nav2_map_generated = False
    nav2_map_output_dir = output_dir / NAV2_MAP_OUTPUT_SUBDIR
    # ... (Nav2 map logic) ...
    gml_for_nav2_map_path = alpha_shape_gml_path
    if gml_for_nav2_map_path and Path(gml_for_nav2_map_path).exists():
        print("\n=== STEP 7: Generating Nav2 Map Files ===")
        nav2_map_output_dir.mkdir(parents=True, exist_ok=True)
        # ... (call generate_nav2_map) ...
        try:
            success_step7 = generate_nav2_map(
                gml_input_path_str=str(gml_for_nav2_map_path),
                output_dir_str=str(nav2_map_output_dir),
                output_map_basename=NAV2_MAP_OUTPUT_BASENAME,
                map_resolution=NAV2_MAP_RESOLUTION,
                map_padding_m=NAV2_MAP_PADDING_M
            )
            if success_step7: nav2_map_generated = True
        except Exception as e_nav_map: print(f"ERROR during Step 7 (Nav2 Map Generation): {e_nav_map}")

    # --- Step 8: Generate Gazebo World ---
    gazebo_world_generated = False
    gazebo_files_output_dir = output_dir / GAZEBO_OUTPUT_SUBDIR

    inputs_valid_for_gazebo = (
        transformed_obj_created and
        transformed_obj_path_step6b.exists() and
        intermediate_mtl_path_step6.exists() and
        (final_texture_path and Path(final_texture_path).exists()) and
        intermediate_obj_path_step6.exists()
    )

    if inputs_valid_for_gazebo:
        print("\n=== STEP 8: Generating Gazebo World Files ===")
        gazebo_files_output_dir.mkdir(parents=True, exist_ok=True)
        print(f"Gazebo files output directory: {gazebo_files_output_dir.resolve()}")
        try:
            success_step8 = create_gazebo_model_and_world(
                transformed_obj_file_path=str(transformed_obj_path_step6b),
                mtl_file_path=str(intermediate_mtl_path_step6),
                texture_file_path=str(final_texture_path),
                original_obj_for_origin_calc_path=str(intermediate_obj_path_step6),
                original_obj_crs_str=TARGET_CRS, # <<< PASS THE CRS OF THE ORIGINAL OBJ
                output_dir_str=str(gazebo_files_output_dir),
                gazebo_model_name=GAZEBO_MODEL_NAME,
                gazebo_world_filename=GAZEBO_WORLD_FILENAME
            )
            if success_step8:
                gazebo_world_generated = True
                print(f"Gazebo world and model files generated in: {gazebo_files_output_dir}")
            else:
                print("Gazebo world and model generation failed.")
        except Exception as e_gazebo:
            print(f"ERROR during Step 8 (Gazebo World Generation): {e_gazebo}")
            import traceback; traceback.print_exc()
    else:
        print("Skipping Step 8 (Gazebo World Generation): Missing necessary input files from previous steps.")

    end_time_script = time.time()
    print(f"\n--- Orchestrator Script Complete ---")
    print(f"Total execution time: {end_time_script - start_time_script:.2f} seconds")
    print(f"Main output directory: {output_dir.resolve()}")

    if transformed_obj_created:
        print(f"Final transformed OBJ model output directory: {final_model_output_dir.resolve()}")
        print(f"  Transformed OBJ: {transformed_obj_path_step6b.name}")
        print(f"  Associated MTL: {intermediate_mtl_path_step6.name}") # Still points to the original MTL name
        print(f"  Associated Texture: {Path(final_texture_path).name}")
    elif cut_model_generated_step6:
        print(f"Intermediate (untransformed) OBJ model output directory: {final_model_output_dir.resolve()}")
        print(f"  Untransformed OBJ: {intermediate_obj_path_step6.name}")
        print(f"  Associated MTL: {intermediate_mtl_path_step6.name}")
        print(f"  Associated Texture: {Path(final_texture_path).name}")

    if nav2_map_generated: print(f"Nav2 Map output directory: {nav2_map_output_dir.resolve()}")
    if gazebo_world_generated: print(f"Gazebo files output directory: {gazebo_files_output_dir.resolve()}")

if __name__ == '__main__':
    if not Path(CSV_FILE).exists():
        import pandas as pd
        print(f"Creating dummy '{CSV_FILE}' for testing.")
        dummy_data = {'latitude': [51.87101360965492], 'longitude': [7.286309500176276]}
        pd.DataFrame(dummy_data).to_csv(CSV_FILE, index=False)
    main()