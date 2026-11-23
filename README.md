# PCB Missing Component Detector (Task B)

An offline, zero-CDN Automated Optical Inspection (AOI) web platform for detecting missing electronic surface-mount devices (SMD) on printed circuit boards. The system pairs sub-pixel Euclidean/Affine alignment (ECC) with local Zero-mean Normalized Cross-Correlation (ZNCC) and patch difference analysis to deliver fast, transparent, and calibrated defect detection without requiring GPU infrastructure or massive labeled datasets.

---

## What the Application Does

* **Golden Reference & Component Registration**: Allows engineers to capture or upload a known-good "Golden Board", interactively annotate component bounding boxes with normalized coordinates, and assign detection sensitivities.
* **Global Sub-Pixel Image Alignment**: Automatically compensates for PCB mechanical placement shifts and camera rotation using OpenCV's Enhanced Correlation Coefficient (ECC) maximization algorithm.
* **Missing Component Detection**: Performs a local sub-pixel translation search ($\pm 4\text{ px}$) around each component ROI, computing multi-channel ZNCC and normalized patch absolute differences against calibrated dual-threshold decision gates.
* **3-State Classification & Triage**: Classifies every inspected part into `PRESENT` (OK), `MISSING` (DEFECT), or `UNCERTAIN` (REVIEW), ensuring ambiguous parts (due to shadows or minor reflections) are safely escalated rather than falsely rejected.
* **Enterprise Features**: Includes offline JSON recipe save/load with 256-bit luminance Average Hash (aHash) fingerprinting, live webcam/USB microscope video capture, human-in-the-loop operator sign-off, dynamic First-Pass Yield (FPY) tracking, and audit-ready CSV/printable Inspection Reports.

---

## Installation & Execution

### Prerequisites
* Python 3.10, 3.11, or 3.12
* Windows, Linux, or macOS
* Modern web browser (Chrome, Edge, Firefox, Safari)

### 1. Clone & Set Up Virtual Environment
```bash
git clone https://github.com/Krutik50/pcb-missing-part-detector.git
cd pcb-missing-part-detector

# Create and activate virtual environment
python -m venv .venv

# Windows (Command Prompt / PowerShell):
.venv\Scripts\activate

# Linux / macOS:
source .venv/bin/activate
```

### 2. Install Pinned Dependencies
```bash
pip install -r requirements.txt
```
*(For complete environment reproducibility, the full frozen dependency closure is also available in `requirements-lock.txt`.)*

### 3. Run the Application
```bash
python run.py
```
Open your web browser and navigate to:
```
http://127.0.0.1:8000
```

---

## 3-Step Operator Workflow

```
 ┌────────────────────────┐      ┌────────────────────────┐      ┌────────────────────────┐
 │ Step 1: Golden Board   │ ───► │ Step 2: Mark ROIs      │ ───► │ Step 3: Batch Inspect  │
 │ Upload or Live Camera  │      │ Draw boxes / Load JSON │      │ Upload & Audit Reports │
 └────────────────────────┘      └────────────────────────┘      └────────────────────────┘
```

1. **Step 1: Set Reference Board**
   * Upload a high-resolution photo of a fully populated, defect-free golden board, OR click **Start Camera** in the Live Camera tab to freeze a live frame.
   * *(Optional)* In the collapsed **Sample data for testing** drawer, click **Load Sample Reference** to test with the bundled calibration reference image.

2. **Step 2: Register Components**
   * Click and drag directly on the interactive canvas to draw bounding boxes around target components (resistors, capacitors, ICs, LEDs, crystals).
   * Enter a designator name (e.g., `U1_MCU`, `C1`, `R1`) and select a sensitivity profile (`Strict`, `Normal`, `Tolerant`).
   * *(Optional)* Click **Download Recipe** to save your component coordinates for future production runs, or click **Load Standard 14 Parts** in the sample data drawer.

3. **Step 3: Multi-Board Batch Inspection**
   * Upload one or more test board images (or capture them sequentially via the live camera).
   * Click **Run Inspection**.
   * Review board-level verdicts (`OK`, `DEFECT`, `REVIEW`), inspect annotated visual crops, review side-by-side reference vs test diffs, and sign off on any flagged components.

