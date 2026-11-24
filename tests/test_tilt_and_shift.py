"""
Unit tests for SMT Component Angular Tilt and Positional Misalignment Tolerance Engine.
Verifies compliance with IPC-A-610 Class 2/3 placement tolerance envelopes.
"""

import unittest
import sys
from pathlib import Path
import numpy as np
import cv2

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.core.config import DetectionConfig
from app.core.detector import estimate_angular_tilt, inspect_component
from app.core.decision import classify_component, aggregate_board_status


class TestTiltAndShiftDetection(unittest.TestCase):
    def setUp(self):
        self.config = DetectionConfig(sensitivity="balanced")
        # Create a synthetic reference component (IC package with pins)
        self.ref_img = np.zeros((200, 200, 3), dtype=np.uint8)
        self.ref_img[:] = (34, 120, 34)  # Green PCB soldermask
        # Black IC package in center at [50, 50, 80, 80]
        self.bbox = [50, 50, 80, 80]
        x, y, w, h = self.bbox
        self.ref_img[y+10:y+h-10, x+10:x+w-10] = (25, 25, 25) # IC mold
        # Metallic leads on left and right
        self.ref_img[y+15:y+h-15:10, x:x+10] = (200, 200, 200)
        self.ref_img[y+15:y+h-15:10, x+w-10:x+w] = (200, 200, 200)

    def test_nominal_aligned_component_is_present(self):
        # Test image identical to reference
        test_img = self.ref_img.copy()
        insp = inspect_component(self.ref_img, test_img, self.bbox)
        dec = classify_component("U1", insp, self.config)

        self.assertEqual(dec["status"], "PRESENT")
        self.assertLessEqual(abs(dec["tilt_deg"]), self.config.max_allowed_tilt_deg)
        self.assertLessEqual(dec["shift_dist_px"], self.config.max_allowed_shift_px)

    def test_tilted_component_detection(self):
        # Rotate component inside test image by +8.0 degrees (tolerance is 3.5 deg)
        test_img = self.ref_img.copy()
        x, y, w, h = self.bbox
        center = (x + w / 2.0, y + h / 2.0)
        M = cv2.getRotationMatrix2D(center, 8.0, 1.0)
        test_img = cv2.warpAffine(test_img, M, (200, 200), borderMode=cv2.BORDER_REFLECT)

        insp = inspect_component(self.ref_img, test_img, self.bbox, search_margin_px=10)
        dec = classify_component("U1", insp, self.config)

        self.assertEqual(dec["status"], "TILTED")
        self.assertGreater(abs(dec["tilt_deg"]), self.config.max_allowed_tilt_deg)
        self.assertIn("tilted", dec["reason"].lower())

    def test_misaligned_shifted_component_detection(self):
        # Shift component by dx=+8 px, dy=0 px (tolerance is 5.0 px)
        test_img = np.zeros((200, 200, 3), dtype=np.uint8)
        test_img[:] = (34, 120, 34)
        x, y, w, h = self.bbox
        sx = x + 8
        sy = y
        test_img[sy+10:sy+h-10, sx+10:sx+w-10] = (25, 25, 25)
        test_img[sy+15:sy+h-15:10, sx:sx+10] = (200, 200, 200)
        test_img[sy+15:sy+h-15:10, sx+w-10:sx+w] = (200, 200, 200)

        insp = inspect_component(self.ref_img, test_img, self.bbox, search_margin_px=16)
        dec = classify_component("U1", insp, self.config)

        self.assertEqual(dec["status"], "MISALIGNED")
        self.assertGreater(dec["shift_dist_px"], self.config.max_allowed_shift_px)
        self.assertIn("shifted", dec["reason"].lower())

    def test_missing_component_detection(self):
        # Empty bare PCB soldermask at component site
        test_img = np.zeros((200, 200, 3), dtype=np.uint8)
        test_img[:] = (34, 120, 34)

        insp = inspect_component(self.ref_img, test_img, self.bbox, search_margin_px=16)
        dec = classify_component("U1", insp, self.config)

        self.assertEqual(dec["status"], "MISSING")

    def test_board_level_aggregation_with_tilt_and_shift(self):
        comp_results = [
            {"name": "R1", "status": "PRESENT"},
            {"name": "C1", "status": "TILTED"},
            {"name": "U1", "status": "MISALIGNED"},
            {"name": "U2", "status": "MISSING"},
        ]
        b_eval = aggregate_board_status(comp_results)
        self.assertEqual(b_eval["board_status"], "DEFECT")
        self.assertIn("C1", b_eval["tilted_components"])
        self.assertIn("U1", b_eval["misaligned_components"])
        self.assertIn("U2", b_eval["missing_components"])
        self.assertIn("tilted", b_eval["summary"].lower())
        self.assertIn("shifted", b_eval["summary"].lower())


if __name__ == "__main__":
    unittest.main()
