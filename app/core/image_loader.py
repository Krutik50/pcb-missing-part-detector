"""
Image loading, EXIF orientation correction, dimension normalization,
isotropic scaling, and letterbox masking.
"""

from pathlib import Path
from typing import Tuple, Union, Optional
import cv2
import numpy as np
from PIL import Image, ImageOps


def load_image_with_exif(source: Union[str, Path, bytes, np.ndarray], max_dimension: int = 1920) -> Tuple[np.ndarray, Tuple[int, int], float]:
    """
    Loads an image from a path, raw bytes, or existing numpy array.
    Applies EXIF transpose to ensure visual orientation matches pixel coordinates.
    Caps resolution to max_dimension on the longest edge while preserving aspect ratio.

    Returns:
        image: BGR numpy array (uint8)
        orig_shape: (original_height, original_width)
        scale_factor: float scale applied to reach max_dimension
    """
    if isinstance(source, np.ndarray):
        img_bgr = source.copy()
        orig_h, orig_w = img_bgr.shape[:2]
    elif isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Image not found at {path}")
        # Use PIL to read EXIF orientation tag safely
        with Image.open(path) as pil_img:
            pil_img = ImageOps.exif_transpose(pil_img)
            img_rgb = np.array(pil_img)
            if img_rgb.ndim == 2:
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_GRAY2BGR)
            elif img_rgb.shape[2] == 4:
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGBA2BGR)
            else:
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        orig_h, orig_w = img_bgr.shape[:2]
    elif isinstance(source, bytes):
        import io
        with Image.open(io.BytesIO(source)) as pil_img:
            pil_img = ImageOps.exif_transpose(pil_img)
            img_rgb = np.array(pil_img)
            if img_rgb.ndim == 2:
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_GRAY2BGR)
            elif img_rgb.shape[2] == 4:
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGBA2BGR)
            else:
                img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
        orig_h, orig_w = img_bgr.shape[:2]
    else:
        raise TypeError(f"Unsupported image source type: {type(source)}")

    # Cap resolution at max_dimension
    max_edge = max(orig_h, orig_w)
    if max_edge > max_dimension:
        scale_factor = max_dimension / float(max_edge)
        new_w = int(round(orig_w * scale_factor))
        new_h = int(round(orig_h * scale_factor))
        img_bgr = cv2.resize(img_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
    else:
        scale_factor = 1.0

    return img_bgr, (orig_h, orig_w), scale_factor


def normalize_to_reference(ref_img: np.ndarray, test_img: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """
    Normalizes test_img to match ref_img's canvas dimensions:
    - If dimensions match: Returns copies with an all-255 active mask.
    - If dimensions or aspect ratio differ: Scales test_img isotropically (no distortion)
      and centers it on a neutral letterbox canvas matching ref_img's size.
    - Produces a single-channel binary mask (255 = active image, 0 = letterbox padding)
      so that alignment algorithms ignore the synthetic borders.

    Returns:
        ref_norm: Reference image (H, W, 3)
        test_norm: Normalized/padded test image (H, W, 3)
        mask: Binary mask (H, W), uint8
        info: Dictionary with scale and padding offsets
    """
    ref_h, ref_w = ref_img.shape[:2]
    test_h, test_w = test_img.shape[:2]

    if (ref_h, ref_w) == (test_h, test_w):
        mask = np.full((ref_h, ref_w), 255, dtype=np.uint8)
        info = {
            "is_padded": False,
            "scale": 1.0,
            "pad_top": 0, "pad_bottom": 0,
            "pad_left": 0, "pad_right": 0
        }
        return ref_img.copy(), test_img.copy(), mask, info

    # Isotropic scale calculation
    scale = min(ref_w / test_w, ref_h / test_h)
    scaled_w = int(round(test_w * scale))
    scaled_h = int(round(test_h * scale))

    scaled_test = cv2.resize(test_img, (scaled_w, scaled_h), interpolation=cv2.INTER_AREA if scale < 1.0 else cv2.INTER_LINEAR)

    # Center on canvas with neutral letterboxing (BGR: 128, 128, 128)
    canvas = np.full((ref_h, ref_w, 3), 128, dtype=np.uint8)
    mask = np.zeros((ref_h, ref_w), dtype=np.uint8)

    pad_left = (ref_w - scaled_w) // 2
    pad_top = (ref_h - scaled_h) // 2

    canvas[pad_top:pad_top + scaled_h, pad_left:pad_left + scaled_w] = scaled_test
    mask[pad_top:pad_top + scaled_h, pad_left:pad_left + scaled_w] = 255

    info = {
        "is_padded": True,
        "scale": scale,
        "pad_top": pad_top,
        "pad_bottom": ref_h - (pad_top + scaled_h),
        "pad_left": pad_left,
        "pad_right": ref_w - (pad_left + scaled_w)
    }

    return ref_img.copy(), canvas, mask, info
