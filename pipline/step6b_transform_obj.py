# pipline/step6b_transform_obj.py
import os
import sys
import io # For string-based OBJ processing
from pathlib import Path

# --- Configuration ---
# Z_ADDITIONAL_OFFSET is passed as a function argument
# FLOAT_PRECISION is implicitly handled by f-string formatting to .6f

def _transform_obj_content(obj_content: str, z_additional_offset_val: float) -> str | None:
    """
    Transforms vertex coordinates in an OBJ string.
    - Calculates the 2D bounding box (min/max X and Y).
    - Determines the shorter side of this bounding box.
    - Sets the new origin such that:
        - If X-side is shorter/equal: new origin X is at the midpoint of the original X-range,
                                     new origin Y is at the original min_y.
        - If Y-side is shorter: new origin X is at the original min_x,
                                new origin Y is at the midpoint of the original Y-range.
    - Subtracts these calculated offsets from all vertex X and Y coords.
    - Finds the minimum Z value (min_z) across all vertices.
    - Shifts all Z coordinates so that the new minimum Z becomes 0.0 + z_additional_offset_val.
    - Replaces header comments.
    - Preserves all other data (vt, vn, f, etc.).

    Args:
        obj_content: The original OBJ file content as a string.
        z_additional_offset_val: An additional offset to apply to all Z coordinates
                                 after the initial shift to make min_z = 0.

    Returns:
        The transformed OBJ file content as a string, or None if an error occurs.
    """

    vertices_data = [] # To store {'x': val, 'y': val, 'z': val, 'original_line': line}
    other_lines_after_vertices = []
    original_header_non_comments = []
    vertex_lines_processed = False

    min_x_orig, max_x_orig = float('inf'), float('-inf')
    min_y_orig, max_y_orig = float('inf'), float('-inf')
    min_z_orig = float('inf')

    # --- Pass 1: Read lines, parse vertices, find min/max X/Y and min_z, store other lines ---
    for line in obj_content.splitlines():
        stripped_line = line.strip()
        if not stripped_line:
            if vertex_lines_processed:
                other_lines_after_vertices.append(line)
            else:
                original_header_non_comments.append(line)
            continue

        if stripped_line.startswith('v '):
            vertex_lines_processed = True
            try:
                parts = stripped_line.split()
                x = float(parts[1])
                y = float(parts[2])
                z = float(parts[3])
                vertices_data.append({'x': x, 'y': y, 'z': z, 'original_line': line})
                min_x_orig = min(min_x_orig, x)
                max_x_orig = max(max_x_orig, x)
                min_y_orig = min(min_y_orig, y)
                max_y_orig = max(max_y_orig, y)
                min_z_orig = min(min_z_orig, z) # Find overall minimum Z
            except (IndexError, ValueError) as e:
                print(f"  Warning: Could not parse vertex line, skipping transformation for it: '{line}' - Error: {e}")
                # Decide whether to append or skip. Let's append to other_lines if parsing fails.
                other_lines_after_vertices.append(line)
        elif not vertex_lines_processed:
             if not stripped_line.startswith('#'):
                 original_header_non_comments.append(line)
        else: # Lines after vertices start (vt, vn, f, s, usemtl, etc.)
            other_lines_after_vertices.append(line)

    if not vertices_data:
        print("  Error: No geometric vertices ('v' lines) found. Cannot perform transformations.")
        return None # Indicate failure for transformation logic

    # Check if bounding box could be determined
    if min_x_orig == float('inf') or min_y_orig == float('inf') or \
       max_x_orig == float('-inf') or max_y_orig == float('-inf') or \
       min_z_orig == float('inf'):
         print("  Error: Could not determine bounding box or min_z (perhaps only malformed vertices?). Cannot transform.")
         return None

    print(f"  Original Bounding Box: X=[{min_x_orig:.6f}, {max_x_orig:.6f}], Y=[{min_y_orig:.6f}, {max_y_orig:.6f}]")
    print(f"  Original Min Z: {min_z_orig:.6f}")

    # --- Calculate X, Y offsets based on the shortest side of the 2D bounding box ---
    bb_width = max_x_orig - min_x_orig
    bb_height = max_y_orig - min_y_orig

    offset_x_translation = 0.0
    offset_y_translation = 0.0

    if bb_width <= bb_height: # X-dimension is shorter or equal
        offset_x_translation = (min_x_orig + max_x_orig) / 2.0
        offset_y_translation = min_y_orig
        print(f"  Info: Bbox X-dim ({bb_width:.6f}) <= Y-dim ({bb_height:.6f}). Origin X at X-mid, Y at Y-min.")
    else: # Y-dimension is shorter
        offset_x_translation = min_x_orig
        offset_y_translation = (min_y_orig + max_y_orig) / 2.0
        print(f"  Info: Bbox Y-dim ({bb_height:.6f}) < X-dim ({bb_width:.6f}). Origin X at X-min, Y at Y-mid.")

    # Z offset is determined by min_z_orig to bring the base to Z=0, then add z_additional_offset_val
    z_shift_to_ground = -min_z_orig
    print(f"  Calculated X,Y offsets for new origin: dx={-offset_x_translation:.6f}, dy={-offset_y_translation:.6f}")
    print(f"  Z-coords will be shifted by {z_shift_to_ground:.6f} (to make min_z=0.0).")
    if z_additional_offset_val != 0.0:
        print(f"  Applying additional Z offset: {z_additional_offset_val:.6f}")
    final_min_z_target = 0.0 + z_additional_offset_val


    # --- Pass 2: Build the output string ---
    output_buffer = io.StringIO()

    # Write the new header comments
    output_buffer.write("# 3D Model: model.obj (Transformed)\n")
    output_buffer.write("# Source Polygon File: cropped_wfs_features_final.xml (Example, adjust if known)\n")
    output_buffer.write("# Texture Source: WMS https://www.wms.nrw.de/geobasis/wms_nw_dop Layer nw_dop_rgb (Example)\n")
    output_buffer.write("# Base Shape: Merged Polygon(s) Exterior(s) (Example)\n")
    output_buffer.write("# Coordinate System of Vertices: Local (derived from EPSG:25832, then transformed).\n")
    output_buffer.write("# X,Y origin at midpoint of shortest 2D bbox side (or corresponding edge).\n")
    output_buffer.write(f"# Z coordinates shifted so that the minimum Z value becomes {final_min_z_target:.6f}.\n")

    # Write original non-comment header lines (like mtllib, o)
    for line in original_header_non_comments:
         output_buffer.write(line + "\n")

    if vertices_data and original_header_non_comments and original_header_non_comments[-1].strip() != "":
        output_buffer.write("\n") # Ensure a blank line before vertices if header didn't end with one

    output_buffer.write("# Vertices (X Y Z)\n")
    # Write transformed vertices
    actual_new_min_z = float('inf')
    for v_data in vertices_data:
        new_x = v_data['x'] - offset_x_translation
        new_y = v_data['y'] - offset_y_translation
        new_z = v_data['z'] + z_shift_to_ground + z_additional_offset_val # Shift Z
        actual_new_min_z = min(actual_new_min_z, new_z)
        output_buffer.write(f"v {new_x:.6f} {new_y:.6f} {new_z:.6f}\n")
    
    print(f"  New Min Z after transformation: {actual_new_min_z:.6f} (Targeted: {final_min_z_target:.6f})")


    # Ensure a blank line separates vertices from other data if both exist
    if vertices_data and other_lines_after_vertices:
        # Check if the buffer currently ends with a newline. If so, we might need another
        # if the last line written wasn't itself a blank line.
        # A simpler check: if the last char isn't \n, add one. Then if the second to last isn't \n, add another.
        # Or, more robustly, ensure there's a blank line before starting the next section.
        # Current logic: if vertices were written, and other lines follow, add a newline.
        # This might result in one too many if other_lines_after_vertices starts with blank lines.
        # The splitlines() and join with \n at the end handles this better.
        # Let's ensure the vertex section ends with a newline, and the next section starts correctly.
        if not output_buffer.getvalue().endswith("\n\n") and not output_buffer.getvalue().endswith("\r\n\r\n"):
             if not output_buffer.getvalue().endswith("\n"): output_buffer.write("\n") # Ensure at least one
             if not other_lines_after_vertices[0].strip() == "": # if next part is not blank
                output_buffer.write("\n") # Add blank line separator

    for line in other_lines_after_vertices:
        output_buffer.write(line + "\n") # Ensure each line from list ends with a newline

    return output_buffer.getvalue()


