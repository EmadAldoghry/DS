# -*- coding: utf-8 -*-
# step7_generate_nav2_map.py

import geopandas as gpd
import cv2
import numpy as np
import yaml
import math
from shapely.geometry import Polygon, MultiPolygon
from pathlib import Path
import traceback

def extract_polygons_from_gml(gml_path):
    """
    Extracts polygon vertices from a GML file.
    Returns a list, where each element is a list of (x, y) vertex tuples for a polygon.
    Handles both Polygon and MultiPolygon geometries.
    """
    all_polygons_vertices_world = []
    try:
        gdf = gpd.read_file(gml_path)
    except Exception as e:
        print(f"  Error reading GML file {gml_path}: {e}")
        traceback.print_exc()
        return None # Return None on failure

    if gdf.empty:
        print(f"  Warning: No features found in GML file: {gml_path}")
        return [] # Return empty list if no features

    # print(f"  GML Coordinate Reference System: {gdf.crs}") # Optional debug

    for geometry in gdf.geometry:
        if geometry is None or geometry.is_empty: continue
        if isinstance(geometry, Polygon):
            exterior_coords = list(geometry.exterior.coords)
            all_polygons_vertices_world.append(exterior_coords)
        elif isinstance(geometry, MultiPolygon):
            for poly in geometry.geoms: # Use geoms for newer shapely/geopandas
                if poly is None or poly.is_empty: continue
                exterior_coords = list(poly.exterior.coords)
                all_polygons_vertices_world.append(exterior_coords)
        # else: print(f"  Skipping non-polygon geometry type: {geometry.geom_type}") # Less verbose

    if not all_polygons_vertices_world:
        print(f"  Warning: No valid Polygon/MultiPolygon vertices extracted from {gml_path}")

    return all_polygons_vertices_world


def create_map_from_polygons_list(list_of_polygons_vertices_world, # List of [ [(x,y),...], [(x,y),...] ]
                                  map_resolution,         # Meters per pixel (e.g., 0.05)
                                  output_pgm_path_str,    # Full path for PGM
                                  output_yaml_path_str,   # Full path for YAML
                                  padding_m=10.0):
    """ Creates PGM and YAML map files from polygon vertex lists. """

    if not list_of_polygons_vertices_world:
        print("  Error: No polygon vertices provided to create map.")
        return False

    # 1. Determine map dimensions and origin
    all_vertices = [v for poly_verts in list_of_polygons_vertices_world for v in poly_verts]
    if not all_vertices: print("  Error: No vertices found."); return False

    min_x_world = min(v[0] for v in all_vertices); max_x_world = max(v[0] for v in all_vertices)
    min_y_world = min(v[1] for v in all_vertices); max_y_world = max(v[1] for v in all_vertices)

    map_origin_for_yaml = [min_x_world - padding_m, min_y_world - padding_m, 0.0]
    map_width_m = (max_x_world + padding_m) - map_origin_for_yaml[0]
    map_height_m = (max_y_world + padding_m) - map_origin_for_yaml[1]
    map_width_px = int(math.ceil(map_width_m / map_resolution))
    map_height_px = int(math.ceil(map_height_m / map_resolution))

    if map_width_px <= 0 or map_height_px <= 0:
        print(f"  Error: Invalid map dimensions calculated ({map_width_px}x{map_height_px}). Check input coordinates/padding.")
        return False

    print(f"    Map dimensions: {map_width_px}px width, {map_height_px}px height")
    print(f"    Map origin (YAML): {map_origin_for_yaml}")

    # 2. Create blank image (0=occupied/black)
    image = np.zeros((map_height_px, map_width_px), dtype=np.uint8)

    # 3. Draw filled polygons (255=free/white)
    polygons_drawn = 0
    for polygon_vertices_world in list_of_polygons_vertices_world:
        polygon_vertices_px = []
        for wx, wy in polygon_vertices_world:
            px = int((wx - map_origin_for_yaml[0]) / map_resolution)
            py = map_height_px - 1 - int((wy - map_origin_for_yaml[1]) / map_resolution)
            polygon_vertices_px.append([px, py])
        if len(polygon_vertices_px) >= 3: # Need at least 3 points for a polygon
            try:
                polygon_np_array = np.array([polygon_vertices_px], dtype=np.int32)
                cv2.fillPoly(image, [polygon_np_array], 255)
                polygons_drawn += 1
            except Exception as draw_err:
                print(f"    Warning: Failed to draw a polygon: {draw_err}")
        # else: print("    Skipping polygon with < 3 vertices.") # Less verbose

    if polygons_drawn == 0:
        print("  Warning: No polygons were successfully drawn onto the map image.")
        # Continue to save the (likely black) map, but it might not be useful.

    # 4. Save PGM
    output_pgm_path = Path(output_pgm_path_str)
    try:
        cv2.imwrite(str(output_pgm_path), image)
        print(f"    Saved PGM map: {output_pgm_path.name}")
    except Exception as e_pgm:
        print(f"  Error saving PGM map to {output_pgm_path}: {e_pgm}")
        traceback.print_exc()
        return False

    # 5. Create YAML file
    output_yaml_path = Path(output_yaml_path_str)
    map_yaml_data = {
        'image': output_pgm_path.name, # Use relative filename in YAML
        'resolution': map_resolution,
        'origin': map_origin_for_yaml,
        'negate': 0,
        'occupied_thresh': 0.65,
        'free_thresh': 0.25
    }
    try:
        with open(output_yaml_path, 'w') as f:
            yaml.dump(map_yaml_data, f, sort_keys=False, default_flow_style=None) # Use block style
        print(f"    Saved YAML map metadata: {output_yaml_path.name}")
        return True # Success
    except Exception as e_yaml:
        print(f"  Error saving YAML map metadata to {output_yaml_path}: {e_yaml}")
        traceback.print_exc()
        # Attempt to clean up PGM if YAML fails? Optional.
        # if output_pgm_path.exists(): output_pgm_path.unlink()
        return False

