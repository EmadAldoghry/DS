# -*- coding: utf-8 -*-
# step5_generate_texture.py
from pathlib import Path
import fiona
import rasterio
import rasterio.mask
from rasterio.io import MemoryFile
from rasterio.transform import from_bounds
from shapely.geometry import shape, mapping
from shapely.ops import transform as shapely_transform, unary_union
import numpy as np
from PIL import Image
import pyproj
import traceback
import requests
from io import BytesIO
import geopandas as gpd

# Use the shared plotting helper if available
from helpers import plot_geometries, plot_image_array

def generate_texture_from_polygon(
    polygon_gml_path_str,
    output_dir_str,             # <<< Directory where the final OBJ/MTL/PNG will reside
    output_texture_filename,    # <<< Just the filename for the texture (e.g., "base_texture.png")
    wms_url, wms_layer, wms_version, wms_format,
    wms_width, wms_height, target_wms_crs_str,
    wms_bbox_padding, polygon_crs_fallback_str,
    fill_color_rgb,
    show_plots=True, save_plots=True, plot_dpi=150):
    """
    Reads polygons from GML, downloads WMS, crops, and saves texture PNG
    directly into the specified output_dir_str.
    Returns the full path to the saved texture file or None on failure.
    """
    print("\n--- Running: Texture Generation ---")
    polygon_path = Path(polygon_gml_path_str)
    output_dir = Path(output_dir_str) # Use the directory passed from orchestrator
    output_dir.mkdir(parents=True, exist_ok=True)
    # Construct the full output path for the texture
    output_texture_path = output_dir / output_texture_filename
    target_crs_obj = pyproj.CRS.from_user_input(target_wms_crs_str)

    # Create a subdirectory *within* the main output for texture-specific plots
    texture_plot_dir = output_dir / "texture_plots"
    if save_plots: texture_plot_dir.mkdir(parents=True, exist_ok=True)

    if not polygon_path.is_file():
        print(f"Error: Polygon GML file not found: {polygon_path}"); return None

    # --- Step 1: Read Polygons & Reproject ---
    print(f"  Step 1: Reading Polygons from {polygon_path.name}...")
    geometries_in_target_crs = []
    input_crs_obj = None # Define outside try block
    try:
        # Use GeoPandas for easier reading and CRS handling
        gdf = gpd.read_file(polygon_path)
        if gdf.empty: print("  Warning: Polygon GML is empty."); return None

        input_crs_obj_gml = gdf.crs
        if input_crs_obj_gml:
             input_crs_obj = input_crs_obj_gml # Keep original CRS for plotting
             if not input_crs_obj.equals(target_crs_obj):
                  print(f"    Reprojecting source polygons from {input_crs_obj.srs} to {target_crs_obj.srs}...")
                  gdf = gdf.to_crs(target_crs_obj)
             else: print(f"    Source polygons already in target CRS {target_crs_obj.srs}.")
        else:
             print(f"    Warning: Polygon GML has no CRS. Assuming fallback: {polygon_crs_fallback_str}")
             try:
                  input_crs_obj = pyproj.CRS.from_user_input(polygon_crs_fallback_str)
                  gdf.crs = input_crs_obj # Assign fallback
                  if not input_crs_obj.equals(target_crs_obj):
                       print(f"    Reprojecting source polygons from fallback {input_crs_obj.srs} to {target_crs_obj.srs}...")
                       gdf = gdf.to_crs(target_crs_obj)
                  else: print(f"    Fallback CRS matches target CRS {target_crs_obj.srs}.")
             except Exception as fallback_err: print(f"Error setting/using fallback CRS: {fallback_err}"); return None

        # Extract valid geometries after potential reprojection
        geoms_for_processing = []
        for geom in gdf.geometry:
            if geom is None or geom.is_empty: continue
            geom_type = geom.geom_type
            if geom_type in ['Polygon', 'MultiPolygon']:
                cleaned = geom if geom.is_valid else geom.buffer(0)
                if cleaned.is_valid and not cleaned.is_empty and cleaned.geom_type in ['Polygon', 'MultiPolygon']:
                     geoms_for_processing.append(cleaned)
        if not geoms_for_processing: print("Error: No valid Polygon/MultiPolygon found after reading/reprojection."); return None
        print(f"    Found {len(geoms_for_processing)} valid Polygon/MultiPolygon features for texture base.")

        # Plot original and reprojected shapes (optional)
        # Need to handle plotting logic if gdf was reprojected vs original
        # For simplicity, just plot the final geoms_for_processing
        plot_geometries(geoms_for_processing, target_crs_obj,
                        f"Step 5 Pre-Merge: Input Polygons for Texture (Target CRS)",
                        texture_plot_dir, "texture_plot_01_input_reproj", # Save plots in subfolder
                        show_plots=show_plots, save_plots=save_plots, plot_dpi=plot_dpi)

    except Exception as e: print(f"Error in Step 1 (Read GML for Texture): {e}"); traceback.print_exc(); return None

    # --- Step 2: Merge Polygons (for WMS BBOX calculation) ---
    print("  Step 2: Merging geometries for BBOX...")
    merged_geom_for_bbox = None
    try:
        merged_geom_for_bbox = unary_union(geoms_for_processing).buffer(0)
        if merged_geom_for_bbox.is_empty or not merged_geom_for_bbox.is_valid: print("Error: Merged geometry is invalid/empty."); return None
        print(f"    Merged geometry type for BBOX: {merged_geom_for_bbox.geom_type}")
        plot_geometries(merged_geom_for_bbox, target_crs_obj,
                        "Step 5: Merged Polygon for Texture BBOX",
                        texture_plot_dir, "texture_plot_02_merged",
                        show_plots=show_plots, save_plots=save_plots, plot_dpi=plot_dpi)
    except Exception as e: print(f"Error in Step 2 (Merge for Texture BBOX): {e}"); traceback.print_exc(); return None

    # --- Step 3: Download WMS ---
    print(f"  Step 3: Downloading WMS Layer '{wms_layer}'...")
    # ... (Keep WMS download logic exactly as before - creates wms_image_array, wms_transform, wms_meta) ...
    wms_image_array, wms_transform, wms_meta, wms_bounds_tuple = None, None, None, None
    try:
        min_x, min_y, max_x, max_y = merged_geom_for_bbox.bounds
        wms_bbox = (min_x - wms_bbox_padding, min_y - wms_bbox_padding, max_x + wms_bbox_padding, max_y + wms_bbox_padding)
        wms_bounds_tuple = wms_bbox
        wms_params = {'service': 'WMS', 'request': 'GetMap', 'version': wms_version, 'layers': wms_layer, 'styles': '',
                      'crs': target_wms_crs_str, 'bbox': f"{wms_bbox[0]},{wms_bbox[1]},{wms_bbox[2]},{wms_bbox[3]}",
                      'width': str(wms_width), 'height': str(wms_height), 'format': wms_format}
        response = requests.get(wms_url, params=wms_params, timeout=180); response.raise_for_status()
        print(f"    WMS Response Status: {response.status_code}, Content-Type: {response.headers.get('Content-Type')}")
        with Image.open(BytesIO(response.content)) as img:
            target_mode = 'RGB'; original_mode = img.mode
            if img.mode != target_mode: img = img.convert(target_mode) # Simplify conversion
            wms_image_array = np.array(img)
            if wms_image_array.ndim == 3: wms_image_array = np.transpose(wms_image_array, (2, 0, 1))
            elif wms_image_array.ndim == 2: wms_image_array = np.stack([wms_image_array]*3, axis=0)
        if wms_image_array is None or wms_image_array.ndim != 3 or wms_image_array.shape[0] != 3:
             raise ValueError(f"Failed to process WMS image into 3-band array (shape: {wms_image_array.shape if wms_image_array is not None else 'None'})")
        wms_transform = from_bounds(*wms_bbox, wms_width, wms_height)
        wms_meta = {'driver': 'MEM', 'height': wms_image_array.shape[1], 'width': wms_image_array.shape[2],
                    'count': 3, 'dtype': wms_image_array.dtype, # Expect 3 bands now
                    'crs': target_crs_obj, 'transform': wms_transform}
        plot_image_array(wms_image_array, wms_transform, target_crs_obj, "Step 5: Full WMS Download",
                         texture_plot_dir, "texture_plot_03a_wms_full",
                         show_plots=show_plots, save_plots=save_plots, plot_dpi=plot_dpi)
        plot_geometries(merged_geom_for_bbox, target_crs_obj, "Step 5: Polygon on WMS Bounds", texture_plot_dir,
                        "texture_plot_03b_poly_on_wms", raster_bounds_tuple=wms_bounds_tuple,
                        show_plots=show_plots, save_plots=save_plots, plot_dpi=plot_dpi)
    except Exception as e: print(f"Error in Step 3 (WMS Download): {e}"); traceback.print_exc(); return None

    # --- Step 4: Crop WMS Image & Fill (Save PNG to final output dir) ---
    print("  Step 4: Cropping WMS image...")
    texture_generated = False
    try:
        with MemoryFile() as memfile:
            with memfile.open(**wms_meta) as src_wms:
                src_wms.write(wms_image_array)
                # Use the ORIGINAL list of valid polygons for masking, not the merged one
                # This preserves internal holes correctly if they existed in the source
                geoms_for_mask_list = [mapping(g) for g in geoms_for_processing] # Use the list derived directly from GDF
                if not geoms_for_mask_list: raise ValueError("No valid geoms for masking.")

                out_image_masked, out_transform = rasterio.mask.mask(src_wms, geoms_for_mask_list, crop=True, filled=False, nodata=0)
        if out_image_masked.shape[1] == 0 or out_image_masked.shape[2] == 0: raise ValueError("Cropped image zero dimensions.")

        # Fill masked area
        fill_value_rgb = np.array(fill_color_rgb, dtype=np.uint8)
        fill_value_array = fill_value_rgb.reshape((3, 1, 1)) # Reshape for 3 bands
        if isinstance(out_image_masked, np.ma.MaskedArray):
            out_image_filled = np.where(out_image_masked.mask, fill_value_array, out_image_masked.data)
        else: out_image_filled = out_image_masked # Should be masked array

        # Ensure uint8 RGB
        out_image_final = out_image_filled
        if out_image_final.dtype != np.uint8:
             if np.issubdtype(out_image_final.dtype, np.floating):
                 out_image_final = (out_image_final * 255).clip(0, 255)
             out_image_final = out_image_final.astype(np.uint8)
        if out_image_final.shape[0] != 3: raise ValueError("Cropped image not 3 bands")

        # Save texture using PIL to the main output directory
        img_to_save_pil = np.transpose(out_image_final, (1, 2, 0)) # H, W, C for PIL
        pil_img = Image.fromarray(img_to_save_pil, 'RGB')
        pil_img.save(output_texture_path) # <<< Save to the final destination
        print(f"    Cropped/filled texture saved: {output_texture_path}")
        texture_generated = True

        # Plot final texture
        plot_image_array(out_image_final, out_transform, target_crs_obj, "Step 5: Final Cropped Texture",
                         texture_plot_dir, "texture_plot_04_cropped",
                         show_plots=show_plots, save_plots=save_plots, plot_dpi=plot_dpi)
        return str(output_texture_path) # Return the full path

    except Exception as e:
        print(f"Error in Step 4 (Crop/Save Texture): {e}"); traceback.print_exc()
        return None # Return None on failure