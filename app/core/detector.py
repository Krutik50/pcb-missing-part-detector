"""
Local bounded template matching via ZNCC and Normalized Mean Absolute Patch Difference.
Derived strictly from the reference crop without hardcoded pad heuristics.
"""

from typing import Tuple, Dict, Any, List
import cv2
import numpy as np


def inspect_component(
    ref_img: np.ndarray,
    aligned_test_img: np.ndarray,
    bbox: List[int],
    search_margin_px: int = 16,
) -> Dict[str, Any]:
    """
    Evaluates a single component site:
    1. Extracts reference template T_ref at bbox [x, y, w, h].
    2. Searches a localized window in aligned_test_img (x ± margin, y ± margin)
       using Zero-mean Normalized Cross-Correlation (cv2.TM_CCOEFF_NORMED).
    3. Finds best-matching candidate location and peak ZNCC correlation score.
    4. Computes Normalized Mean Absolute Difference (L1 patch residual) after
       local mean-illumination adjustment.

    Returns:
        Dictionary with zncc_score, patch_diff, best_bbox, displacement_px, and diagnostics.
    """
    ref_h, ref_w = ref_img.shape[:2]
    test_h, test_w = aligned_test_img.shape[:2]

    x, y, w, h = bbox
    # Ensure bounding box is within reference boundaries
    x = max(0, min(x, ref_w - 1))
    y = max(0, min(y, ref_h - 1))
    w = max(4, min(w, ref_w - x))
    h = max(4, min(h, ref_h - y))

    # Crop reference template
    template_bgr = ref_img[y:y + h, x:x + w]
    template_gray = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY) if template_bgr.ndim == 3 else template_bgr

    # Define localized search window in test image
    pad = search_margin_px
    x_min = max(0, x - pad)
    y_min = max(0, y - pad)
    x_max = min(test_w, x + w + pad)
    y_max = min(test_h, y + h + pad)

    search_region_bgr = aligned_test_img[y_min:y_max, x_min:x_max]
    search_region_gray = cv2.cvtColor(search_region_bgr, cv2.COLOR_BGR2GRAY) if search_region_bgr.ndim == 3 else search_region_bgr

    # Search window must be strictly larger than or equal to template
    s_h, s_w = search_region_gray.shape[:2]
    if s_h < h or s_w < w:
        # Boundary fallback: directly compare co-located patch
        candidate_gray = search_region_gray[:min(s_h, h), :min(s_w, w)]
        t_crop = template_gray[:candidate_gray.shape[0], :candidate_gray.shape[1]]
        diff = float(np.mean(np.abs(t_crop.astype(np.float32) - candidate_gray.astype(np.float32))) / 255.0)
        return {
            "zncc_score": 0.0,
            "patch_diff": diff,
            "best_bbox": [x, y, w, h],
            "shift_px": (0, 0),
            "template_shape": (w, h),
        }

    # Check for empty/flat ROI warning (standard deviation)
    std_t = float(np.std(template_gray))
    is_low_texture = std_t < 10.0

    # If template has virtually zero variance, ZNCC denominator is 0 (undefined in OpenCV)
    if std_t < 1.0:
        c_crop = search_region_gray[y - y_min:y - y_min + h, x - x_min:x - x_min + w]
        if c_crop.shape == template_gray.shape:
            diff = float(np.mean(np.abs(template_gray.astype(np.float32) - c_crop.astype(np.float32))) / 255.0)
        else:
            diff = 1.0
        return {
            "zncc_score": 0.0,
            "patch_diff": round(diff, 4),
            "best_bbox": [x, y, w, h],
            "shift_px": (0, 0),
            "is_low_texture": True,
            "template_std": round(std_t, 2),
        }

    # Step 1: Zero-mean Normalized Cross-Correlation (ZNCC)
    match_map = cv2.matchTemplate(search_region_gray, template_gray, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(match_map)

    peak_zncc = float(max_val)
    best_x_local, best_y_local = max_loc

    # Global coordinates of candidate match in aligned test image
    match_x = x_min + best_x_local
    match_y = y_min + best_y_local
    shift_x = match_x - x
    shift_y = match_y - y

    # Crop matched patch from test image
    candidate_gray = search_region_gray[best_y_local:best_y_local + h, best_x_local:best_x_local + w]

    # Step 2: Illumination-Compensated Mean Absolute Patch Difference
    # Cancels uniform lighting offset between reference crop and test patch
    t_f = template_gray.astype(np.float32)
    c_f = candidate_gray.astype(np.float32)

    # Adjust candidate to match template's mean intensity
    mean_t = float(np.mean(t_f))
    mean_c = float(np.mean(c_f))
    c_adjusted = c_f - mean_c + mean_t

    # L1 residual normalized to [0.0, 1.0]
    patch_diff = float(np.mean(np.abs(t_f - c_adjusted)) / 255.0)

    # Check for empty/flat ROI warning (standard deviation)
    std_t = float(np.std(t_f))
    is_low_texture = std_t < 10.0

    return {
        "zncc_score": round(peak_zncc, 4),
        "patch_diff": round(patch_diff, 4),
        "best_bbox": [match_x, match_y, w, h],
        "shift_px": (shift_x, shift_y),
        "is_low_texture": is_low_texture,
        "template_std": round(std_t, 2),
    }
