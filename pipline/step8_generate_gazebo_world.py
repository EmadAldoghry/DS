# pipline/step8_generate_gazebo_world.py
import os
import shutil
from pathlib import Path
import numpy as np
import pyproj # <<< NEW IMPORT for CRS transformation

def get_obj_vertices(obj_file_path):
    """Reads an OBJ file and returns a list of its geometric vertices."""
    vertices = []
    try:
        with open(obj_file_path, 'r') as f:
            for line in f:
                if line.startswith('v '):
                    parts = line.strip().split()
                    try:
                        vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
                    except (IndexError, ValueError) as e:
                        print(f"  Warning: Could not parse vertex line: {line.strip()} - {e}")
    except FileNotFoundError:
        print(f"  Error: OBJ file for vertex extraction not found: {obj_file_path}")
        return None
    except Exception as e:
        print(f"  Error reading OBJ file {obj_file_path}: {e}")
        return None
    return vertices

def calculate_and_transform_origin_for_gazebo(
    original_obj_file_path,
    obj_crs_str, # CRS of the coordinates in the original_obj_file_path
    target_latlon_crs_str="EPSG:4326" # CRS for Gazebo's spherical_coordinates
    ):
    """
    Calculates the Gazebo world origin based on the original OBJ's bbox,
    assuming obj_crs_str for its coordinates, and transforms this origin
    to target_latlon_crs_str (typically EPSG:4326 for Gazebo).

    Returns:
        tuple: (latitude_deg, longitude_deg) in target_latlon_crs_str, or (None, None).
    """
    print(f"  Calculating Gazebo origin from bounding box of: {original_obj_file_path}")
    print(f"    Assuming original OBJ coordinates are in CRS: {obj_crs_str}")
    print(f"    Target CRS for Gazebo latitude/longitude: {target_latlon_crs_str}")

    vertices = get_obj_vertices(original_obj_file_path)

    if not vertices or len(vertices) < 3:
        print("  Error: Not enough vertices in original OBJ to calculate bounding box.")
        return None, None

    vertices_np = np.array(vertices)
    min_coords_obj_crs = np.min(vertices_np, axis=0)
    max_coords_obj_crs = np.max(vertices_np, axis=0)

    dim_x_obj_crs = max_coords_obj_crs[0] - min_coords_obj_crs[0]
    dim_y_obj_crs = max_coords_obj_crs[1] - min_coords_obj_crs[1]

    print(f"    Original OBJ BBox Min (in {obj_crs_str}): ({min_coords_obj_crs[0]:.2f}, {min_coords_obj_crs[1]:.2f})")
    print(f"    Original OBJ BBox Max (in {obj_crs_str}): ({max_coords_obj_crs[0]:.2f}, {max_coords_obj_crs[1]:.2f})")
    print(f"    Original OBJ BBox Dimensions (X, Y in {obj_crs_str}): ({dim_x_obj_crs:.2f}, {dim_y_obj_crs:.2f})")

    origin_x_obj_crs = None
    origin_y_obj_crs = None

    if dim_x_obj_crs <= dim_y_obj_crs: # X-dimension is shorter or equal
        origin_x_obj_crs = (min_coords_obj_crs[0] + max_coords_obj_crs[0]) / 2.0 # Mid-point along the X-dimension
        origin_y_obj_crs = min_coords_obj_crs[1]                          # Lower Y value
        print(f"    X-dim is shorter. Calculated origin in {obj_crs_str}: (X={origin_x_obj_crs:.2f}, Y={origin_y_obj_crs:.2f}).")
    else: # Y-dimension is shorter
        origin_x_obj_crs = min_coords_obj_crs[0]                         # Lower X value
        origin_y_obj_crs = (min_coords_obj_crs[1] + max_coords_obj_crs[1]) / 2.0  # Mid-point along the Y-dimension
        print(f"    Y-dim is shorter. Calculated origin in {obj_crs_str}: (X={origin_x_obj_crs:.2f}, Y={origin_y_obj_crs:.2f}).")

    # --- Transform the calculated origin (x,y) to latitude, longitude ---
    try:
        transformer = pyproj.Transformer.from_crs(
            pyproj.CRS.from_user_input(obj_crs_str),
            pyproj.CRS.from_user_input(target_latlon_crs_str),
            always_xy=True # Ensure (lon, lat) order for EPSG:4326 if it's the target
        )
        # The transformer output order depends on the target CRS.
        # For EPSG:4326, GIS standards often expect (lat, lon) but pyproj with always_xy=True
        # might give (lon, lat) if the CRS authority defines it that way.
        # Let's assume transformer gives (lon, lat) for EPSG:4326 target.
        transformed_lon, transformed_lat = transformer.transform(origin_x_obj_crs, origin_y_obj_crs)

        print(f"    Transformed origin to {target_latlon_crs_str}: (Lon={transformed_lon:.6f}, Lat={transformed_lat:.6f})")
        # Gazebo <spherical_coordinates> expects latitude_deg then longitude_deg
        return transformed_lat, transformed_lon # Return in (lat, lon) order for direct use

    except Exception as e:
        print(f"  ERROR: Failed to transform origin coordinates from {obj_crs_str} to {target_latlon_crs_str}: {e}")
        import traceback
        traceback.print_exc()
        return None, None


