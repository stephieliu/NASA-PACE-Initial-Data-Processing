#imports
import os
import sys
from pathlib import Path
import logging

import cartopy
import cartopy.crs as ccrs
import cf_xarray
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import rioxarray as rio
import xarray as xr
from rasterio.enums import Resampling
import time

#set up logger
FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.DEBUG, format=FORMAT, stream=sys.stdout, force=True) #force output to stdout (unbuffered output)
logger = logging.getLogger(__name__) #new logger instance

#level 2 2D data
def l2_2d(file, var, user_crs = "epsg:4326", output=""):
    #default save dir is file
    if output == "": output=file

    try:
        dt = xr.open_datatree(file)
    except Exception as e:
        logger.error(f"Exception during open_datatree: {e}")
        return None
    logger.debug(f"Dims: {dt['geophysical_data'][var].dims}")

    var_sc = dt['geophysical_data'].to_dataset()

    #mask clouds with CLDICE flag
    logger.debug("Masking clouds")
    if var_sc['l2_flags'].cf.is_flag_variable:
        cloudmask = ~(var_sc['l2_flags'].cf == 'CLDICE')
        var_sc = var_sc.where(cloudmask)
    
    # setting coordinates and reference
    logger.debug("Setting coords")
    var_sc.coords['longitude'] = dt['navigation_data']['longitude']
    var_sc.coords['latitude'] = dt['navigation_data']['latitude']

    var_sc = var_sc.rio.set_spatial_dims('pixels_per_line', 'number_of_lines')
    var_sc = var_sc.rio.write_crs(user_crs)

    logger.debug(f"Dataset ready for reprojection: {var_sc}")

    #do reprojection of dataset
    logger.debug("Reprojecting data")
    try:
        var_ds = var_sc.rio.reproject(
            dst_crs = var_sc.rio.crs,
            src_geoloc_array=(
                var_sc.coords['longitude'],
                var_sc.coords['latitude'],
            ),
            nodata = np.nan,
            resampling=Resampling.nearest,
        ).rename({'x':'longitude', 'y':'latitude'})
    except Exception as e:
        logger.error(f"Exception during reprojection: {e}")
        return None

    logger.debug(f"Dataset ready for export: {var_ds}")

    #geotiff export
    logger.debug("Exporting to geotiff...")
    var_ds_name=Path(output).with_suffix(".tif")

    logger.debug(f"output path: {var_ds_name}")

    output_path_dir = output.split("\PACE_OCI.")[0]
    logger.debug(f"making output directory: {output_path_dir}")
    os.makedirs(output_path_dir, exist_ok=True)

    profile={
        # "driver":'COG', #cloud-optimized geotiff
        'width': var_ds[var].shape[1],
        'height': var_ds[var].shape[0],
        'count': 11,
        'crs': var_ds.rio.crs,
        'dtype': var_ds[var].dtype,
        'transform': var_ds.rio.transform(),
        'compress': 'lzw',
        'nodata': np.nan,
        'interleave': 'BAND',
        'tiled': 'YES',
        'blockxsize': '512',
        'blockysize': '512',
    }

    logger.debug(f"Writing to raster: {var_ds_name}")
    try:
        var_ds.rio.to_raster(var_ds_name, **profile)
    except Exception as e:
        logger.error(f"Exception during to_raster: {e}")
        return None
    logger.debug(f"Created new geotiff: {var_ds_name}")

#level2 3D data

# level 3 data
def l3_chlor(file, user_crs = "epsg:4326", output=""):
    output_path_dir = output.split("\PACE_OCI.")[0]
    logger.debug(f"making output directory: {output_path_dir}")
    os.makedirs(output_path_dir, exist_ok=True)

    demo = file

    try:
        demo_ds = xr.open_dataset(demo).drop_vars('palette')
    except Exception as e:
        logger.error(f"Exception during open_datatree: {e}")
        return None

    demo_ds = demo_ds.rio.write_crs(user_crs)
    logger.debug(f"Dataset ready for raster: {demo_ds}")

    logger.debug(f"Writing to raster: {output}")
    try:
        demo_ds.rio.to_raster(Path(output).with_suffix('.tif'))
    except Exception as e:
        logger.error(f"Exception during to_raster: {e}")
        logger.error(f"Skip to next file, cannot process raster for {output}.")
        return None

#iterate through all target files and create new geotiff files
parent_dir = r'\LocalPACESearch\target_data'
output_root_dir = r'\LocalPACESearch\target_data_tif'

all_paths = []

#list all relative paths
for root, dirs, files in os.walk(parent_dir):
    for file in files:
        if not file in all_paths:
            all_paths.append(os.path.join(root, file))

if not all_paths:
    logger.error("No files found.")
    exit()

#sort the paths in alphabetical order
all_paths.sort()

logger.debug(f"All files found: {all_paths}")

for file in all_paths:
    if "level2" in file:
        # continue
        logger.debug(f"Processing file: {file}")
        outputfilename = output_root_dir + file.split(parent_dir)[-1]
        try:
            l2_2d(file, var='chlor_a', output=outputfilename)
        except Exception as e:
            logger.error(f"Exception during l2 bgc processing: {e}")
            logger.error(f"Skip to next file, cannot process raster for {file}.")
            continue
    elif "level3" in file:
        logger.debug(f"Processing file: {file}")
        outputfilename = output_root_dir + file.split(parent_dir)[-1]
        try:
            l3_chlor(file, output=outputfilename)
        except Exception as e:
            logger.error(f"Exception during l3 chlor processing: {e}")
            logger.error(f"Skip to next file, cannot process raster for {file}.")
            continue