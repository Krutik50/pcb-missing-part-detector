# System Architecture: Offline PCB Automated Optical Inspection (AOI)

This document describes the end-to-end architecture, pipeline design, data contracts, and engineering trade-offs of the **PCB Missing Component Detector (Task B)**.

---

## 1. High-Level Architecture Overview

The system is architected as an air-gapped, zero-CDN, offline-first Automated Optical Inspection (AOI) station. It pairs a lightweight client-side presentation layer (HTML5 Canvas, Vanilla JS, CSS) with a high-performance Python computer vision backend (FastAPI, OpenCV, NumPy).

![System Architecture](docs/architecture.svg)

> **Interactive Architecture Diagram**: An interactive, explorable version of this architecture diagram with live signal flows, semantic passports, and visual inspection tools is available at [docs/architecture.html](docs/architecture.html).

---

## 2. System Subsystems and Flow

### 2.1 Frontend Presentation Tier (Browser Client)
The browser client operates completely air-gapped with zero external CDN dependencies, running directly from FastAPI's static mount.

1. **Live Camera Station (`navigator.mediaDevices.getUserMedia`)**:
   - Captures real-time video frames from integrated webcams or industrial USB inspection microscopes.
   - Provides live reticle/crosshairs and positioning hints ("Capture reference and test boards with the same camera position and lighting").
   - Freezes captured frames and transfers them seamlessly to the Reference Board or Test Batch ingestion pipelines without disk roundtrips.

2. **Recipe Engine (Save / Load / Verify)**:
   - Serializes golden board configurations to lightweight JSON recipes containing:
     - Board name and reference dimensions (`width`, `height`, `aspect_ratio`).
     - A 256-bit Average Hash (`image_fingerprint`) computed from a downscaled $16 \times 16$ grayscale canvas.
     - Normalized bounding boxes (`[x1, y1, x2, y2]` in $[0, 1]$ relative coordinates).
     - Component detection sensitivity settings (`strict`, `normal`, `tolerant`).
   - Validates incoming recipes against reference images: warns if the aspect ratio differs by $>5\%$ or if the 256-bit fingerprint differs, while still allowing the operator to proceed.

3. **Interactive ROI Canvas**:
   - Renders the golden reference image with full aspect-ratio preservation.
   - Provides drag-and-drop bounding box creation and interactive handles for component registration.
   - Features a collapsed **Sample data for testing** drawer to prevent sample fixtures from interfering with real customer production boards.

4. **Multi-Board Batch Inspection Console**:
   - Handles multi-file drag-and-drop or sequential camera captures.
   - Displays real-time inspection progress, per-board verdict badges (`OK`, `DEFECT`, `REVIEW`), and side-by-side reference vs test crop diff viewers.

5. **Operator Review & KPI Sign-Off Console**:
   - Human-in-the-loop review station for boards or components flagged as `REVIEW` or `DEFECT`.
   - Allows operators to sign off with **Verify Present** or **Confirm Missing**, capturing Operator Badge ID and audit notes.
   - Preserves original machine verdicts side-by-side with human overrides.
   - Computes First-Pass Yield (FPY) versus post-sign-off Operational Yield in real time.
   - Displays a Pareto tally of the most frequently missing component designators.
   - Generates downloadable CSV audit logs and opens formatted printable Inspection Reports.

---

### 2.2 Backend Application Tier (FastAPI & OpenCV)
The backend is powered by FastAPI and Uvicorn, structured for deterministic execution and low latency.

* **REST Routing Layer (`app/main.py`)**:
  - `POST /api/session/reference`: Ingests reference image, initializes session.
  - `POST /api/session/{id}/components`: Registers normalized component ROIs.
  - `POST /api/session/{id}/inspect`: Executes batch board alignment and defect detection.
  - `GET /api/session/{id}/recipe`: Exports JSON recipe.
  - `POST /api/session/{id}/validate_recipe`: Audits recipe fingerprint and aspect ratio.
  - `POST /api/session/{id}/signoff`: Records operator triage sign-offs.
  - `GET /api/session/{id}/export_report`: Exports complete machine + human audit CSV.
  - `GET /api/health`: Service liveness check.

* **In-Memory Session Store (`app/core/session.py`)**:
  - Thread-safe volatile storage maintaining session state, OpenCV BGR reference matrices, registered ROIs, and inspection history.

---

### 2.3 Computer Vision Pipeline (`app/core/`)

The inspection core consists of a three-stage classical computer vision pipeline:

```
[ Incoming Test Board Image ]
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 0: Global Board Alignment (ECC Maximization)          │
│ • cv2.findTransformECC (MOTION_EUCLIDEAN / MOTION_AFFINE)   │
│ • Sub-pixel translation & rotation recovery (warpAffine)    │
│ • Alignment confidence score (rho >= 0.70)                  │
└────────────────────────────┬────────────────────────────────┘
                             │ Aligned Test Image
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Local Sub-pixel Search & Feature Correlation       │
│ • Local translation search grid (+/- 4 pixels)              │
│ • Zero-mean Normalized Cross-Correlation (ZNCC)             │
│ • Multi-channel Patch Mean Absolute Difference (Patch Diff) │
└────────────────────────────┬────────────────────────────────┘
                             │ (ZNCC, Patch Diff) per ROI
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: Calibrated 3-State Classification & Triage         │
│ • High ZNCC (>= 0.89) & Low Diff (<= 0.065)   ==> PRESENT   │
│ • Low ZNCC  (<= 0.86) & High Diff (>= 0.090)  ==> MISSING   │
│ • Intermediate Ambiguous Region              ==> UNCERTAIN │
└────────────────────────────┬────────────────────────────────┘
                             │ Annotated Crops & Board Verdicts
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: Human-in-the-Loop Review & Audit Logging           │
│ • Route UNCERTAIN parts to Operator Sign-off               │
│ • Preserve Machine Verdict vs Operator Final Override       │
│ • First-Pass Yield (FPY) vs Final Operational Yield         │
└─────────────────────────────────────────────────────────────┘
```

