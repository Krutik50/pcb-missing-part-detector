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

    def test_get_sample_recipe(self):
        response = client.get("/api/sample-recipe")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["recipe_version"], "1.0")
        self.assertEqual(data["board_name"], "PCB_SAMPLE_MAIN_BOARD")
        self.assertEqual(data["image_size"]["width"], 1920)
        self.assertEqual(data["image_size"]["height"], 1080)
        self.assertIn("aspect_ratio", data["image_size"])
        self.assertIn("image_fingerprint", data)
        self.assertEqual(data["sensitivity"], "balanced")
        self.assertGreater(len(data["components"]), 0)

    def test_validate_recipe_success(self):
        recipe = {
            "recipe_version": "1.0",
            "board_name": "TEST_BOARD_REV1",
            "image_size": {"width": 1920, "height": 1080},
            "sensitivity": "balanced",
            "components": [
                {"name": "U1_MCU", "normalized_bbox": [0.3021, 0.3704, 0.1042, 0.1852]},
                {"name": "R1_PULLUP", "pixel_bbox": [880, 420, 24, 48]},
            ],
        }
        response = client.post("/api/recipes/validate?expected_width=1920&expected_height=1080", json=recipe)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["valid"])
        self.assertEqual(data["board_name"], "TEST_BOARD_REV1")
        self.assertEqual(data["components_count"], 2)
        self.assertFalse(data["dimension_mismatch"])

    def test_validate_recipe_aspect_ratio_and_fingerprint(self):
        # 1. Matching Aspect Ratio (1920x1080 and 1280x720 both have 16:9 = ~1.778)
        recipe = {
            "recipe_version": "1.0",
            "board_name": "TEST_BOARD_AR",
            "image_size": {"width": 1920, "height": 1080, "aspect_ratio": 1.7778},
            "image_fingerprint": "abc123hash",
            "sensitivity": "balanced",
            "components": [
                {"name": "U1_MCU", "normalized_bbox": [0.3021, 0.3704, 0.1042, 0.1852]},
            ],
        }
        resp = client.post("/api/recipes/validate?expected_width=1280&expected_height=720&expected_fingerprint=abc123hash", json=recipe)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["valid"])
        self.assertFalse(data["aspect_ratio_mismatch"])
        self.assertFalse(data["fingerprint_mismatch"])

        # 2. Differing Aspect Ratio (1920x1080 AR 1.778 vs 1000x1000 AR 1.0)
        resp_diff = client.post("/api/recipes/validate?expected_width=1000&expected_height=1000&expected_fingerprint=different_hash", json=recipe)
        self.assertEqual(resp_diff.status_code, 200)
        data_diff = resp_diff.json()
        self.assertTrue(data_diff["valid"])
        self.assertTrue(data_diff["aspect_ratio_mismatch"])
        self.assertTrue(data_diff["fingerprint_mismatch"])
        self.assertIn("Aspect ratio warning", data_diff["aspect_ratio_warning"])
        self.assertIn("fingerprint", data_diff["fingerprint_warning"])

    def test_operator_signoff_and_csv_report_export(self):
        # 1. Upload reference
        with open(SAMPLE_DIR / "reference.png", "rb") as f:
            ref_resp = client.post("/api/reference", files={"file": ("reference.png", f, "image/png")})
        session_id = ref_resp.json()["session_id"]

        # 2. Register components
        client.post(
            f"/api/sessions/{session_id}/components",
            json={"components": [{"name": "U1_MCU", "bbox": [580, 400, 200, 200]}]},
        )

        # 3. Inspect a test board
        with open(SAMPLE_DIR / "calibration/calib_01_all_ok_nominal.png", "rb") as fp:
            client.post(
                "/api/inspect",
                data={"session_id": session_id, "sensitivity": "balanced"},
                files=[("test_images", ("board_nominal.png", fp, "image/png"))],
            )

        # 4. Record sign-off
        signoff_payload = {
            "filename": "board_nominal.png",
            "component_name": "U1_MCU",
            "final_status": "PRESENT",
            "operator_id": "OP-702",
            "note": "Verified under microscope",
        }
        sign_resp = client.post(f"/api/sessions/{session_id}/signoff", json=signoff_payload)
        self.assertEqual(sign_resp.status_code, 200)
        self.assertEqual(sign_resp.json()["status"], "success")

        # 5. Export CSV Report
        csv_resp = client.get(f"/api/sessions/{session_id}/report.csv")
        self.assertEqual(csv_resp.status_code, 200)
        self.assertIn("text/csv", csv_resp.headers["content-type"])
        csv_text = csv_resp.text
        self.assertIn("Timestamp,Session_ID,Board_Filename", csv_text)
        self.assertIn("board_nominal.png", csv_text)
        self.assertIn("OP-702", csv_text)
        self.assertIn("Verified under microscope", csv_text)

    def test_operator_defect_override_permitted(self):
        # 1. Upload reference
        with open(SAMPLE_DIR / "reference.png", "rb") as f:
            ref_resp = client.post("/api/reference", files={"file": ("reference.png", f, "image/png")})
        session_id = ref_resp.json()["session_id"]

        # 2. Register components
        client.post(
            f"/api/sessions/{session_id}/components",
            json={"components": [{"name": "U1_MCU", "bbox": [580, 400, 200, 200]}]},
        )

        # 3. Inspect a test board that has a missing component
        with open(SAMPLE_DIR / "calibration/calib_08_missing_u1_mcu.png", "rb") as fp:
            client.post(
                "/api/inspect",
                data={"session_id": session_id, "sensitivity": "balanced"},
                files=[("test_images", ("board_missing.png", fp, "image/png"))],
            )

        # 4. Standard unified operator overrides the defect to PRESENT without 403 restriction
        signoff_payload = {
            "filename": "board_missing.png",
            "component_name": "U1_MCU",
            "final_status": "PRESENT",
            "operator_id": "OP-101",
            "operator_role": "OPERATOR",
            "note": "Authorized override by SMT Operator",
        }
        sign_resp = client.post(f"/api/sessions/{session_id}/signoff", json=signoff_payload)
        self.assertEqual(sign_resp.status_code, 200)
        self.assertEqual(sign_resp.json()["status"], "success")

    def test_validate_recipe_dimension_mismatch(self):
        recipe = {
            "recipe_version": "1.0",
            "board_name": "TEST_BOARD_REV1",
            "image_size": {"width": 1920, "height": 1080},
            "sensitivity": "balanced",
            "components": [
                {"name": "U1_MCU", "normalized_bbox": [0.3021, 0.3704, 0.1042, 0.1852]},
            ],
        }
        # Expected is 1000x1000 (aspect ratio 1.0), but recipe was 1920x1080 (1.778)
        response = client.post("/api/recipes/validate?expected_width=1000&expected_height=1000", json=recipe)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["valid"])
        self.assertTrue(data["dimension_mismatch"])
        self.assertIn("Aspect ratio warning", data["dimension_warning"])

    def test_validate_recipe_empty_components_rejection(self):
        recipe = {
            "recipe_version": "1.0",
            "board_name": "TEST_BOARD_EMPTY",
            "components": [],
        }
        response = client.post("/api/recipes/validate", json=recipe)
        self.assertEqual(response.status_code, 400)
        self.assertIn("zero components", response.json()["detail"])

    def test_validate_recipe_invalid_normalized_bbox(self):
        recipe = {
            "recipe_version": "1.0",
            "board_name": "TEST_BOARD_INVALID",
            "components": [
                {"name": "U1_MCU", "normalized_bbox": [1.5, 0.3, 0.2, 0.2]},  # 1.5 > 1.0
            ],
        }
        response = client.post("/api/recipes/validate", json=recipe)
        self.assertEqual(response.status_code, 400)
        self.assertIn("between 0.0 and 1.0", response.json()["detail"])

    def test_get_physical_presets(self):
        response = client.get("/api/presets")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("presets", data)
        presets = data["presets"]
        self.assertGreaterEqual(len(presets), 5)
        preset_ids = [p["id"] for p in presets]
        self.assertIn("arduino_uno_dip", preset_ids)
        self.assertIn("phenolic_appliance_board", preset_ids)
        self.assertIn("industrial_weighing_pms63", preset_ids)

        # Check first preset attributes
        p0 = presets[0]
        self.assertIn("reference_url", p0)
        self.assertIn("components", p0)
        self.assertGreater(len(p0["components"]), 0)
        self.assertIn("sample_tests", p0)

    def test_get_auth_profiles(self):
        response = client.get("/api/auth/profiles")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("profiles", data)
        profiles = data["profiles"]
        self.assertGreaterEqual(len(profiles), 1)
        op_ids = [p["operator_id"] for p in profiles]
        self.assertIn("OP-101", op_ids)

    def test_operator_login_flow(self):
        # 1. Login with existing profile
        resp = client.post("/api/auth/login", json={"operator_id": "OP-101"})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["success"])
        self.assertEqual(data["user"]["name"], "Lead SMT Operator")
        self.assertEqual(data["user"]["role"], "OPERATOR")
        self.assertIn("session_token", data["user"])

        # 2. Login with custom operator
        resp_custom = client.post(
            "/api/auth/login",
            json={"operator_id": "TECH-505", "name": "Alex Mercer", "role": "OPERATOR"}
        )
        self.assertEqual(resp_custom.status_code, 200)
        data_custom = resp_custom.json()
        self.assertTrue(data_custom["success"])
        self.assertEqual(data_custom["user"]["operator_id"], "TECH-505")
        self.assertEqual(data_custom["user"]["name"], "Alex Mercer")
        self.assertEqual(data_custom["user"]["role"], "OPERATOR")

    def test_save_custom_recipe_lifecycle(self):
        # 1. Upload reference
        with open(SAMPLE_DIR / "reference.png", "rb") as f:
            ref_resp = client.post("/api/reference", files={"file": ("reference.png", f, "image/png")})
        session_id = ref_resp.json()["session_id"]

        # 2. Register components
        client.post(
            f"/api/sessions/{session_id}/components",
            json={"components": [{"name": "R1_PULLUP", "bbox": [100, 200, 50, 60]}]},
        )

        # 3. Save recipe to Board & CAD Studio
        save_resp = client.post(
            f"/api/sessions/{session_id}/save-recipe",
            json={"name": "Test Custom Studio Board", "tier": "Custom Recipe", "category": "Testing"},
        )
        self.assertEqual(save_resp.status_code, 200)
        save_data = save_resp.json()
        self.assertEqual(save_data["status"], "success")
        recipe_id = save_data["recipe_id"]
        self.assertIn("custom_", recipe_id)

        # 4. Check that /api/presets returns the new custom recipe
        presets_resp = client.get("/api/presets")
        self.assertEqual(presets_resp.status_code, 200)
        p_data = presets_resp.json()
        custom_presets = [p for p in p_data["presets"] if p.get("is_custom")]
        self.assertTrue(any(p["id"] == recipe_id for p in custom_presets))

        # 5. Clean up by deleting the recipe
        del_resp = client.delete(f"/api/recipes/{recipe_id}")
        self.assertEqual(del_resp.status_code, 200)
        self.assertEqual(del_resp.json()["status"], "success")

        # 6. Verify it's no longer in presets
        presets_after = client.get("/api/presets").json()
        self.assertFalse(any(p["id"] == recipe_id for p in presets_after["presets"]))

    def test_aligned_image_and_loupe_endpoints(self):
        # 1. Upload reference
        with open(SAMPLE_DIR / "reference.png", "rb") as f:
            ref_resp = client.post("/api/reference", files={"file": ("reference.png", f, "image/png")})
        session_id = ref_resp.json()["session_id"]

        # 2. Register component U1
        client.post(
            f"/api/sessions/{session_id}/components",
            json={"components": [{"name": "U1", "bbox": [212, 254, 190, 147]}]},
        )

        # 3. Inspect a test image
        with open(SAMPLE_DIR / "calibration/calib_08_missing_u1_mcu.png", "rb") as f:
            insp_resp = client.post(
                "/api/inspect",
                data={"session_id": session_id},
                files=[("test_images", ("calib_08_missing_u1_mcu.png", f, "image/png"))],
            )
        self.assertEqual(insp_resp.status_code, 200)

        # 4. Test aligned-image endpoint
        aligned_resp = client.get(f"/api/sessions/{session_id}/aligned-image/calib_08_missing_u1_mcu.png")
        self.assertEqual(aligned_resp.status_code, 200)
        self.assertEqual(aligned_resp.headers["content-type"], "image/png")
        self.assertGreater(len(aligned_resp.content), 1000)

        # Nonexistent file returns 404
        bad_aligned = client.get(f"/api/sessions/{session_id}/aligned-image/nonexistent.png")
        self.assertEqual(bad_aligned.status_code, 404)

        # 5. Test loupe endpoint
        loupe_resp = client.get(f"/api/sessions/{session_id}/loupe/calib_08_missing_u1_mcu.png/U1")
        self.assertEqual(loupe_resp.status_code, 200)
        loupe_data = loupe_resp.json()
        self.assertEqual(loupe_data["component_name"], "U1")
        self.assertEqual(loupe_data["filename"], "calib_08_missing_u1_mcu.png")
        self.assertTrue(loupe_data["ref_crop_url"].startswith("data:image/png;base64,"))
        self.assertTrue(loupe_data["test_crop_url"].startswith("data:image/png;base64,"))
        self.assertTrue(loupe_data["diff_crop_url"].startswith("data:image/png;base64,"))
        self.assertIn("zncc_score", loupe_data)
        self.assertIn("patch_diff", loupe_data)
        self.assertIn("tilt_deg", loupe_data)
        self.assertIn("shift_dist_px", loupe_data)
        self.assertIn("shift_px", loupe_data)
        self.assertIn("max_pixel_dev_pct", loupe_data)

        # Nonexistent component returns 404
        bad_loupe = client.get(f"/api/sessions/{session_id}/loupe/calib_08_missing_u1_mcu.png/NONEXISTENT")
        self.assertEqual(bad_loupe.status_code, 404)


if __name__ == "__main__":
    unittest.main()