# --- Main function for pipeline integration ---
def generate_nav2_map(gml_input_path_str,
                      output_dir_str,
                      output_map_basename, # e.g., "alpha_shape_map" -> creates .pgm & .yaml
                      map_resolution,
                      map_padding_m):
    """
    Main function for Step 7: Creates Nav2 map files from a GML file.
    Returns True on success, False otherwise.
    """
    print(f"\n--- Generating Nav2 Map Files ---")
    input_gml_path = Path(gml_input_path_str)
    output_dir = Path(output_dir_str)
    output_dir.mkdir(parents=True, exist_ok=True) # Ensure output dir exists

    # Define output paths
    output_pgm_path = output_dir / f"{output_map_basename}.pgm"
    output_yaml_path = output_dir / f"{output_map_basename}.yaml"

    print(f"  Input GML: {input_gml_path.name}")
    print(f"  Output Dir: {output_dir}")
    print(f"  Output Base Name: {output_map_basename}")
    print(f"  Map Resolution: {map_resolution} m/pixel")
    print(f"  Map Padding: {map_padding_m} m")

    # 1. Extract polygon vertices
    list_of_polygons = extract_polygons_from_gml(input_gml_path)

    if list_of_polygons is None: # Check for None which indicates read error
        print("  Failed to extract polygons due to GML read error.")
        return False
    elif not list_of_polygons: # Empty list means no polygons found
        print("  No polygons extracted from GML. Cannot generate map.")
        return False

    # 2. Create the map files
    success = create_map_from_polygons_list(
        list_of_polygons,
        map_resolution,
        str(output_pgm_path),
        str(output_yaml_path),
        padding_m=map_padding_m
    )

    if success:
        print(f"  Nav2 map generation successful.")
    else:
        print(f"  Nav2 map generation failed.")

    return success

# --- Example Usage (for testing this module independently) ---
if __name__ == '__main__':
    print("--- Testing Step 7: Generate Nav2 Map ---")
    # Assume Step 4 ran and created this file in output_project
    test_gml_path = "../output_project/calculated_alpha_shape.gml" # Adjust path as needed relative to this script
    test_output_directory = "../output_project/nav2_map_output" # Save test output separately
    test_map_base = "alpha_shape_costmap"
    test_resolution = 0.05
    test_padding = 5.0

    if Path(test_gml_path).exists():
        generate_nav2_map(
            gml_input_path_str=test_gml_path,
            output_dir_str=test_output_directory,
            output_map_basename=test_map_base,
            map_resolution=test_resolution,
            map_padding_m=test_padding
        )
    else:
        print(f"Test skipped: Input GML not found at {test_gml_path}")

    print("--- Test Finished ---")