def transform_obj_file(input_obj_path_str: str, output_obj_path_str: str, z_additional_offset_val: float) -> bool:
    """
    Reads an OBJ file, transforms its vertex coordinates, and writes a new OBJ file.
    Uses the _transform_obj_content function for the core logic.

    Args:
        input_obj_path_str: Path to the input OBJ file.
        output_obj_path_str: Path to save the transformed OBJ file.
        z_additional_offset_val: Additional Z offset to apply.

    Returns:
        True if successful, False otherwise.
    """
    print(f"Reading OBJ file from: {input_obj_path_str}")
    try:
        with open(input_obj_path_str, 'r', encoding='utf-8') as infile:
            original_obj_data = infile.read()
    except FileNotFoundError:
        print(f"  Error: Input file '{input_obj_path_str}' not found.")
        return False
    except Exception as e:
        print(f"  An error occurred while reading the file '{input_obj_path_str}': {e}")
        return False

    if not original_obj_data.strip():
        print("  Input OBJ file is empty. Nothing to transform.")
        # Write an empty file or copy? Let's write an empty transformed file.
        try:
            with open(output_obj_path_str, 'w', encoding='utf-8') as outfile:
                outfile.write("# Original file was empty.\n")
            print(f"  Wrote empty placeholder to {output_obj_path_str}")
            return True # Technically not a failure of transformation itself
        except Exception as e_write:
            print(f"  Error writing empty output file: {e_write}")
            return False

    print("\n  --- Performing OBJ Transformation ---")
    transformed_obj_data = _transform_obj_content(original_obj_data, z_additional_offset_val)

    if transformed_obj_data is None:
        print("  OBJ content transformation failed. No output file generated.")
        # Attempt to copy original if transformation logic fails but file was readable
        # This is a design choice: if transform fails, what to do?
        # Old script copied original if no vertices. New logic returns None.
        # Let's say if _transform_obj_content returns None, it's a critical failure for this step.
        return False

    print(f"\n  --- Writing transformed OBJ to: {output_obj_path_str} ---")
    try:
        # Create output directory if it doesn't exist
        output_dir = os.path.dirname(output_obj_path_str)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            print(f"  Created output directory: {output_dir}")

        with open(output_obj_path_str, 'w', encoding='utf-8') as outfile:
            outfile.write(transformed_obj_data)
        print("  Transformation writing complete.")
        return True
    except Exception as e:
        print(f"  An error occurred while writing transformed file '{output_obj_path_str}': {e}")
        return False

