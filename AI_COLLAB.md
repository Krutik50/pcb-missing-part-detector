# Human-AI Collaboration Record: Engineering Decision Log

> **Project**: Industrial Automated Optical Inspection (AOI) — Missing & Defective SMT Component Detector  
> **Repository**: `PCB_missing_component_detector`  
> **Context**: Evolution from an experimental prototype into a zero-CDN, air-gapped, production-grade SMT assembly inspection station.

---

## 1. Executive Summary: Shared Understanding & Steering

Throughout the lifecycle of this project, the partnership between the Human Engineer and the AI followed a rigorous steering dynamic:
1. **AI Role**: Technical prototyping, mathematical modeling (ECC homography, ZNCC, Deep Metric learning), test suite authoring, and rapid code generation.
2. **Human Engineer Role**: Architectural governance, domain realism, factory floor usability, noise elimination, and cutting through algorithmic hype.

When left undirected, the AI naturally gravitated toward typical developer tendencies: adding extraneous synthetic simulation buttons, over-engineering complex multi-role logins, keeping obsolete exploratory scratchpads, and referencing popular buzzwords (like YOLO) even when mathematically inferior for zero-shot golden-board inspection. 

The Human Engineer repeatedly steered the system back to **manufacturing reality**: prioritizing real physical PCB boards, eliminating shop-floor friction, insisting on micro-optical inspection accuracy, and demanding a lean, well-organized codebase.

---

## 2. Key Collaboration Decisions (Steering Log)

---

### Decision 1: Interstitial "Save Board Recipe to CAD Studio" Workflow

* **What the AI Suggested**:  
  The AI initially kept user-drawn component footprints in ephemeral session memory (`in-memory session state`). When the user asked to preserve custom boards, the AI proposed a traditional web-app pattern: downloading a JSON file to the operator's desktop with a manual "Import Recipe" button on subsequent visits.
* **What the Engineer Decided**:  
  The engineer rejected separate import/export file handling and designed an intuitive interstitial manufacturing workflow: immediately after finishing component footprint marking and clicking *Proceed to Batch Inspection*, the station presents an interstitial prompt asking whether the operator wants to permanently save the reference board and annotated footprints into the **Board & CAD Studio**. If confirmed, it is saved directly to `data/recipes/` and appears dynamically alongside the 5 hardware presets.
* **Why**:  
  In a real factory environment, line operators do not manage file downloads or JSON schemas. A seamless in-flow prompt ensures newly onboarded boards are instantly cataloged into the physical preset library for one-click re-use.
