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

    def test_solder_bridge_detection(self):
        # Create test image with solder bridging across pins
        test_img = self.ref_img.copy()
        x, y, w, h = self.bbox
        # Add bright solder bridge between pins on top lead zone
        test_img[y:y+12, x:x+w] = (220, 220, 220)

        insp = inspect_component(self.ref_img, test_img, self.bbox, search_margin_px=10)
        dec = classify_component("U1", insp, self.config)

        self.assertEqual(dec["status"], "BRIDGED")
        self.assertIn("bridge", dec["reason"].lower())

    def test_reversed_polarity_detection(self):
        # Create an asymmetric component (e.g. IC with white orientation dot)
        ref_asym = self.ref_img.copy()
        x, y, w, h = self.bbox
        # White orientation dot at top-left corner
        ref_asym[y+12:y+20, x+12:x+20] = (245, 245, 245)

        # In-place 180° inverted placement on footprint
        test_asym = ref_asym.copy()
        test_asym[y:y+h, x:x+w] = cv2.rotate(ref_asym[y:y+h, x:x+w], cv2.ROTATE_180)

        insp = inspect_component(ref_asym, test_asym, self.bbox, search_margin_px=10)
        dec = classify_component("U1", insp, self.config)

        self.assertEqual(dec["status"], "POLARITY_REVERSED")
        self.assertIn("reversed polarity", dec["reason"].lower())

    def test_tombstone_detection(self):
        # Passive chip component: left half is bare green soldermask, right half is lifted body
        ref_chip = np.zeros((150, 150, 3), dtype=np.uint8)
        ref_chip[:] = (34, 120, 34)
        cbox = [40, 50, 70, 30] # 70x30 passive chip
        cx, cy, cw, ch = cbox
        ref_chip[cy:cy+ch, cx:cx+cw] = (40, 40, 40) # Black resistor body
        ref_chip[cy:cy+ch, cx:cx+8] = (210, 210, 210) # Left silver cap
        ref_chip[cy:cy+ch, cx+cw-8:cx+cw] = (210, 210, 210) # Right silver cap

        test_tomb = ref_chip.copy()
        # Lift left half completely off pad (exposed green PCB)
        test_tomb[cy:cy+ch, cx:cx+cw//2] = (34, 120, 34)
        # Right half has compressed vertical body
        test_tomb[cy:cy+ch, cx+cw//2:cx+cw] = (20, 20, 20)
        test_tomb[cy-5:cy+ch+5, cx+cw-12:cx+cw] = (220, 220, 220)

        insp = inspect_component(ref_chip, test_tomb, cbox, search_margin_px=8)
        dec = classify_component("R1", insp, self.config)

        self.assertEqual(dec["status"], "TOMBSTONED")
        self.assertIn("tombstoned", dec["reason"].lower())


if __name__ == "__main__":
    unittest.main()
