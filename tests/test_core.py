"""
Unit tests for core computer vision and decision modules.
Run with: python -m unittest discover tests
"""

import unittest
import numpy as np
import cv2

from app.core.config import DetectionConfig, DEFAULT_CONFIG
from app.core.image_loader import load_image_with_exif, normalize_to_reference
from app.core.aligner import align_test_to_reference
from app.core.detector import inspect_component
from app.core.decision import classify_component, aggregate_board_status


class TestImageLoader(unittest.TestCase):
    def test_resolution_capping(self):
        # Create dummy image exceeding 1920 max dimension
        large_img = np.zeros((2400, 3200, 3), dtype=np.uint8)
        loaded, orig_shape, scale = load_image_with_exif(large_img, max_dimension=1920)

        self.assertEqual(orig_shape, (2400, 3200))
        self.assertEqual(max(loaded.shape[:2]), 1920)
        self.assertAlmostEqual(scale, 1920 / 3200, places=3)

    def test_letterbox_mask_generation(self):
        ref = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # Test image with different aspect ratio (4:3 vs 16:9)
        test = np.zeros((1200, 1600, 3), dtype=np.uint8)

        ref_norm, test_norm, mask, info = normalize_to_reference(ref, test)
        self.assertEqual(test_norm.shape, ref.shape)
        self.assertEqual(mask.shape, (1080, 1920))
        self.assertTrue(info["is_padded"])
        # Active region should be 255, padding borders 0
        self.assertEqual(mask[mask > 0].min(), 255)
        self.assertEqual(mask[mask == 0].max(), 0)


class TestAligner(unittest.TestCase):
    def test_rigid_alignment_recovery(self):
        # Create textured board with high-contrast features
        ref = np.zeros((400, 600, 3), dtype=np.uint8)
        cv2.rectangle(ref, (100, 100), (300, 300), (200, 200, 200), -1)
        cv2.circle(ref, (200, 200), 40, (50, 50, 50), -1)

        # Shift test image by +3 px X, -2 px Y
        M = np.float32([[1, 0, 3], [0, 1, -2]])
        test = cv2.warpAffine(ref, M, (600, 400), borderMode=cv2.BORDER_REFLECT_101)

        aligned, warp_mat, meta = align_test_to_reference(ref, test, motion_type="EUCLIDEAN", downscale=1.0)
        self.assertTrue(meta["success"])
        self.assertFalse(meta["fallback_used"])
        # Shift recovered should be approximately -3 and +2 (inverse map)
        self.assertAlmostEqual(meta["dx_px"], 3.0, delta=1.5)
        self.assertAlmostEqual(meta["dy_px"], -2.0, delta=1.5)

    def test_fallback_on_unrelated_image(self):
        # Random noise should fail ECC or violate bounds and trigger fallback
        np.random.seed(42)
        ref = np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)
        test = np.random.randint(0, 255, (300, 300, 3), dtype=np.uint8)

        aligned, warp_mat, meta = align_test_to_reference(ref, test, downscale=1.0)
        # Should cleanly trigger fallback to identity without crashing
        self.assertTrue(meta["fallback_used"])
        np.testing.assert_array_equal(warp_mat, np.eye(2, 3, dtype=np.float32))


class TestDetector(unittest.TestCase):
    def test_identical_match(self):
        ref = np.zeros((200, 200, 3), dtype=np.uint8)
        cv2.rectangle(ref, (40, 40), (80, 80), (180, 120, 60), -1)
        cv2.circle(ref, (60, 60), 10, (220, 220, 220), -1)

        result = inspect_component(ref, ref, bbox=[40, 40, 40, 40], search_margin_px=10)
        self.assertGreaterEqual(result["zncc_score"], 0.98)
        self.assertLessEqual(result["patch_diff"], 0.05)

    def test_missing_or_dissimilar_patch(self):
        ref = np.zeros((200, 200, 3), dtype=np.uint8)
        # Populated component: dark body with bright metallic contacts
        cv2.rectangle(ref, (40, 40), (80, 80), (30, 30, 30), -1)
        cv2.rectangle(ref, (40, 40), (50, 80), (210, 210, 210), -1)
        cv2.rectangle(ref, (70, 40), (80, 80), (210, 210, 210), -1)

        test = np.zeros((200, 200, 3), dtype=np.uint8)
        # Empty site: green substrate with only two thin pad traces
        test[:, :] = (24, 78, 40)
        cv2.rectangle(test, (40, 42), (48, 78), (195, 205, 215), -1)
        cv2.rectangle(test, (72, 42), (80, 78), (195, 205, 215), -1)

        result = inspect_component(ref, test, bbox=[40, 40, 40, 40], search_margin_px=10)
        # Even with exposed pads mimicking pin locations, ZNCC drops and patch residual is high
        self.assertLess(result["zncc_score"], 0.85)
        self.assertGreater(result["patch_diff"], 0.12)


class TestDecisionLogic(unittest.TestCase):
    def setUp(self):
        self.config = DetectionConfig()

    def test_classification_states(self):
        # Case 1: High match -> PRESENT
        good_insp = {"zncc_score": 0.88, "patch_diff": 0.12, "best_bbox": [10, 10, 20, 20]}
        v_good = classify_component("C1", good_insp, self.config)
        self.assertEqual(v_good["status"], "PRESENT")

        # Case 2: Low match / High diff -> MISSING
        bad_insp = {"zncc_score": 0.25, "patch_diff": 0.45, "best_bbox": [10, 10, 20, 20]}
        v_bad = classify_component("U1", bad_insp, self.config)
        self.assertEqual(v_bad["status"], "MISSING")

        # Case 3: Borderline scores -> UNCERTAIN
        border_insp = {"zncc_score": 0.52, "patch_diff": 0.28, "best_bbox": [10, 10, 20, 20]}
        v_border = classify_component("R1", border_insp, self.config)
        self.assertEqual(v_border["status"], "UNCERTAIN")

    def test_board_aggregation(self):
        # All present -> OK
        parts_ok = [
            {"name": "C1", "status": "PRESENT"},
            {"name": "R1", "status": "PRESENT"},
        ]
        self.assertEqual(aggregate_board_status(parts_ok)["board_status"], "OK")

        # One missing -> DEFECT
        parts_defect = [
            {"name": "C1", "status": "PRESENT"},
            {"name": "R1", "status": "MISSING"},
        ]
        self.assertEqual(aggregate_board_status(parts_defect)["board_status"], "DEFECT")

        # None missing, one uncertain -> REVIEW
        parts_review = [
            {"name": "C1", "status": "PRESENT"},
            {"name": "R1", "status": "UNCERTAIN"},
        ]
        self.assertEqual(aggregate_board_status(parts_review)["board_status"], "REVIEW")


if __name__ == "__main__":
    unittest.main()
