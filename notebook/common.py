import os
import csv
import cv2
import openslide
import numpy as np
import pandas as pd


def find_patches_from_slide(slide_path, 
                            truth_path, 
                            patch_size=256, 
                            filter_non_tissue=True,
                            filter_only_all_tumor=True):
    '''Returns a DataFrame of all patches in slide
        Args:
            - slide_path: path of slide
            - truth_path: path of truth(mask)
            - patch_size: patch size for samples
            - filter_non_tissue: remove samples no tissue detected
        Returns:
            - all_tissue_samples: patch samples from slide'''
    # 해당 데이터가 양성인지 판단
    slide_contains_tumor = 'pos' in slide_path

    # read_region을 위한 start, level, size 계산
    bounds_offset_props = (openslide.PROPERTY_NAME_BOUNDS_X, openslide.PROPERTY_NAME_BOUNDS_Y)
    bounds_size_props = (openslide.PROPERTY_NAME_BOUNDS_WIDTH, openslide.PROPERTY_NAME_BOUNDS_HEIGHT)

    with openslide.open_slide(slide_path) as slide:
        start = (0, 0)
        size_scale = (1, 1)
        level = int(np.log2(patch_size))
        l_dimensions = [(int(np.ceil(dim_x * size_scale[0])), int(np.ceil(dim_y * size_scale[1])))
                        for dim_x, dim_y in slide.level_dimensions]
        size = l_dimensions[level]
        
        if slide_contains_tumor: 
            start = (int(slide.properties.get(bounds_offset_props[0], 0)), 
                     int(slide.properties.get(bounds_offset_props[1], 0)))
            size_scale = tuple(int(slide.properties.get(prop, dim)) / dim 
                               for prop, dim in zip(bounds_size_props, slide.dimensions))
            
            with openslide.open_slide(truth_path) as truth:
                z_dimensions = []
                z_size = truth.dimensions
                z_dimensions.append(z_size)
                while z_size[0] > 1 or z_size[1] > 1:
                    z_size = tuple(max(1, int(np.ceil(z/2))) for z in z_size)
                    z_dimensions.append(z_size)
            size = z_dimensions[level-4]
        slide4 = slide.read_region(start, level, size)
        
    # is_tissue 부분
    slide4_grey = np.array(slide4.convert('L'))

    # background에 대한 작업
    slide4_not_black = slide4_grey[slide4_grey > 0]
    # thresh = threshold_otsu(slide4_not_black)
    ret, th = cv2.threshold(slide4_not_black, 0, 255, 
                            cv2.THRESH_BINARY+cv2.THRESH_OTSU)

    binary = slide4_grey > 0  # black == 0
    h, w = slide4_grey.shape
    for i in range(h):
        for j in range(w):
            if slide4_grey[i, j] > ret:
                binary[i, j] = False

    # patch_df
    patches = pd.DataFrame(pd.DataFrame(binary).stack(), columns=['is_tissue'])
    patches.loc[:, 'slide_path'] = slide_path
    
    # is_tumor 부분
    if slide_contains_tumor:
        with openslide.open_slide(truth_path) as truth:
            thumbnail_truth = truth.get_thumbnail(size)

        # truth pathes_df
        patches_y = pd.DataFrame(
                pd.DataFrame(np.array(thumbnail_truth.convert('L'))).stack())
        patches_y['is_tumor'] = patches_y[0] > 0

        # mask된 영역이 애매한 경우
        patches_y['is_all_tumor'] = patches_y[0] == 255
        patches_y.drop(0, axis=1, inplace=True)
        samples = pd.concat([patches, patches_y], axis=1)
    else: 
        samples = patches
        samples.loc[:, 'is_tumor'] = False
        samples.loc[:, 'is_all_tumor'] = False

    if filter_non_tissue:  # tissue인것만 가져오기
        samples = samples[samples['is_tissue'] == True]
        
    if filter_only_all_tumor:  # 어떤 의미?
        samples['tile_loc'] = list(samples.index)
        all_tissue_samples = samples[samples['is_tumor'] == False]
        all_tissue_samples = all_tissue_samples.append(samples[samples['is_all_tumor'] == True])
        all_tissue_samples.reset_index(inplace=True, drop=True)
    else:
        return samples
    
    return all_tissue_samples