#### Mathematical Formulation

1. **Global Alignment (ECC)**:
   The affine or Euclidean warp matrix $W(p)$ maximizes the correlation coefficient between the warped test image $I_w(x)$ and reference image $I_r(x)$:
   $$\rho = \frac{\sum_x (I_r(x) - \bar{I}_r)(I_w(x) - \bar{I}_w)}{\sqrt{\sum_x (I_r(x) - \bar{I}_r)^2 \sum_x (I_w(x) - \bar{I}_w)^2}}$$

2. **Local Zero-mean Normalized Cross-Correlation (ZNCC)**:
   For each component ROI, a local window search ($\Delta x, \Delta y \in [-4, +4]$) finds the maximum correlation:
   $$\text{ZNCC} = \max_{\Delta x, \Delta y} \frac{\sum_{i,j} (T(i, j) - \bar{T})(R(i+\Delta x, j+\Delta y) - \bar{R})}{\sqrt{\sum_{i,j}(T(i,j)-\bar{T})^2 \sum_{i,j}(R(i+\Delta x, j+\Delta y)-\bar{R})^2}}$$

3. **Normalized Patch Difference**:
   Measures absolute intensity deviation across all color channels normalized to $[0, 1]$:
   $$\text{Diff} = \frac{1}{3 \cdot W \cdot H} \sum_{c=1}^3 \sum_{x=1}^W \sum_{y=1}^H \frac{|I_{\text{test}}(x, y, c) - I_{\text{ref}}(x, y, c)|}{255}$$

---

## 3. Engineering Trade-offs & Design Decisions

### 3.1 Classical CV (ECC + ZNCC) vs. Deep Learning (YOLO / Siamese Networks)
* **Zero-Shot Instant Deployment**: In real-world electronics manufacturing and high-mix low-volume (HMLV) prototyping, collecting hundreds of annotated defect images per PCB design is cost-prohibitive. Classical template matching requires only a single "Golden Board" reference and operates immediately without dataset collection, training, or labeling overhead.
* **Deterministic Interpretability**: Neural network classifications output opaque probabilities sensitive to adversarial lighting shifts. In contrast, ZNCC and Patch Diff provide bounded, physically interpretable metrics ($[-1, 1]$ and $[0, 1]$) with transparent calibration thresholds.
* **CPU Efficiency**: The entire pipeline executes on low-cost factory hardware or laptops without requiring CUDA GPUs or heavy runtime dependencies.
* **Trade-off**: Classical template matching is sensitive to extreme specular glare (hotspots) and bare copper PCB trace reflections where an unpopulated footprint visually mirrors solder pads.

### 3.2 In-Memory Session Store vs. Persistent Database (PostgreSQL / SQLite)
* **Simplicity & Portability**: Storing active sessions in a thread-safe Python dictionary eliminates database migrations, external daemons, and connection management, allowing the app to run completely out-of-the-box (`python run.py`).
* **Low Latency**: High-resolution OpenCV image arrays reside directly in RAM without serializing to disk or blob stores between pipeline stages.
* **Trade-off**: Sessions, unexported inspection histories, and sign-offs are volatile and reset upon server restart. To mitigate data loss, the application provides immediate recipe JSON export and CSV/printable report generation for long-term record-keeping.

### 3.3 Aspect-Ratio Validation vs. Strict Pixel Dimension Locking
* **Sensor & Resolution Agnostic**: Bounding boxes are stored as normalized coordinates $[x_1, y_1, x_2, y_2] \in [0, 1]$. An operator can capture a reference board at $1920 \times 1080$ and later inspect boards using a $1280 \times 720$ camera stream without coordinate degradation.
* **Smart Guardrails**: Rather than strictly rejecting mismatched pixel resolutions, the system calculates the geometric aspect ratio ($W / H$). If the aspect ratio deviates by $>5\%$, a yellow warning alerts the operator to potential distortion or orientation mismatches while still allowing inspection to proceed.

### 3.4 3-State Classification (OK / DEFECT / REVIEW) vs. Binary Classification
* **False Alarm Suppression**: In high-reliability electronics inspection, false alarms erode operator trust, while missed defects compromise quality. Binary thresholds inevitably force ambiguous cases (minor shadows, minor solder paste flux variations) into false positive defects.
* **Human-in-the-Loop Safety**: The intermediate `UNCERTAIN` classification routes borderline components to a human operator sign-off workflow. This preserves the original algorithmic score while recording human verification, enabling accurate First-Pass Yield (FPY) tracking.