def create_gazebo_model_and_world(
    transformed_obj_file_path,
    mtl_file_path,
    texture_file_path,
    original_obj_for_origin_calc_path, # Path to the UNTRANSFORMED obj
    original_obj_crs_str,              # <<< NEW: CRS of the original OBJ
    output_dir_str,                    # Base directory for Gazebo model/world
    gazebo_model_name="pipeline_model",
    gazebo_world_filename="pipeline_world.world"):
    """
    Creates a Gazebo model directory and a world file including that model.
    The world origin (latitude, longitude) is derived from the original OBJ's bbox
    and transformed to EPSG:4326.
    """
    print(f"\n--- Generating Gazebo Model and World ---")
    output_gazebo_dir = Path(output_dir_str)
    output_gazebo_dir.mkdir(parents=True, exist_ok=True)

    # --- 1. Calculate and Transform Gazebo World Origin ---
    # The original OBJ's coordinates are assumed to be in original_obj_crs_str (e.g., EPSG:25832)
    # We want the Gazebo world's spherical_coordinates to be in EPSG:4326 (lat/lon)
    latitude_deg, longitude_deg = calculate_and_transform_origin_for_gazebo(
        original_obj_file_path=original_obj_for_origin_calc_path,
        obj_crs_str=original_obj_crs_str, # e.g., 'EPSG:25832'
        target_latlon_crs_str="EPSG:4326" # Gazebo wants WGS84 lat/lon
    )

    if latitude_deg is None or longitude_deg is None:
        print("  ERROR: Could not determine/transform Gazebo world origin. Aborting Gazebo file generation.")
        return False

    print(f"  Using Gazebo world origin (EPSG:4326) - Latitude: {latitude_deg:.7f}, Longitude: {longitude_deg:.7f}")

    # ... (rest of the function: prepare file paths, create model dir, write files) ...
    # --- 2. Prepare file paths and content ---
    try:
        with open(transformed_obj_file_path, 'r') as f: transformed_obj_content = f.read()
        with open(mtl_file_path, 'r') as f: mtl_file_content = f.read()
    except FileNotFoundError as e:
        print(f"  Error: Could not read OBJ/MTL content for Gazebo: {e}")
        return False
    except Exception as e:
        print(f"  Error reading OBJ/MTL content: {e}")
        return False

    if not Path(texture_file_path).exists():
        print(f"  Error: Texture file '{texture_file_path}' for Gazebo model not found.")
        return False

    # --- 3. Create Gazebo Model Directory Structure ---
    model_dir_path = output_gazebo_dir / gazebo_model_name
    model_dir_path.mkdir(parents=True, exist_ok=True)
    print(f"  Gazebo model directory: {model_dir_path.resolve()}")

    obj_filename_in_model_dir = Path(transformed_obj_file_path).name
    mtl_filename_in_model_dir = Path(mtl_file_path).name
    texture_filename_in_model_dir = Path(texture_file_path).name

    target_obj_path = model_dir_path / obj_filename_in_model_dir
    target_mtl_path = model_dir_path / mtl_filename_in_model_dir
    target_texture_path = model_dir_path / texture_filename_in_model_dir
    target_sdf_path = model_dir_path / "model.sdf"
    target_config_path = model_dir_path / "model.config"

    # --- 4. Write/Copy files to Gazebo model directory ---
    try:
        with open(target_obj_path, "w") as f: f.write(transformed_obj_content)
        with open(target_mtl_path, "w") as f: f.write(mtl_file_content)
        shutil.copyfile(texture_file_path, target_texture_path)
        print(f"    Copied/Wrote OBJ, MTL, Texture to {model_dir_path}")
    except Exception as e:
        print(f"  Error writing/copying model files: {e}")
        return False

    # --- 5. Create model.config ---
    model_config_content = f"""<?xml version="1.0"?>
<model>
  <name>{gazebo_model_name}</name>
  <version>1.0</version>
  <sdf version="1.10">model.sdf</sdf>
  <author>
    <name>Pipeline User</name>
    <email>user@example.com</email>
  </author>
  <description>
    A model generated by the pipeline.
  </description>
</model>"""
    try:
        with open(target_config_path, "w") as f: f.write(model_config_content)
        print(f"    Created: {target_config_path.name}")
    except Exception as e:
        print(f"  Error writing model.config: {e}")
        return False

    # --- 6. Create model.sdf ---
    model_sdf_content = f"""<sdf version='1.10'>
<model name='{gazebo_model_name}'>
  <static>true</static>
  <link name='link'>
    <visual name='visual'>
      <geometry>
        <mesh>
          <uri>{obj_filename_in_model_dir}</uri>
          <scale>1 1 1</scale>
        </mesh>
      </geometry>
    </visual>
    <collision name='collision'>
      <geometry>
        <mesh>
          <uri>{obj_filename_in_model_dir}</uri>
          <scale>1 1 1</scale>
        </mesh>
      </geometry>
    </collision>
    <inertial>
        <mass>1000</mass>
        <inertia>
          <ixx>100</ixx> <ixy>0</ixy> <ixz>0</ixz>
          <iyy>100</iyy> <iyz>0</iyz> <izz>100</izz>
        </inertia>
    </inertial>
  </link>
</model>
</sdf>"""
    try:
        with open(target_sdf_path, "w") as f: f.write(model_sdf_content)
        print(f"    Created: {target_sdf_path.name}")
    except Exception as e:
        print(f"  Error writing model.sdf: {e}")
        return False

    # --- 7. Create Gazebo World File ---
    world_file_path = output_gazebo_dir / gazebo_world_filename
    world_content = f"""<sdf version='1.10'>
<world name='default'>
  <plugin name='gz::sim::systems::Physics' filename='gz-sim-physics-system'/>
  <plugin name='gz::sim::systems::UserCommands' filename='gz-sim-user-commands-system'/>
  <plugin name='gz::sim::systems::SceneBroadcaster' filename='gz-sim-scene-broadcaster-system'/>
  <plugin name='gz::sim::systems::Contact' filename='gz-sim-contact-system'/>
  <plugin
    filename="gz-sim-sensors-system"
    name="gz::sim::systems::Sensors">
    <render_engine>ogre2</render_engine>
  </plugin>
  <plugin
    filename="gz-sim-imu-system"
    name="gz::sim::systems::Imu"/>
  <plugin
    filename="gz-sim-navsat-system"
    name="gz::sim::systems::NavSat"/>

  <physics name='1ms' type='ignored'>
    <max_step_size>0.001</max_step_size>
    <real_time_factor>1</real_time_factor>
    <real_time_update_rate>1000</real_time_update_rate>
  </physics>
  <gravity>0 0 -9.81</gravity>
  <magnetic_field>5.5645e-06 2.28758e-05 -4.23884e-05</magnetic_field>
  <atmosphere type='adiabatic'/>
  <scene>
    <ambient>0.4 0.4 0.4 1</ambient>
    <background>0.7 0.7 0.7 1</background>
    <shadows>true</shadows>
  </scene>

  <spherical_coordinates>
    <surface_model>EARTH_WGS84</surface_model>
    <world_frame_orientation>ENU</world_frame_orientation>
    <latitude_deg>{latitude_deg if latitude_deg is not None else 0.0:.7f}</latitude_deg>
    <longitude_deg>{longitude_deg if longitude_deg is not None else 0.0:.7f}</longitude_deg>
    <elevation>0</elevation>
    <heading_deg>0</heading_deg>
  </spherical_coordinates>

  <light name='sun' type='directional'>
    <pose>0 0 10 0 0 0</pose>
    <cast_shadows>true</cast_shadows>
    <intensity>0.8</intensity>
    <direction>-0.5 0.1 -0.9</direction>
    <diffuse>0.8 0.8 0.8 1</diffuse>
    <specular>0.2 0.2 0.2 1</specular>
  </light>

  <model name='ground_plane'>
    <static>true</static>
    <link name='link'>
      <collision name='collision'>
        <geometry><plane><normal>0 0 1</normal><size>200 200</size></plane></geometry>
      </collision>
      <visual name='visual'>
        <geometry><plane><normal>0 0 1</normal><size>200 200</size></plane></geometry>
        <material><ambient>0.7 0.7 0.7 1</ambient><diffuse>0.7 0.7 0.7 1</diffuse><specular>0.7 0.7 0.7 1</specular></material>
      </visual>
    </link>
  </model>

  <include>
    <uri>{gazebo_model_name}</uri>
    <name>{gazebo_model_name}_instance</name>
    <pose>0 0 0 0 0 0</pose>
  </include>

</world>
</sdf>
"""
    try:
        with open(world_file_path, "w") as f: f.write(world_content)
        print(f"    Created Gazebo world file: {world_file_path.resolve()}")
        print(f"  To use this world and model, ensure GAZEBO_MODEL_PATH includes '{output_gazebo_dir.resolve()}'")
        return True
    except Exception as e:
        print(f"  Error writing Gazebo world file: {e}")
        return False


