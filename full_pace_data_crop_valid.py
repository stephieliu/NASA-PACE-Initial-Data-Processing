#script to convert all target data in a directory to cropped area defined by polygon geojson file

#imports
import os
import sys
from pathlib import Path
import logging

import geopandas as gpd
import pandas as pd
import rioxarray as rxr
import rasterio as rio
from rasterio.plot import plotting_extent
import matplotlib
import matplotlib.pyplot as plt
import earthpy as et
import earthpy.spatial as es
import earthpy.plot as ep
import numpy as np


#set up logger
FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
logging.basicConfig(level=logging.DEBUG, format=FORMAT, stream=sys.stdout, force=True) #force output to stdout (unbuffered output)
logger = logging.getLogger(__name__) #new logger instance

#set up the directories to loop through for processing
filespath = r'\LocalPACESearch\target_data_tif\level3_chl_a\global\11_16_39_PACE_OCI_L3M_CHL'
parent_dir = r'\LocalPACESearch\target_data_tif'

#save directory name
savepath = r'\LocalPACESearch\cropped_validated_target_data_tif'

#threshold value to filter out NaN values
threshold = 0.1 #set to 10% default

#set vector data geojson which will be used to crop the raster data
#uncomment whichever default file would be preferred for cropping!
area_boundary_path = r'\LocalPACESearch\lake_simcoe.geojson'

#open boundary file with gpd
#check the areaboundary crs if needed, it must match the data
#default for the uploaded geojson files should be wgs84
area_boundary = gpd.read_file(area_boundary_path)
# area_boundary.crs

#find all tif files inside of root directory to process
all_paths = []
for root, dirs, files in os.walk(filespath):
    for file in files:
        if not file in all_paths:
            all_paths.append(os.path.join(root, file))

logger.debug(f"Files found in path: {all_paths}")

#iterate through all found files and save valid cropped versions (only save if they have >TARGET_COVERAGE )
for filename in all_paths:
    #open raster data temporarily
    data = rxr.open_rasterio(filename, masked=True)
    
    data_crs = es.crs_check(filename) #crs of the data

    #IMPORTANT: need to match the crs of boundary w/ data
    area_boundary_plt = area_boundary.to_crs(data_crs)

    #open and clip the data simultaneously to speed up the process
    clipped_data = rxr.open_rasterio(filename, masked=True).rio.clip(area_boundary_plt.geometry)

    #save the newly clipped data IF there is valid data present

    #first save the clipped data temporarily
    clipped_data = clipped_data.rio.write_crs("epsg:4326")
    profile={
        # "driver":'COG', #cloud-optimized geotiff
        # 'width': clipped_data[var].shape[1],
        # 'height': var_ds[var].shape[0],
        'count': 11,
        # 'crs': var_ds.rio.crs,
        'dtype': clipped_data.dtype,
        'transform': clipped_data.rio.transform(),
        'compress': 'lzw',
        'nodata': np.nan,
        'interleave': 'BAND',
        'tiled': 'YES',
        'blockxsize': '512',
        'blockysize': '512',
    }

    #we will only keep valid data if it is above the threshold

    #get the file saving name
    if "level2" in filename:
        save_filename = savepath + filename.split(parent_dir)[-1]
    elif "level3" in filename:
        segment1=filename.split(parent_dir)[-1]
        save_filename = savepath + segment1[:segment1.index("global\\")+7] + area_boundary_path.split("\\")[-1].split(".geojson")[0] + "\\" + segment1[segment1.index("global\\")+7:]

    #make the save dir if it doesn't exist
    save_path_dirs = save_filename.split('\\PACE_OCI.')[0]

    logger.debug(f"Making save dir: {save_path_dirs}")

    os.makedirs(save_path_dirs, exist_ok = True)

    # save raster
    save_filename = Path(save_filename).with_suffix('.tif')
    clipped_data.rio.to_raster(save_filename, **profile) 

    with rio.open(save_filename) as clipped_data:
        if "level3" in str(save_filename):
            nodata = clipped_data.nodata #get raster nodata value if it exists (in l3 data)
            logger.debug(f"Found nodata value: {nodata}")
        data = clipped_data.read(1)

    #unique pixels and their count in numpy
    unique, count = np.unique(data, return_counts = True)

    #make dataframe of pixels and counts
    df_pixelcounts = pd.DataFrame()
    df_pixelcounts['Pixels'] = unique
    df_pixelcounts['Count'] = count

    sum_count = df_pixelcounts['Count'].sum() #get sum of all count column values, basically this would be the total #pixels
    if "level2" in filename:
        nodata_count = df_pixelcounts['Count'].loc[df_pixelcounts['Pixels'].isna()] #this would locate where the NaN value is in the dataframe 'pixels' column and then return the 'count' value
    elif "level3" in filename:
        nodata_count = df_pixelcounts['Count'].loc[df_pixelcounts['Pixels']==nodata] #this would locate where the NaN value is in the dataframe 'pixels' column and then return the 'count' value
        #i.e. the number of NaN values present

    #since the df is sorted from smallest to largest, nan will always be the last row

    #now calculate the % valid data
    validDataProp = 1 - (nodata_count.values[0]/sum_count)

    logger.debug(f"Calculated % not NaN data: {validDataProp}")

    #finally, remove data if it is below the threshold

    if validDataProp >= threshold:
        logger.debug(f"File data above threshold. Saved to {save_filename}")
    else:
        os.remove(save_filename)
        logger.debug(f"Not valid file. Removed {save_filename}")