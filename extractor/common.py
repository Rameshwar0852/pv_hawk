import os
import glob
import shutil
import json
import csv
from copy import deepcopy
from collections.abc import Mapping
from collections import defaultdict
import logging
import numpy as np
import cv2


logger = logging.getLogger(__name__)


def preprocess_radiometric_frame(frame, equalize_hist):
    """Preprocesses raw radiometric frame.

    Raw 16-bit radiometric intensity values are normalized to range [0, 255] 
    and converted to 8-bit. Then, histogram equalization is performed to normalize
    brightness and enhance contrast.
    """
    frame = (frame - np.min(frame)) / (np.max(frame) - np.min(frame))
    frame = (frame*255.0).astype(np.uint8)
    if equalize_hist:
        frame = cv2.equalizeHist(frame)
    return frame


def delete_output(output_dir, cluster=None):
    """Deletes the specified directory.
    If a cluster is specified, the behaviour is different. Instead of deleting
    the entire directory, only files or subdirectories belonging to this cluster
    (found via the cluster_idx) are deleted."""
    if cluster is None:
        shutil.rmtree(output_dir, ignore_errors=True)
        logger.info("Deleted {}".format(output_dir))
    else:
        cluster_idx = cluster["cluster_idx"]
        path_objects = glob.glob(os.path.join(output_dir, "*{:06d}*".format(cluster_idx)))
        for path_object in path_objects:
            try:
                os.remove(path_object)
                logger.info("Deleted {}".format(path_object))
            except IsADirectoryError:
                shutil.rmtree(path_object, ignore_errors=True)
                logger.info("Deleted {}".format(path_object))
            except FileNotFoundError:
            	pass


def get_immediate_subdirectories(a_dir):
    """Returns the immediate subdirectories of the provided directory."""
    return [name for name in os.listdir(a_dir) if os.path.isdir(os.path.join(a_dir, name))]


def get_group_name(group):
    """Returns the group name if available, empty string otherwise."""
    try:
        group_name = group["name"]
    except KeyError:
        group_name = ""
    return group_name


def merge_dicts(dict1, dict2):
    """Return a new dictionary by merging two dictionaries recursively."""
    result = deepcopy(dict1)
    for key, value in dict2.items():
        if isinstance(value, Mapping):
            result[key] = merge_dicts(result.get(key, {}), value)
        else:
            result[key] = deepcopy(dict2[key])
    return result


def remove_none(obj):
    """Removes all None items (either key or value) from nested data structures
    of dicts, lists, tuples and sets."""
    if isinstance(obj, (list, tuple, set)):
        return type(obj)(remove_none(x) for x in obj if x is not None)
    elif isinstance(obj, dict):
        return type(obj)((remove_none(k), remove_none(v))
            for k, v in obj.items() if k is not None and v is not None)
    else:
        return obj


def replace_empty_fields(dict1):
    """Takes a potentially nested dictionary and replaces all None values with
    an empty dictionary."""
    for key, value in dict1.items():
        if value is None:
            dict1[key] = {}


def sort_cw(pts):
    """Sort points clockwise by first splitting
    left/right points and then top/bottom.
    
    Acts on image coordinates, e.g. x-axis points
    rights and y-axis down.
    """
    pts = [list(p) for p in pts.reshape(-1, 2)]
    pts_sorted = sorted(pts , key=lambda k: k[0])
    pts_left = pts_sorted[:2]
    pts_right = pts_sorted[2:]
    pts_left_sorted = sorted(pts_left , key=lambda k: k[1])
    pts_right_sorted = sorted(pts_right , key=lambda k: k[1])
    tl = pts_left_sorted[0]
    bl = pts_left_sorted[1]
    tr = pts_right_sorted[0]
    br = pts_right_sorted[1]
    return np.array([tl, tr, br, bl])


def contour_and_convex_hull(mask):
    """Computes the contour and convex hull of a binary mask image.

    If the mask consists of several disconnected contours, only the largest one
    is considered.

    Args:
        mask (`numpy.ndarray`): Binary image of a segmentation mask with shape
            `(H, W)` and dtype uint8. The background should be represented by 0
            and the segmented object by 255.

    Returns:
        convex_hull (`numpy.ndarray`): Subset of the M contour points which
        represents the convex hull of the provided mask. Shape (M, 1, 2),
        dtype int32.

        contour (`numpy.ndarray`): The N contour points uniquely describing the
        boundary between segmented object and background in the provided mask.
        Shape (N, 1, 2), dtype int32.
    """
    contours, hierarchy = cv2.findContours(mask, mode=cv2.RETR_EXTERNAL, method=cv2.CHAIN_APPROX_SIMPLE)
    # get largest contour
    areas = []
    for contour in contours:
        areas.append(cv2.contourArea(contour))
    cnt_idx = np.argmax(areas)
    convex_hull = cv2.convexHull(contours[cnt_idx], clockwise=False, returnPoints=True)
    return convex_hull, contours[cnt_idx]


