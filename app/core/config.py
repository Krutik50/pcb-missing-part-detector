"""
Configuration parameters for the PCB Missing Component Detection Pipeline.
Contains baseline thresholds, search margins, and sensitivity profiles.
Allows tuning without modifying core detection code.
"""

from dataclasses import dataclass, asdict
from typing import Dict, Any


@dataclass
class DetectionConfig:
    # Maximum dimension for canonical working resolution (longest edge)
    max_dimension: int = 1920

    # Alignment parameters
    alignment_motion_type: str = "EUCLIDEAN"  # Rigid motion (translation + rotation)
    alignment_downscale_factor: float = 0.5   # Downsample factor for fast ECC convergence
    alignment_max_iterations: int = 40
    alignment_eps: float = 1e-3
    max_rotation_deg: float = 5.0
    max_scale_drift: float = 0.05
    max_translation_ratio: float = 0.05       # 5% of diagonal

    # Local template matching parameters
    search_margin_px: int = 16               # Search slack around reference bounding box (±px)

    # SMT Placement Tolerances (IPC-A-610 Class 2/3 Compliance)
    max_allowed_tilt_deg: float = 3.5       # Maximum allowable angular tilt/skew in degrees (±3.5°)
    max_allowed_shift_px: float = 5.0       # Maximum allowable translation shift in pixels (5.0 px)

    # Baseline Decision Thresholds (Calibrated empirically on 20 calibration boards)
    # ZNCC Appearance Match: [-1.0, 1.0]
    # Present range: 0.911 to 0.997 | Missing range: 0.140 to 0.859
    zncc_high_thresh: float = 0.89           # Above 0.89: Confident PRESENT
    zncc_low_thresh: float = 0.86            # Below 0.86: Confident MISSING

    # Normalized Mean Absolute Patch Difference: [0.0, 1.0]
    # Present range: 0.013 to 0.063 | Missing range: 0.055 to 0.265
    patch_diff_low_thresh: float = 0.065     # Below 0.065: Confident PRESENT
    patch_diff_high_thresh: float = 0.090    # Above 0.090: Confident MISSING

    # Sensitivity Profile: "strict", "balanced", "lenient"
    sensitivity: str = "balanced"

    def get_effective_thresholds(self) -> Dict[str, float]:
        """
        Adjusts thresholds dynamically according to the sensitivity setting:
        - 'strict': Higher bar for PRESENT (catches subtle defects, higher vigilance)
        - 'balanced': Nominal calibrated operating point
        - 'lenient': Lower bar for PRESENT (tolerates heavy lighting/glare fluctuations)
        """
        base_zncc_high = self.zncc_high_thresh
        base_zncc_low = self.zncc_low_thresh
        base_diff_low = self.patch_diff_low_thresh
        base_diff_high = self.patch_diff_high_thresh

        mode = self.sensitivity.lower().strip()
        if mode == "strict":
            return {
                "zncc_high": min(0.95, base_zncc_high + 0.08),
                "zncc_low": min(0.90, base_zncc_low + 0.08),
                "diff_low": max(0.02, base_diff_low - 0.025),
                "diff_high": max(0.04, base_diff_high - 0.030),
                "max_allowed_tilt_deg": max(1.5, self.max_allowed_tilt_deg - 1.5),
                "max_allowed_shift_px": max(2.5, self.max_allowed_shift_px - 1.5),
            }
        elif mode == "lenient":
            return {
                "zncc_high": max(0.40, base_zncc_high - 0.08),
                "zncc_low": max(0.25, base_zncc_low - 0.08),
                "diff_low": min(0.40, base_diff_low + 0.06),
                "diff_high": min(0.55, base_diff_high + 0.06),
                "max_allowed_tilt_deg": self.max_allowed_tilt_deg + 2.5,
                "max_allowed_shift_px": self.max_allowed_shift_px + 3.0,
            }
        else:  # "balanced"
            return {
                "zncc_high": base_zncc_high,
                "zncc_low": base_zncc_low,
                "diff_low": base_diff_low,
                "diff_high": base_diff_high,
                "max_allowed_tilt_deg": self.max_allowed_tilt_deg,
                "max_allowed_shift_px": self.max_allowed_shift_px,
            }

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Default global configuration instance
DEFAULT_CONFIG = DetectionConfig()
