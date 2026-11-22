# RESEARCH.md: Technical Investigation & Architecture Evaluation

This document details the prior research, public datasets, academic literature, and computer vision methodologies evaluated for Task B: Missing Component Detection on Assembled Circuit Boards (PCBA).

---

## 1. Verified Sources & Data Investigations

Every link below was directly opened, read, and evaluated against the specific operational constraints of this task: **a fixed camera setup with exactly one reference photo of an unseen board provided at runtime, followed by up to 3 test photos**.

### Public PCB Datasets

* **FICS-PCB: A Multi-Modal Image Dataset for Automated Printed Circuit Board Visual Inspection**
  * **Direct URL:** [https://eprint.iacr.org/2020/366](https://eprint.iacr.org/2020/366)
  * **What the paper/source documents:** A dataset of 31 PCB boards containing 77,347 annotated component instances (resistors, ICs, capacitors) captured across varied illumination angles, zoom scales, and sensor models by the Florida Institute for Cybersecurity (FICS) Research at the University of Florida.
  * **Utility Assessment:** *Partially usable for component crops.* It provides high-quality images of actual surface-mount components under lighting shifts. However, it does not provide paired "populated vs. unpopulated" photos of identical boards, so it cannot serve as a ground-truth benchmark for missing parts.

* **DeepPCB**
  * **Direct URL:** [https://github.com/tangsanli5201/DeepPCB](https://github.com/tangsanli5201/DeepPCB)
  * **What the page documents:** 1,500 image pairs (reference template vs. tested board) covering 6 bare-board fabrication flaws: open circuit, short circuit, mousebite, spur, pin-hole, and spurious copper.
  * **Utility Assessment:** *Rejected as non-applicable.* DeepPCB is strictly a **bare-board fabrication dataset** (bare copper traces on substrate). It contains zero electronic components and cannot be used for assembled PCBA component inspection.

* **PKU-Market-PCB (Peking University)**
  * **Direct URLs:** 
    * GitHub implementation: [https://github.com/Ixiaohuihuihui/Tiny-Defect-Detection-for-PCB](https://github.com/Ixiaohuihuihui/Tiny-Defect-Detection-for-PCB)
    * Kaggle benchmark mirror: [https://www.kaggle.com/datasets/akhatova/pcb-defects](https://www.kaggle.com/datasets/akhatova/pcb-defects)
  * **What the pages document:** 1,386 synthetic images containing 6 categories of manufacturing defects on bare boards (missing hole, mouse bite, open circuit, short, spur, spurious copper).
  * **Utility Assessment:** *Rejected as non-applicable.* Like DeepPCB, this benchmark evaluates bare printed circuit board etching and drilling flaws, not populated surface-mount devices (SMDs).

* **PCBA-Dataset (PCBA-DET)**
  * **Direct URL:** [https://github.com/ismh16/PCBA-Dataset](https://github.com/ismh16/PCBA-Dataset)
  * **What the page documents:** An object detection dataset created for the paper *"Defect detection of printed circuit board assembly based on YOLOv5"*, featuring images captured from three viewpoints (above, side, tilted) formatted for YOLO training.
  * **Utility Assessment:** *Partially usable for general visual inspection.* While it focuses on assembled boards (PCBA), the photos are taken from varying viewing angles rather than a fixed overhead jig.

---

### Academic Literature

* **PCB-MC: Missing Component Analysis in Printed Circuit Boards**
  * **Direct URL:** [https://arxiv.org/abs/2609.39427](https://arxiv.org/abs/2609.39427)
  * **Authors:** Betsy Villa Brochero, Ian Gibson, Estefania Talavera (Sep 2026).
  * **What the paper documents:** The paper formalizes the distinction between standard visual object detection (detecting what *is* present) and missing component analysis (detecting a *structural absence* based on empty footprints, exposed pads, and silkscreen traces). It benchmarks supervised detectors and unsupervised anomaly detection methods across 197 distinct board layouts using board-type-aware cross-validation splits.
  * **Key Benchmark Findings Cited:**
    * When tested on unseen board layouts without a board-specific reference, supervised single-stage detectors suffered high False Negative Rates on missing components: **YOLOv8 and YOLOv11 yielded FNR $\ge 0.87$ on Task M (missing components)**, with YOLOv11 achieving an mAP of only ~0.09.
    * Unsupervised anomaly detection methods (such as DRAEM and Reverse Distillation) failed completely on missing component detection (**mAP of 0.00, FNR of 1.00**) because they lacked exact spatial alignment with a board-specific reference image.
  * **Role in this Project:** Used strictly as an academic baseline. The authors state that the underlying dataset is only available upon paper acceptance, so it cannot be downloaded for local practice data. However, its empirical findings confirm that general object detectors struggle with missing components on unseen boards without a board-specific reference template.

---

### Core Computer Vision & Alignment References

* **OpenCV `matchTemplate` Documentation**
  * **Direct URL:** [https://docs.opencv.org/4.x/df/dfb/group__imgproc__object.html#ga586ebfb0a7fb604b35a23d85391329be](https://docs.opencv.org/4.x/df/dfb/group__imgproc__object.html#ga586ebfb0a7fb604b35a23d85391329be)
  * **Technical Details:** Evaluates sliding-window similarity across an image. The `TM_CCOEFF_NORMED` method mean-centers the template and patch and normalizes by their standard deviations, mapping scores to $[-1.0, 1.0]$. This normalization cancels linear brightness shifts ($I' = \alpha I + \beta$).

* **OpenCV `findTransformECC` Documentation**
  * **Direct URL:** [https://docs.opencv.org/4.x/dc/d6b/group__video__track.html#ga1aa3570077768773b9b3399923209f3c](https://docs.opencv.org/4.x/dc/d6b/group__video__track.html#ga1aa3570077768773b9b3399923209f3c)
  * **Technical Details:** Computes the optimal geometric warp matrix by maximizing the Enhanced Correlation Coefficient (ECC) between reference and test grayscale images. It supports an `inputMask` parameter, which allows padded borders (from isotropic letterboxing) to be masked out so they do not distort alignment calculations.

* **Structural Similarity Index (SSIM)**
  * **Direct URL / DOI:** [https://doi.org/10.1109/TIP.2003.819861](https://doi.org/10.1109/TIP.2003.819861) | [Open Access PDF (NYU)](https://www.cns.nyu.edu/pub/eero/wang03b.pdf)
  * **Citation:** Zhou Wang, Alan C. Bovik, Hamid R. Sheikh, and Eero P. Simoncelli, *"Image Quality Assessment: From Error Visibility to Structural Similarity"*, IEEE Transactions on Image Processing, Vol. 13, No. 4, pp. 600–612, 2004.
  * **Technical Details:** Proposes an image quality metric evaluating structural correlation, luminance, and contrast rather than raw pixel differences (MSE).

---

## 2. Options Compared

| Methodology | Data Requirements | Offline Feasibility | Handling of Unseen Board at Demo | Failure Mode Under Inspection |
| :--- | :--- | :--- | :--- | :--- |
| **Option A: Aligned Multi-Cue Matching (Selected)** | Exactly 1 reference image | High (Pure OpenCV/NumPy) | Native (operates directly on runtime reference) | Highly explainable (ZNCC score + patch residual) |
| **Option B: Supervised Object Detection (YOLOv8/11)** | Thousands of labeled images | Moderate (Torch / ONNX) | Poor (fails on unseen components without retraining) | Black-box false negatives on empty footprints |
| **Option C: Deep Anomaly Detection (PatchCore/PaDiM)** | Hundreds of defect-free images | Low (Heavy memory/compute) | Poor (collapses with $N=1$ reference sample) | Sensitive to global sensor noise without spatial alignment |
| **Option D: Pre-trained Embeddings (DINOv2/CLIP)** | Zero-shot feature extraction | Moderate (ONNX / Torch) | Fair (cosine similarity on crops) | Low spatial resolution on tiny surface-mount parts |

---

## 3. What I Picked and Why

### Selected Architecture: Aligned ECC + Local ZNCC + Normalized Patch Difference

1. **Global Rigid Registration with Border Masking (`findTransformECC`):**
   * Uses an Affine/Euclidean motion model (translation + small rotation) to correct for minor camera/jig displacement.
   * Leverages `inputMask` to completely exclude letterboxed/padded margins from the alignment gradient.
   * Includes a strict safety fallback: if ECC optimization does not converge or exceeds plausible physical limits ($|\theta| > 5^\circ$), the transform falls back to Identity, avoiding severe distortion.

2. **Local Bounded Search via ZNCC (`matchTemplate`):**
   * Around each user-defined ROI, searches a local neighborhood ($\pm 15$ pixels) using `TM_CCOEFF_NORMED`.
   * Compensates for any residual localized mechanical jitter while maintaining invariance to linear lighting shifts.

3. **Dual Verification via Normalized Patch Difference ($\Delta_{patch}$):**
   * To prevent false positives where exposed solder pads or silkscreen traces correlate with component pins, the best-matched patch is locally normalized and subtracted from the reference template (Mean Absolute Error).
   * A populated component produces low residual difference, whereas an empty site exposing bare copper/tin pads produces a distinct pixel residual.

4. **Three-State Verdict with Dynamic UI Sensitivity:**
   * Parts are classified into **Present**, **Missing**, or **Uncertain** (borderline match requiring human verification).
   * An interactive sensitivity slider in the UI dynamically shifts decision thresholds without requiring code modifications or restarts.

---

## 4. What I Rejected and Why

### 1. Rejected: Supervised Object Detection (YOLOv8, YOLOv11, Faster R-CNN)
* **Reasoning:** In the live demo, the evaluator presents a single reference photo of an unseen board and annotates custom components. Supervised object detectors require training on thousands of examples of specific component classes. A generic model has no prior training on the user's specific board layout or part numbering.
* Furthermore, empirical benchmarks from the PCB-MC paper (`arXiv:2609.39427`) show that even when trained on diverse boards, modern YOLO detectors yield high False Negative Rates ($\ge 0.87$) when tasked with identifying missing components on unfamiliar board architectures.

### 2. Rejected: Deep Visual Anomaly Detection (PatchCore, PaDiM, DRAEM)
* **Reasoning:** Frameworks like PatchCore build memory banks of neighborhood feature distributions from large sets of defect-free reference images. In this challenge, the system is given exactly **one** reference photo ($N=1$). With a single image, distribution modeling collapses into nearest-neighbor retrieval.
* As demonstrated in the PCB-MC study, unsupervised anomaly detectors without rigid, board-specific spatial registration fail completely (reporting mAP scores of 0.00 and FNR of 1.00) because normal board-to-board variations are indistinguishable from true defects.

### 3. Rejected: Pre-trained Vision Foundation Embeddings (DINOv2, CLIP)
* **Reasoning:** Vision Foundation models are optimized for semantic invariance (identifying high-level object concepts across different backgrounds and orientations). Industrial PCBA inspection requires the inverse: extreme sensitivity to high-frequency spatial details (e.g., verifying whether a tiny 0402 capacitor is soldered across its pads or absent).
* In our evaluation, passing small crops through a Vision Transformer (ViT) patch tokenization ($14 \times 14$ pixel patches) risks smoothing over crucial lead-frame and solder-pad details, while introducing heavy runtime dependencies (Torch/ONNX) without solving local misalignment.

---

## 5. Limitations & What Was Not Verified

To maintain strict technical transparency, the following aspects were not verified or could not be confirmed:

1. **PCBA-Dataset Annotations:** The repository structure of `ismh16/PCBA-Dataset` was confirmed, but the full multi-gigabyte dataset archive was not downloaded to manually verify whether "missing components" is an explicitly separated class or grouped into general assembly defects.
2. **PCB-MC Practice Data Access:** Because the PCB-MC dataset is restricted ("available upon acceptance"), its images could not be downloaded to serve as a local training or calibration set; it was used solely as a published benchmark reference.
3. **FICS-PCB Paired Testing:** FICS-PCB contains real component instances under varied lighting, but lacks paired before-and-after (populated vs. missing) captures of the exact same board.
4. **Empirical Latency & Threshold Boundaries:** Runtimes, memory usage, and numerical threshold boundaries are unmeasured hypotheses until formal benchmarking is executed on actual test images during system implementation.