---

## Extra Features

### 1. Recipe Save & Load
* **Format**: Portable JSON file recording board name, reference image dimensions (`width`, `height`, `aspect_ratio`), a 256-bit luminance Average Hash (`image_fingerprint`), and normalized bounding boxes $[x_1, y_1, x_2, y_2] \in [0, 1]$.
* **Fingerprint & Dimension Validation**:
  * Calculates an aHash ($16 \times 16$ grayscale downscaled luminance thresholded against mean luminance, generating 256 bits / 64 hex characters).
  * Compares geometric aspect ratios ($W/H$). If a loaded recipe has an aspect ratio difference exceeding 5% or a mismatched image fingerprint, a clear yellow advisory warning is displayed, but inspection remains enabled since bounding boxes are normalized.

### 2. Live Camera Acquisition Station
* **Webcam & USB Microscope Support**: Directly accesses local video hardware via the browser's standard `navigator.mediaDevices.getUserMedia` API.
* **Positioning Guidance**: Features live crosshairs and an on-screen guidance hint: *"Capture reference and test boards with the same camera position and lighting to ensure sub-pixel alignment."*
* **One-Click Frame Freezing**: The **Capture Frame** button grabs the active video frame and transfers it directly into Step 1 (Golden Reference) or Step 3 (Test Batch).

### 3. Operator Review Sign-off & Inspection Reports
* **Human-in-the-Loop Triage**: For any component or board flagged as `REVIEW` or `DEFECT`, operators can click **Verify Present** or **Confirm Missing**.
* **Audit Trail Integrity**: Prompts for an Operator Badge ID and optional notes. The system stores the human override in `final_status` while **strictly preserving the original algorithmic `machine_status`** to maintain audit traceability.
* **Yield Metrics & Pareto Tally**: The batch summary panel dynamically tracks:
  * Inspected boards tally (`OK`, `DEFECT`, `REVIEW`).
  * First-Pass Yield (FPY % based strictly on raw machine verdicts).
  * Operational Yield (% based on final status post operator sign-off).
  * Component Defect Pareto tally highlighting the most frequently missing part designators.
* **Audit Export**:
  * **Download CSV**: Generates an audit-ready CSV file via `/api/session/{id}/export_report` with timestamps, board filenames, part designators, machine verdicts, human sign-offs, and scores.
  * **Printable Inspection Report**: Opens a cleanly formatted, print-optimized browser inspection summary (`window.print()`).

> **Note on Storage**: Active sessions, inspection runs, and operator sign-offs are held in server memory for maximum execution speed and zero-configuration setup. They are volatile and reset upon server restart. Export recipes and CSV inspection reports before restarting the service.

---

## Empirical Benchmark & Evaluation Results

All quantitative evaluations below were executed on synthetic PCB boards produced by a single image generation engine (`generate_samples.py`) modeling 1080p boards ($1920 \times 1080$) with 14 target components per board.

### In-Sample Calibration Results (20 Boards)
Used to establish and freeze calibrated dual-threshold gates (`ZNCC`: `[0.86, 0.89]`, `Patch Diff`: `[0.065, 0.090]`).
* **Source Run File**: [results/calibration_balanced.txt](results/calibration_balanced.txt)
* **Total Boards Evaluated**: 20
* **Board-Level Accuracy**: 20 / 20 (100.0%)
* **Total Components Tested**: 280
* **Expected Missing Components**: 20
* **Detected Missing Components**: 20
* **False Alarms (False Positives)**: 0
* **Missed Defects (False Negatives)**: 0
* **Measured Processing Speed**: Average 154.0 ms per full 1080p board (Min: 127.7 ms, Max: 172.8 ms), quoted from `results/calibration_balanced.txt` under `CALIBRATION (20 images)`.