if __name__ == "__main__":
    # Example for standalone testing
    test_base_output_dir = Path("..") / "output_project"
    test_transformed_obj = test_base_output_dir / "cut_model_output" / "model.obj"
    test_mtl_file = test_base_output_dir / "cut_model_output" / "final_cut_road_model.mtl"
    test_texture_file = test_base_output_dir / "cut_model_output" / "road_texture.png"
    test_original_obj_for_origin = test_base_output_dir / "cut_model_output" / "final_cut_road_model.obj"
    test_original_obj_crs = "EPSG:25832" # Manually specify for testing
    test_gazebo_output_dir = test_base_output_dir / "gazebo_output_transformed_origin"

    print(f"--- Testing Gazebo World Generation with Transformed Origin ---")
    files_exist = True
    for f_path in [test_transformed_obj, test_mtl_file, test_texture_file, test_original_obj_for_origin]:
        if not f_path.exists():
            print(f"ERROR: Test input file not found: {f_path}")
            files_exist = False

    if files_exist:
        # Create a dummy original OBJ if it doesn't exist for testing the origin calculation
        if not test_original_obj_for_origin.exists():
            print(f"Creating dummy original OBJ for origin test: {test_original_obj_for_origin}")
            with open(test_original_obj_for_origin, "w") as f:
                # Example vertices in EPSG:25832 (UTM Zone 32N)
                # A small rectangle around (X=350000, Y=5600000)
                f.write("v 350000.0 5600000.0 0.0\n")
                f.write("v 350010.0 5600000.0 0.0\n") # X-dim = 10m
                f.write("v 350010.0 5600005.0 0.0\n") # Y-dim = 5m
                f.write("v 350000.0 5600005.0 0.0\n")
                # Add some more vertices to make it a "solid" for bbox
                f.write("v 350000.0 5600000.0 1.0\n")
                f.write("v 350010.0 5600000.0 1.0\n")
                f.write("v 350010.0 5600005.0 1.0\n")
                f.write("v 350000.0 5600005.0 1.0\n")
                f.write("f 1 2 3 4\n")
                f.write("f 5 6 7 8\n")


        success = create_gazebo_model_and_world(
            transformed_obj_file_path=str(test_transformed_obj),
            mtl_file_path=str(test_mtl_file),
            texture_file_path=str(test_texture_file),
            original_obj_for_origin_calc_path=str(test_original_obj_for_origin),
            original_obj_crs_str=test_original_obj_crs, # Pass the CRS of the original OBJ
            output_dir_str=str(test_gazebo_output_dir),
            gazebo_model_name="road_segment_transformed_origin",
            gazebo_world_filename="road_segment_transformed_origin.world"
        )
        if success: print(f"Gazebo world (transformed origin) test successful. Output in: {test_gazebo_output_dir}")
        else: print(f"Gazebo world (transformed origin) test failed.")
    else: print("Skipping Gazebo world (transformed origin) test due to missing input files.")