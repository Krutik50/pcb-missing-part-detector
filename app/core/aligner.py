"""
Global image registration using OpenCV's Enhanced Correlation Coefficient (ECC)
with border masking and graceful identity fallback.
"""

import math
from typing import Tuple, Dict, Any, Optional
import cv2
import numpy as np


def align_test_to_reference(
    ref_img: np.ndarray,
    test_img: np.ndarray,
    mask: Optional[np.ndarray] = None,
    motion_type: str = "EUCLIDEAN",
    downscale: float = 0.5,
    max_iterations: int = 40,
    eps: float = 1e-3,
    max_rotation_deg: float = 5.0,
    max_scale_drift: float = 0.05,
    max_translation_ratio: float = 0.05,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, Any]]:
    """
    Aligns test_img to ref_img using Enhanced Correlation Coefficient (findTransformECC).
    Uses a Euclidean (rigid: dx, dy, rotation) or Affine model.
    Passes mask to ensure letterboxed/padded borders are excluded from alignment gradients.
    Includes strict sanity checks and falls back to Identity if alignment diverges or exceeds bounds.

    Returns:
        aligned_img: Warped test image in reference coordinate frame
        warp_matrix: 2x3 transformation matrix
        metadata: Details on convergence, fallback usage, estimated shifts
    """
    ref_h, ref_w = ref_img.shape[:2]

    # Convert to grayscale
    ref_gray = cv2.cvtColor(ref_img, cv2.COLOR_BGR2GRAY) if ref_img.ndim == 3 else ref_img.copy()
    test_gray = cv2.cvtColor(test_img, cv2.COLOR_BGR2GRAY) if test_img.ndim == 3 else test_img.copy()

    # Downscale for fast, stable convergence
    if downscale < 1.0:
        dw = int(round(ref_w * downscale))
        dh = int(round(ref_h * downscale))
        ref_small = cv2.resize(ref_gray, (dw, dh), interpolation=cv2.INTER_AREA)
        test_small = cv2.resize(test_gray, (dw, dh), interpolation=cv2.INTER_AREA)
        mask_small = cv2.resize(mask, (dw, dh), interpolation=cv2.INTER_NEAREST) if mask is not None else None
    else:
        ref_small = ref_gray
        test_small = test_gray
        mask_small = mask

    # Set up motion model
    warp_mode = cv2.MOTION_EUCLIDEAN if motion_type.upper() == "EUCLIDEAN" else cv2.MOTION_AFFINE
    warp_matrix = np.eye(2, 3, dtype=np.float32)

    criteria = (cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, max_iterations, eps)

    fallback_used = False
    fallback_reason = ""
    cc_score = 0.0

    try:
        # Run ECC optimization
        cc_score, warp_matrix_small = cv2.findTransformECC(
            ref_small,
            test_small,
            warp_matrix,
            warp_mode,
            criteria,
            inputMask=mask_small,
            gaussFiltSize=5,
        )

        # Scale translation components back to full resolution
        scale_up = 1.0 / downscale
        warp_matrix_full = warp_matrix_small.copy()
        warp_matrix_full[0, 2] *= scale_up
        warp_matrix_full[1, 2] *= scale_up

        # Physical Plausibility Validation
        # 1. Rotation check
        angle_rad = math.atan2(warp_matrix_full[1, 0], warp_matrix_full[0, 0])
        angle_deg = math.degrees(angle_rad)
        if abs(angle_deg) > max_rotation_deg:
            fallback_used = True
            fallback_reason = f"Estimated rotation ({angle_deg:.2f} deg) exceeds max limit ({max_rotation_deg} deg)"

        # 2. Scale factor check
        scale_est = math.sqrt(warp_matrix_full[0, 0] ** 2 + warp_matrix_full[1, 0] ** 2)
        if abs(scale_est - 1.0) > max_scale_drift:
            fallback_used = True
            fallback_reason = f"Estimated scale drift ({scale_est:.3f}) exceeds limit (±{max_scale_drift})"

        # 3. Translation check
        trans_mag = math.hypot(warp_matrix_full[0, 2], warp_matrix_full[1, 2])
        diag = math.hypot(ref_w, ref_h)
        if trans_mag > (diag * max_translation_ratio):
            fallback_used = True
            fallback_reason = f"Estimated translation ({trans_mag:.1f} px) exceeds {max_translation_ratio*100:.0f}% of diagonal"

    except cv2.error as e:
        fallback_used = True
        fallback_reason = f"ECC optimization failed to converge ({str(e).splitlines()[0]})"
        warp_matrix_full = np.eye(2, 3, dtype=np.float32)

    if fallback_used:
        warp_matrix_final = np.eye(2, 3, dtype=np.float32)
        aligned_img = test_img.copy()
        angle_deg = 0.0
        dx = 0.0
        dy = 0.0
    else:
        warp_matrix_final = warp_matrix_full
        dx = float(warp_matrix_final[0, 2])
        dy = float(warp_matrix_final[1, 2])
        # Apply warp to full image (WARP_INVERSE_MAP aligns test onto ref)
        aligned_img = cv2.warpAffine(
            test_img,
            warp_matrix_final,
            (ref_w, ref_h),
            flags=cv2.INTER_LINEAR + cv2.WARP_INVERSE_MAP,
            borderMode=cv2.BORDER_REFLECT_101,
        )

    metadata = {
        "success": not fallback_used,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "correlation": float(cc_score),
        "dx_px": round(dx, 2),
        "dy_px": round(dy, 2),
        "rotation_deg": round(angle_deg, 2),
    }

    return aligned_img, warp_matrix_final, metadata
