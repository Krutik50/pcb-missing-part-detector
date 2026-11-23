"""
Integration unit tests for FastAPI backend endpoints.
Tests reference upload, component registration, multi-image inspection,
error handling for non-images and corrupt files, and coordinate formatting.
"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from fastapi.testclient import TestClient
from app.main import app, SESSIONS

client = TestClient(app)
SAMPLE_DIR = Path(__file__).resolve().parent.parent / "sample_data"
RESULTS_DIR = Path(__file__).resolve().parent.parent / "results"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)


class TestBackendAPI(unittest.TestCase):
    def setUp(self):
        # Clear sessions before each test for test isolation
        SESSIONS.clear()

        # Load ground truth components
        with open(SAMPLE_DIR / "ground_truth.json", "r", encoding="utf-8") as f:
            self.gt_data = json.load(f)
        self.components_meta = self.gt_data["components"]

    def test_health_check(self):
        response = client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "healthy")
        self.assertTrue(data["offline"])
        self.assertIn("default_thresholds", data)

    def test_reject_non_image_reference(self):
        # Upload a plain text file pretending to be an image
        fake_bytes = b"This is not a real image file, just plain text."
        response = client.post(
            "/api/reference",
            files={"file": ("fake_board.png", fake_bytes, "text/plain")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("not a valid or readable image", response.json()["detail"])

    def test_reject_empty_reference(self):
        response = client.post(
            "/api/reference",
            files={"file": ("empty.png", b"", "image/png")},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("is empty", response.json()["detail"])

    def test_reference_upload_and_session_creation(self):
        ref_path = SAMPLE_DIR / "reference.png"
        with open(ref_path, "rb") as f:
            response = client.post(
                "/api/reference",
                files={"file": ("reference.png", f, "image/png")},
            )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("session_id", data)
        self.assertEqual(data["working_width"], 1920)
        self.assertEqual(data["working_height"], 1080)
        self.assertIn(data["session_id"], SESSIONS)

    def test_component_registration_pixel_and_normalized(self):
        # 1. Upload reference
        with open(SAMPLE_DIR / "reference.png", "rb") as f:
            ref_resp = client.post("/api/reference", files={"file": ("ref.png", f, "image/png")})
        session_id = ref_resp.json()["session_id"]

        # 2. Register one pixel box and one normalized box
        payload = {
            "components": [
                {"name": "U1_MCU", "bbox": [580, 400, 200, 200], "is_normalized": False},
                {"name": "C1_DECOUP", "bbox": [0.2448, 0.3981, 0.0125, 0.0278], "is_normalized": True},
            ]
        }
        resp = client.post(f"/api/sessions/{session_id}/components", json=payload)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["registered_components_count"], 2)

        comps = data["components"]
        self.assertEqual(comps["U1_MCU"]["pixel_bbox"], [580, 400, 200, 200])
        # Normalized coordinates should be properly scaled and rounded
        self.assertEqual(len(comps["C1_DECOUP"]["pixel_bbox"]), 4)
        self.assertEqual(len(comps["C1_DECOUP"]["normalized_bbox"]), 4)

    def test_multi_image_inspection_workflow(self):
        """
        Tests inspecting more than 3 test images (> 3) in a single batch:
        - 1 complete board (calib_01) -> Expect OK
        - 1 board missing U1_MCU (calib_08) -> Expect DEFECT
        - 1 board missing C1_DECOUP (calib_09) -> Expect DEFECT
        - 1 board missing C1 and C2 (calib_12) -> Expect DEFECT
        """
        # 1. Upload reference
        with open(SAMPLE_DIR / "reference.png", "rb") as f:
            ref_resp = client.post("/api/reference", files={"file": ("reference.png", f, "image/png")})
        session_id = ref_resp.json()["session_id"]

        # 2. Register all ground truth components
        comp_payload = {
            "components": [
                {"name": cid, "bbox": cinfo["pixel_bbox"], "is_normalized": False}
                for cid, cinfo in self.components_meta.items()
            ]
        }
        client.post(f"/api/sessions/{session_id}/components", json=comp_payload)

        # 3. Prepare 4 test image files (> 3 images)
        test_files = [
            ("calib_01_all_ok_nominal.png", "calibration/calib_01_all_ok_nominal.png"),
            ("calib_08_missing_u1_mcu.png", "calibration/calib_08_missing_u1_mcu.png"),
            ("calib_09_missing_c1.png", "calibration/calib_09_missing_c1.png"),
            ("calib_12_missing_adj_c1_c2.png", "calibration/calib_12_missing_adj_c1_c2.png"),
        ]

        file_payload = []
        open_files = []
        for upload_name, rel_path in test_files:
            fp = open(SAMPLE_DIR / rel_path, "rb")
            open_files.append(fp)
            file_payload.append(("test_images", (upload_name, fp, "image/png")))

        try:
            inspect_resp = client.post(
                "/api/inspect",
                data={"session_id": session_id, "sensitivity": "balanced"},
                files=file_payload,
            )
        finally:
            for fp in open_files:
                fp.close()

        self.assertEqual(inspect_resp.status_code, 200)
        data = inspect_resp.json()
        self.assertEqual(data["total_images_inspected"], 4)
        self.assertEqual(len(data["results"]), 4)

        results_by_name = {r["filename"]: r for r in data["results"]}

        # Board 1: All OK
        res_01 = results_by_name["calib_01_all_ok_nominal.png"]
        self.assertEqual(res_01["board_status"], "OK")
        self.assertEqual(len(res_01["missing_components"]), 0)
        self.assertTrue(res_01["alignment"]["success"])
        self.assertFalse(res_01["alignment"]["fallback_used"])

        # Board 2: Missing U1_MCU
        res_08 = results_by_name["calib_08_missing_u1_mcu.png"]
        self.assertEqual(res_08["board_status"], "DEFECT")
        self.assertIn("U1_MCU", res_08["missing_components"])

        # Board 3: Missing C1_DECOUP
        res_09 = results_by_name["calib_09_missing_c1.png"]
        self.assertEqual(res_09["board_status"], "DEFECT")
        self.assertIn("C1_DECOUP", res_09["missing_components"])

        # Board 4: Missing C1 and C2
        res_12 = results_by_name["calib_12_missing_adj_c1_c2.png"]
        self.assertEqual(res_12["board_status"], "DEFECT")
        self.assertIn("C1_DECOUP", res_12["missing_components"])
        self.assertIn("C2_DECOUP", res_12["missing_components"])

        # Check box coordinate structure on components
        sample_comp = res_01["components"][0]
        self.assertIn("pixel", sample_comp["box"])
        self.assertIn("normalized", sample_comp["box"])
        self.assertEqual(len(sample_comp["box"]["pixel"]), 4)
        self.assertEqual(len(sample_comp["box"]["normalized"]), 4)
        self.assertIn("zncc", sample_comp["scores"])
        self.assertIn("patch_diff", sample_comp["scores"])
        self.assertIn("reason", sample_comp)

        # Save sample request and response artifact
        sample_artifact = {
            "endpoint": "POST /api/inspect",
            "request": {
                "session_id": session_id,
                "sensitivity": "balanced",
                "test_images_count": 4,
                "filenames": [f[0] for f in test_files],
            },
            "response_summary": {
                "sensitivity": data["sensitivity"],
                "thresholds": data["thresholds"],
                "total_images_inspected": data["total_images_inspected"],
                "results": [
                    {
                        "filename": r["filename"],
                        "board_status": r["board_status"],
                        "summary": r["summary"],
                        "alignment": r["alignment"],
                        "components_sample": r["components"][:2],  # truncate for concise view
                    }
                    for r in data["results"]
                ],
            },
        }

        with open(RESULTS_DIR / "api_sample_request_response.json", "w", encoding="utf-8") as f:
            json.dump(sample_artifact, f, indent=2)

    def test_non_image_file_in_multi_image_inspection(self):
        # 1. Upload reference
        with open(SAMPLE_DIR / "reference.png", "rb") as f:
            ref_resp = client.post("/api/reference", files={"file": ("reference.png", f, "image/png")})
        session_id = ref_resp.json()["session_id"]

        # 2. Register one component
        client.post(
            f"/api/sessions/{session_id}/components",
            json={"components": [{"name": "U1_MCU", "bbox": [580, 400, 200, 200]}]},
        )

        # 3. Upload a corrupt / text file along with a valid image
        with open(SAMPLE_DIR / "calibration/calib_01_all_ok_nominal.png", "rb") as valid_fp:
            response = client.post(
                "/api/inspect",
                data={"session_id": session_id, "sensitivity": "balanced"},
                files=[
                    ("test_images", ("good_board.png", valid_fp, "image/png")),
                    ("test_images", ("corrupted.png", b"NOT AN IMAGE", "image/png")),
                ],
            )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_images_inspected"], 2)

        results_map = {r["filename"]: r for r in data["results"]}
        self.assertEqual(results_map["good_board.png"]["board_status"], "OK")
        self.assertEqual(results_map["corrupted.png"]["board_status"], "ERROR")
        self.assertIn("not a valid or readable image", results_map["corrupted.png"]["error"])

    def test_invalid_sensitivity_rejection(self):
        with open(SAMPLE_DIR / "reference.png", "rb") as f:
            ref_resp = client.post("/api/reference", files={"file": ("reference.png", f, "image/png")})
        session_id = ref_resp.json()["session_id"]

        with open(SAMPLE_DIR / "calibration/calib_01_all_ok_nominal.png", "rb") as valid_fp:
            response = client.post(
                "/api/inspect",
                data={"session_id": session_id, "sensitivity": "ultra_extreme_invalid"},
                files=[("test_images", ("board.png", valid_fp, "image/png"))],
            )
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid sensitivity", response.json()["detail"])

    def test_invalid_session_id_rejection(self):
        with open(SAMPLE_DIR / "calibration/calib_01_all_ok_nominal.png", "rb") as valid_fp:
            response = client.post(
                "/api/inspect",
                data={"session_id": "non_existent_session_12345", "sensitivity": "balanced"},
                files=[("test_images", ("board.png", valid_fp, "image/png"))],
            )
        self.assertEqual(response.status_code, 404)
        self.assertIn("not found", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