* **Evidence**:  
  * Commit [`ed6a48b`](https://github.com/Krutik50/pcb-missing-part-detector/commit/ed6a48b): *"feat: prompt to save board recipe to CAD Studio before batch inspection and remove physical test batch button"*  
  * Backend endpoints: `POST /api/session/{session_id}/save_recipe` and `GET /api/presets`.

---

### Decision 2: Elimination of "Export Recipes (JSON)" Button

* **What the AI Suggested**:  
  The AI placed an `Export Recipes (JSON)` button in the top-right header of the Board & CAD Studio to allow technical extraction of recipes.
* **What the Engineer Decided**:  
  The engineer explicitly instructed the AI to remove this button: *"export recipes(json) button on the top right in Board & CAD Studio please remove it as it is of not needed"*.
* **Why**:  
  The Board & CAD Studio exists to select and load golden reference boards into the inspection station. Exposing a raw JSON export button in the primary interface added visual noise and ran counter to the air-gapped, appliance-like operation of the hardware controller.
* **Evidence**:  
  * Commit [`45e6991`](https://github.com/Krutik50/pcb-missing-part-detector/commit/45e6991): *"feat: remove export recipes button and clean up legacy results text files"*  
  * Removed lines from `app/static/index.html` header tools.

---

### Decision 3: Clarifying True Pipeline Architecture vs. YOLO Hype

* **What the AI Suggested**:  
  Early experimental iterations referenced a "YOLO Deep Learning Pipeline" for component detection, even generating a sample `dataset.yaml` file.
* **What the Engineer Decided**:  
  The engineer directly challenged the AI: *"are we really using yolo model ??"* and demanded exact metrics on what model was actually running, what dataset it was trained on, and its true accuracy, precision, and recall.
* **Why**:  
  The engineer demanded technical transparency over marketing claims. In high-mix, low-volume (HMLV) SMT manufacturing, object detection models like YOLO fail on novel golden boards because they cannot generalize to unseen component geometries without thousands of custom bounding-box annotations per board. The true production pipeline needed zero-shot golden comparison: Euclidean ECC global homography alignment + multi-channel ZNCC correlation + PyTorch Deep SMT Verifier.
* **Evidence**:  
  * Commit [`4a12549`](https://github.com/Krutik50/pcb-missing-part-detector/commit/4a12549): Removed dead YOLO configs (`data/yolo_dataset/dataset.yaml`).  
  * Architectural documentation updated in `README.md` and `ARCHITECTURE.md` confirming 97.1%–98.4% accuracy, 100% precision, and 100% recall on missing components using deterministic CV + PyTorch ConvNet.

---

### Decision 4: Upgrading the 3× Digital Optical Loupe from Pixel Zoom to Optical Fidelity

* **What the AI Suggested**:  
  The AI implemented a simple canvas magnifying loupe that enlarged whatever raw pixels were under the cursor on the canvas.
* **What the Engineer Decided**:  
  The engineer audited the tool and instructed: *"Component (3× Loupe) make this feature more accurate if it is not much accurate then"*.
* **Why**:  
  Enlarging unaligned, raw pixel data is useless for defect verification on a board with slight skew or perspective shift. For an IPC-A-610 inspection microscope, the loupe needed to show the **server-aligned homography crop** of the component against the golden reference, compensate for local illumination differences, provide selectable multi-zoom (1×, 2×, 3×, 5×), overlay an engineering reticle (0.5 mm / 10 mil grid), and feature an alternating blink comparator (2.5 Hz).
* **Evidence**:  
  * Commit [`dc999a2`](https://github.com/Krutik50/pcb-missing-part-detector/commit/dc999a2): *"feat: enhance 3x digital optical loupe with server-aligned crops, reticle overlay, and multi-zoom"*.

---

### Decision 5: Removing Synthetic Demonstration Buttons in Favor of Real Inspection

* **What the AI Suggested**:  
  The AI retained a prominent "Run Physical Test Batch (500 Boards)" button in the inspection header so visitors could run synthetic benchmarks with a single click.
* **What the Engineer Decided**:  
  The engineer ordered the removal of this button and streamlined the inspection trigger to a single production action: inspecting real loaded boards or batches captured from the camera or test sets.
* **Why**:  
  Keeping simulation buttons in a live AOI station confused users between what was a live factory inspection and what was a synthetic benchmark demonstration. Benchmarking scripts belong in `scripts/` and `evaluate_multiboard.py`, not cluttering the operator's primary control station.
* **Evidence**:  
  * Commit [`ed6a48b`](https://github.com/Krutik50/pcb-missing-part-detector/commit/ed6a48b): Removed `btn-batch-physical` from `index.html` and `app.js`.

---

### Decision 6: Pruning Obsolete Diagnostic Dumps & Restoring Repository Hygiene

* **What the AI Suggested**:  
  Over multiple optimization runs, the AI accumulated 10 one-off `.txt` diagnostic dumps in `results/` (`jitter_confusion_matrix.txt`, `box_geometric_dissection.txt`, `cielab_color_difference_analysis.txt`, etc.) and orphaned scripts (`analyze_calibration.py`, `run_detailed_diagnostics.py`).
* **What the Engineer Decided**:  
  The engineer prompted: *"delete the files or folders which are not required our not being used it's just present but of no use that things delete it"*, followed by an audit of whether each file in `results/` and `sample_data/` was actively necessary.
* **Why**:  
  Leftover scratch files create confusion for downstream maintainers, obscure where actual benchmarks reside, and degrade project professionalism. The repository was trimmed so that only canonical benchmark summaries and golden sample images remain.
* **Evidence**:  
  * Commit [`4a12549`](https://github.com/Krutik50/pcb-missing-part-detector/commit/4a12549) and Commit [`45e6991`](https://github.com/Krutik50/pcb-missing-part-detector/commit/45e6991): Safely deleted 10 obsolete `.txt` files and legacy scripts while keeping all 38 automated test cases passing.

---

### Decision 7: Consolidating Role-Based Access Control (RBAC) to a Unified Operator

* **What the AI Suggested**:  
  The AI engineered a complex 3-tier RBAC system (Inspector vs. Quality Supervisor vs. Plant Administrator) requiring PINs, modal switches, and feature locks.
* **What the Engineer Decided**:  
  The engineer guided the AI to consolidate the interface into a single, unified, frictionless operator profile with full privileges.
* **Why**:  
  In dedicated SMT inspection stations connected to an overhead camera, having multi-tier lockout modals slows down the technician without providing real security benefits on an air-gapped machine. Usability on the shop floor demanded immediate access to all tools.
* **Evidence**:  
  * Commit [`2607180`](https://github.com/Krutik50/pcb-missing-part-detector/commit/2607180): *"refactor(rbac): consolidate to single unified operator role with full permissions"*.

---

### Decision 8: Modernization to Archify System Architecture Diagram

* **What the AI Suggested**:  
  The AI previously maintained an outdated, lower-resolution architecture diagram that omitted recent features like the Board & CAD Studio, the interstitial save pipeline, the 7-class defect classifier, and the multi-board dataset.
* **What the Engineer Decided**:  
  The engineer requested: *"upgrade this old architecture diagram"* and provided a screenshot of the legacy diagram, instructing the AI to generate a clean, modern Archify architecture diagram.
* **Why**:  
  As the system evolved from a single-reference toy script into an industrial AOI platform, the architectural documentation had to accurately communicate the data flow between the browser client, FastAPI backend, ECC aligner, ZNCC engine, and Deep SMT Verifier.
* **Evidence**:  
  * Commit [`1bb943c`](https://github.com/Krutik50/pcb-missing-part-detector/commit/1bb943c): Generated `docs/architecture.svg` and `docs/architecture.html` via Archify CLI with an updated high-resolution layout.

---

## 3. Pasted Chat Excerpts (Proof of Human Steering)

### Excerpt 1: Steering the Interstitial Board Saving Architecture
> **User**:  
> *"implement this after finishing component footprint before moving forward to the Batch Inspection in between the user should get an option if user wants to save currently loaded reference board with whatever anotated recipes yes or no if yes then it will be save in the board & CAD Studio so that if anyone wants to use the same board in future or later they can directly use it from the Stuido itself like the 5 boards with loaded recipes are currently present in the Board & cad studio make this end to end feature for my app"*
>
> **AI Reaction**:  
> Originally, custom boards were only kept in active session RAM. In response to the user's explicit UX specification, the AI created an interstitial modal between Step 2 and Step 3, implemented persistent disk storage in `data/recipes/`, created `POST /api/session/{session_id}/save_recipe`, and integrated custom user boards dynamically alongside the 5 hardware presets in the Board & CAD Studio.

---

### Excerpt 2: Challenging the YOLO Buzzword & Requiring True Metrics
> **User**:  
> *"are we really using yolo model ?? now tell me the accuracy , pricision,recall,etc of the model we are using and also tell which ml model we are using our model is trained on how much data tell me"*
>
> **AI Reaction**:  
> The AI acknowledged the reality: the live system is **not** using YOLO at runtime. The AI broke down the true pipeline:
> - **Alignment**: Global Euclidean Enhanced Correlation Coefficient (`cv2.findTransformECC`).
> - **Primary Detection**: Multi-channel Normalized Cross-Correlation (ZNCC) with spatial search ($\pm 4\text{px}$).
> - **Secondary Classification**: PyTorch Deep SMT Verifier (`dl_verifier.py`) trained on 500 physical crops.
> - **Metrics**: 97.1%–98.4% accuracy, 100% precision, 100% recall (zero escaped defects), with dead YOLO config files subsequently purged.

---

### Excerpt 3: Demanding Rigorous Loupe Accuracy and UI Decluttering
> **User**:  
> *"Component (3× Loupe) make this feature more accurate if it is not much accurate then... export recipes(json) button on the top right in Board & CAD Studio please remove it as it is of not needed and also tell me does this all files are being used or they are of no use it's just there tell me"*
>
> **AI Reaction**:  
> Rather than leaving a basic CSS zoom, the AI re-engineered the optical loupe to use server-aligned rectified crops with 1×/2×/3×/5× magnification, an engineering reticle overlay, and a blink comparator. Immediately following this, the AI removed the redundant export button from `index.html` and audited every file in `results/` and `sample_data/`, purging 10 dead exploratory `.txt` files.

---

## 4. Summary Table of Human Steering Outcomes

| Domain | AI Default / Initial Suggestion | Human Engineer Directive | Final Implementation |
| :--- | :--- | :--- | :--- |
| **Workflow** | Ephemeral session memory or manual JSON download | In-flow prompt between Step 2 and Step 3 | Interstitial modal + permanent `data/recipes/` preset card |
| **Studio UI** | Technical "Export Recipes (JSON)" button | Remove button; unnecessary clutter | Clean header displaying only preset cards and status |
| **Model Transparency** | Retained legacy YOLO configuration references | *"Are we really using YOLO?"* | Clarified real ECC + ZNCC + PyTorch ConvNet; purged dead configs |
| **Optical Loupe** | Basic canvas zoom of unaligned test image | *"Make this feature more accurate"* | Server-aligned homography crop + 5× zoom + Reticle + Blink |
| **Test Triggers** | Simulated "Run Physical Batch (500)" button | Strip simulation triggers from UI | Single production inspection button on real images |
| **Repo Hygiene** | Kept 10 exploratory diagnostic text files | *"Delete files that are of no use"* | Cleaned 10 `.txt` files; verified all 38 unit tests pass |
| **Access Control** | 3-tier Inspector/Supervisor/Admin lockout | Unified single-operator profile | Single technician role with instant access to all tools |