### Held-Out Evaluation Results (10 Unseen Boards)
Evaluated on 10 held-out test boards with severe illumination shifts, glare artifacts, and multi-component defects.
* **Source Run File**: [results/heldout_once.txt](results/heldout_once.txt)
* **Total Boards Evaluated**: 10
* **Board-Level Accuracy**: 8 / 10 (80.0%)
* **Total Components Tested**: 140
* **Expected Missing Components**: 14
* **Missing Components Successfully Caught**: 13 of 14 (92.9% defect recall)
* **Missed Defects (False Negatives)**: 1 (Board `test_10_missing_multi_scattered.png`: component `U3_EEPROM` was unpopulated, but its bare copper PCB footprint and silkscreen outline mirrored the IC package, scoring ZNCC 0.866 and Diff 0.053, which fell just outside the defect boundary).
* **False Alarms (False Positives)**: 1 (Board `test_03_all_ok_severe_dual_glare.png`: component `U1_MCU` was present, but severe specular reflection saturated its lead frame, causing its correlation to dip).
* **Uncertain / Borderline Triage Calls**: 12 (Correctly routed to the Operator Sign-off console).
* **Measured Processing Speed**: Average 169.0 ms per full 1080p board (Min: 129.3 ms, Max: 234.4 ms; ~0.41 ms per component ROI crop), quoted from `results/heldout_once.txt` under `TEST_HELDOUT (10 images)`.

---

## Limitations

1. **Empty IC Footprint Structural Reflection**: On small SMD integrated circuits (such as SOIC-8 `U3_EEPROM`), empty PCB footprints feature shiny tinned solder pads and silkscreen borders that structurally resemble the populated chip. Under standard illumination, an empty footprint can exhibit a ZNCC score up to ~0.85, narrowing the safety margin between missing and present states.
2. **Specular Glare Sensitivity**: Extreme directional lighting or bare LED reflections create localized specular saturation spots ($V \approx 255$). If a glare hotspot directly blankets component pins or markings, local cross-correlation degrades, potentially triggering false alarms (observed on `U1_MCU` under extreme dual glare).
3. **Bounding Box Sizing Sensitivity**:
   * **Tight bounding boxes** (-20% margin) that clip outer solder fillets leave only the uniform plastic IC mold body, which degrades under lighting shifts and triggers false alarms.
   * **Loose bounding boxes** (+20% margin) capture excessive surrounding green PCB substrate, whose uniform background artificially inflates ZNCC on empty footprints, causing missed defects or uncertain calls.
4. **Synthetic Data Domain Gap**: All benchmarks were performed on synthetic images generated by `generate_samples.py`. Real-world factory environments introduce non-linear lens distortion, physical board warping (bow/twist), solder flux residue, component manufacturing lot variations, and non-Lambertian solder meniscus reflections.
5. **Session Volatility & Lack of Multi-User Auth**: The application does not include user authentication, role-based access control (RBAC), or a persistent database. All session data is stored in memory and cleared on process termination.

---

## Future Work (Untested Engineering Concepts)

1. **Deep Learning Verification Model**:
   * *Concept*: A lightweight Siamese convolutional network (e.g., MobileNetV3 or ResNet-18 feature extractor) trained with contrastive loss on component pairs.
   * *Rationale*: Rather than replacing the fast classical pipeline, the neural network would act as an automated second-tier verifier solely for parts classified as `UNCERTAIN`, resolving specular glare and empty footprint ambiguities without requiring GPU inference on clear cases.
2. **Specular Glare Masking**:
   * *Concept*: Dynamically threshold over-saturated pixel regions ($V > 250$ in HSV color space) to generate a binary glare mask, excluding those pixels from ZNCC and Patch Diff summation.
   * *Rationale*: Prevents localized reflection hotspots from degrading the correlation score of large components like QFP microcontrollers.
3. **Decoupled Package Body vs. Solder Pad Sub-ROIs**:
   * *Concept*: Automatically decompose each component bounding box into an inner "Package Body" sub-ROI and an outer "Solder Fillet/Pad" sub-ROI.
   * *Rationale*: Evaluates solder presence and component presence independently. If the solder pads are shiny but the central body lacks color and texture variation, the component can be classified as missing with significantly higher statistical confidence.

---

## Architecture

For an in-depth breakdown of system components, pipeline stages, mathematical formulations, and engineering trade-offs, see [ARCHITECTURE.md](ARCHITECTURE.md) and the interactive visual diagram in [docs/architecture.html](docs/architecture.html).