if __name__ == "__main__":
    # Example for standalone testing (adjust paths as needed)
    # This example assumes the script is run from within the 'pipline' directory.
    
    # Relative path setup similar to the original script for testing
    script_dir = Path(__file__).parent
    base_output_dir = script_dir.parent / "output_project" / "cut_model_output"
    base_output_dir.mkdir(parents=True, exist_ok=True)
    
    dummy_input_obj_path = base_output_dir / "final_cut_road_model.obj"
    # Output name changed to model.obj as per the new script's __main__ block
    dummy_output_obj_path = base_output_dir / "model.obj" 
    default_z_offset = 0.05 # Example: raise the model 5cm after grounding

    if not dummy_input_obj_path.exists():
        print(f"Creating dummy OBJ file for testing: {dummy_input_obj_path}")
        with open(dummy_input_obj_path, "w") as f:
            f.write("# Dummy OBJ file for testing step6b_transform_obj.py\n")
            f.write("mtllib final_cut_road_model.mtl\n")
            f.write("o TestObject\n")
            f.write("v 10.0 20.0 5.0\n")
            f.write("v 11.0 20.0 5.0\n")
            f.write("v 11.0 21.0 5.0\n")
            f.write("v 10.0 21.0 5.0\n")
            f.write("v 10.0 20.0 6.0\n")
            f.write("v 11.0 20.0 6.0\n")
            f.write("v 11.0 21.0 6.0\n")
            f.write("v 10.0 21.0 6.0\n")
            f.write("vt 0.0 0.0\n")
            f.write("vt 1.0 0.0\n")
            f.write("vt 1.0 1.0\n")
            f.write("vt 0.0 1.0\n")
            f.write("vn 0.0 0.0 -1.0\n")
            f.write("vn 0.0 0.0 1.0\n")
            f.write("s off\n")
            f.write("usemtl RoadBottom\n")
            # Note: New script doesn't reverse face winding order, so use standard winding.
            f.write("f 1/1/1 2/2/1 3/3/1 4/4/1\n") # Bottom face
            f.write("usemtl RoadSurface\n")
            f.write("f 5/1/2 8/4/2 7/3/2 6/2/2\n") # Top face
    
    print(f"Attempting to transform: {dummy_input_obj_path} -> {dummy_output_obj_path}")
    print(f"Using Z additional offset: {default_z_offset}")

    success = transform_obj_file(
        str(dummy_input_obj_path), 
        str(dummy_output_obj_path),
        z_additional_offset_val=default_z_offset
    )
    if success:
        print(f"Standalone test transformation successful: {dummy_output_obj_path}")
    else:
        print(f"Standalone test transformation FAILED.")
        sys.exit(1) # Indicate failure for test runs