def compute_mask_center(convex_hull, contour, method=1):
    """Computes the center point of a contour representing a segmentation mask.

    Can be used to compute the center point of a segmentation mask by first
    computing the mask's countour with the `contour_and_convex_hull` method.

    Args:
        convex_hull (`numpy.ndarray`): Shape (M, 1, 2), dtype int32. Convex hull
        of a segmented object as returned by `contour_and_convex_hull` method.

        contour (`numpy.ndarray`): Shape (N, 1, 2), dtype int32. Contour points
        of a segmented object as returned by `contour_and_convex_hull` method.

        method (`int`): If 0 compute the center point as the center of the
            minimum enclosing circle of the convex hull. If 1 compute the center
            by means of image moments of the contour.

    Returns:
        center (`tuple` of `float`): x and y position of the countour's center
        point.
    """
    if method == 0:
        center, _ = cv2.minEnclosingCircle(convex_hull)
    if method == 1:
        M = cv2.moments(contour)
        center = (M["m10"] / M["m00"], M["m01"] / M["m00"])
    return center


class Capture:
    def __init__(self, image_files, ir_or_rgb, mask_files=None, camera_matrix=None,
            dist_coeffs=None):
        assert ir_or_rgb in ["ir", "rgb"], "Unknown image mode selection {}".format(ir_or_rgb)
        self.frame_counter = 0
        self.ir_or_rgb = ir_or_rgb
        self.image_files = image_files
        self.mask_files = mask_files
        self.camera_matrix = camera_matrix
        self.dist_coeffs = dist_coeffs
        self.num_images = len(self.image_files)
        # precompute undistortion maps
        probe_frame = cv2.imread(self.image_files[0], cv2.IMREAD_ANYDEPTH)
        self.img_w = probe_frame.shape[1]
        self.img_h = probe_frame.shape[0]
        if self.camera_matrix is not None and self.dist_coeffs is not None:
            new_camera_matrix = self.camera_matrix
            self.mapx, self.mapy = cv2.initUndistortRectifyMap(
                self.camera_matrix, self.dist_coeffs, None,
                new_camera_matrix, (self.img_w, self.img_h), cv2.CV_32FC1)
        if mask_files is not None:
            assert len(mask_files) == len(image_files), "Number of mask_files and image_files do not match"
            self.mask_files = mask_files

    def get_next_frame(self, preprocess=True, undistort=False,
            equalize_hist=True):
        frame, masks, frame_name, mask_names = self.get_frame(
            self.frame_counter, preprocess, undistort,
            equalize_hist)
        self.frame_counter += 1
        return frame, masks, frame_name, mask_names

    def get_frame(self, index, preprocess=True, undistort=False,
            equalize_hist=True):
        frame = None
        masks = None
        frame_name = None
        mask_names = None
        if index < self.num_images:
            image_file = self.image_files[index]
            frame_name = str.split(os.path.basename(image_file), ".")[0]
            if self.ir_or_rgb == "ir":
                frame = cv2.imread(image_file, cv2.IMREAD_ANYDEPTH)
            else:
                frame = cv2.imread(image_file, cv2.IMREAD_COLOR)
            if self.mask_files is not None:
                mask_file = self.mask_files[index]
                masks = [cv2.imread(m, cv2.IMREAD_ANYDEPTH) for m in mask_file]
                mask_names = [str.split(os.path.basename(m), ".")[0] for m in mask_file]
            if preprocess and self.ir_or_rgb == "ir":
                frame = preprocess_radiometric_frame(frame, equalize_hist)
            if undistort and self.camera_matrix is not None and self.dist_coeffs is not None:
                frame = cv2.remap(frame, self.mapx, self.mapy, cv2.INTER_CUBIC)
                if self.mask_files is not None:
                    masks = [cv2.remap(mask, self.mapx, self.mapy, cv2.INTER_CUBIC) for mask in masks]
        return frame, masks, frame_name, mask_names
