// 100% Offline PCB Missing Component Detector Client Logic
// Pure Vanilla JavaScript, zero external libraries

document.addEventListener('DOMContentLoaded', () => {
    // --- Application State ---
    const state = {
        sessionId: null,
        referenceFile: null,
        referenceImg: null,
        workingDim: { width: 1920, height: 1080 },
        scaleFactor: 1.0,
        components: [], // [{ id, name, bbox: [x, y, w, h], normalized: [...] }]
        testFiles: [],  // File objects
        currentStep: 1,
        activeSensitivity: 'balanced',
        referenceFingerprint: null,
        lastInspectionData: null,
        signoffs: {}, // filename -> { compName: { final_status, operator_id, note, timestamp } }
        currentUser: {
            operator_id: 'OP-8402',
            name: 'Sarah Jenkins',
            role: 'INSPECTOR',
            role_label: 'Senior AOI Inspector',
            badge: 'OP-8402',
        },
        presets: [],
        activePreset: null,
        activeTolerances: {
            max_tilt_deg: 3.5,
            max_shift_px: 5.0,
        },
        activeTool: 'rectangle', // 'rectangle', 'pencil', 'polygon'
        carouselIndex: 0,
        resultsViewMode: 'carousel', // 'carousel' or 'stacked'
    };

    // --- DOM Elements ---
    const el = {
        statusDot: document.getElementById('status-dot'),
        btnReset: document.getElementById('btn-reset'),
        globalAlert: document.getElementById('global-alert'),

        // Operator Profile & Authentication
        operatorProfilePill: document.getElementById('operator-profile-pill'),
        headerOperatorName: document.getElementById('header-operator-name'),
        headerOperatorBadge: document.getElementById('header-operator-badge'),
        btnOpenAuthModal: document.getElementById('btn-open-auth-modal'),
        authModal: document.getElementById('auth-modal'),
        btnCloseAuth: document.getElementById('btn-close-auth'),
        btnCancelAuth: document.getElementById('btn-cancel-auth'),
        authProfilesList: document.getElementById('auth-profiles-list'),
        customAuthForm: document.getElementById('custom-auth-form'),
        inputOpBadge: document.getElementById('input-op-badge'),
        inputOpName: document.getElementById('input-op-name'),
        selectOpRole: document.getElementById('select-op-role'),

        // Presets
        presetsContainer: document.getElementById('presets-container'),
        btnLoadPresetBatch: document.getElementById('btn-load-preset-batch'),

        // Step Navigation
        stepNav1: document.getElementById('step-nav-1'),
        stepNav2: document.getElementById('step-nav-2'),
        stepNav3: document.getElementById('step-nav-3'),
        panelStep1: document.getElementById('panel-step-1'),
        panelStep2: document.getElementById('panel-step-2'),
        panelStep3: document.getElementById('panel-step-3'),

        // Step 1
        refDropzone: document.getElementById('ref-dropzone'),
        refFileInput: document.getElementById('ref-file-input'),
        btnBrowseRef: document.getElementById('btn-browse-ref'),
        btnLoadSampleRef: document.getElementById('btn-load-sample-ref'),
        btnCameraRef: document.getElementById('btn-camera-ref'),
        btnOpenCamera: document.getElementById('btn-open-camera'),

        // Step 2
        annotationCanvas: document.getElementById('annotation-canvas'),
        canvasContainer: document.getElementById('canvas-container'),
        canvasDimInfo: document.getElementById('canvas-dim-info'),
        canvasToolHint: document.getElementById('canvas-tool-hint'),
        btnToolRect: document.getElementById('tool-rect'),
        btnToolPencil: document.getElementById('tool-pencil'),
        btnToolPoly: document.getElementById('tool-poly'),
        componentListContainer: document.getElementById('component-list-container'),
        emptyCompsMsg: document.getElementById('empty-comps-msg'),
        compCount: document.getElementById('comp-count'),
        btnLoadSampleComps: document.getElementById('btn-load-sample-comps'),
        btnClearComps: document.getElementById('btn-clear-comps'),
        btnExportRecipe: document.getElementById('btn-export-recipe'),
        btnImportRecipe: document.getElementById('btn-import-recipe'),
        recipeFileInput: document.getElementById('recipe-file-input'),
        btnProceedToStep3: document.getElementById('btn-proceed-to-step3'),

        // Step 3
        testDropzone: document.getElementById('test-dropzone'),
        testFileInput: document.getElementById('test-file-input'),
        btnBrowseTest: document.getElementById('btn-browse-test'),
        testFileList: document.getElementById('test-file-list'),
        btnLoadSampleBatch: document.getElementById('btn-load-sample-batch'),
        btnCameraTest: document.getElementById('btn-camera-test'),
        btnRunInspect: document.getElementById('btn-run-inspect'),
        inspectionSpinner: document.getElementById('inspection-spinner'),
        inspectionResultsArea: document.getElementById('inspection-results-area'),
        resultsSummaryBadge: document.getElementById('results-summary-badge'),
        resultsCardsContainer: document.getElementById('results-cards-container'),
        toggleViewCarousel: document.getElementById('toggle-view-carousel'),
        toggleViewStacked: document.getElementById('toggle-view-stacked'),
        activeSessionBadge: document.getElementById('active-session-badge'),

        // Batch Summary & KPIs
        batchSummaryPanel: document.getElementById('batch-summary-panel'),
        kpiTotal: document.getElementById('kpi-total'),
        kpiOk: document.getElementById('kpi-ok'),
        kpiDefect: document.getElementById('kpi-defect'),
        kpiReview: document.getElementById('kpi-review'),
        kpiFpy: document.getElementById('kpi-fpy'),
        kpiFinalYield: document.getElementById('kpi-final-yield'),
        defectTallyList: document.getElementById('defect-tally-list'),
        btnDownloadCsv: document.getElementById('btn-download-csv'),
        btnPrintReport: document.getElementById('btn-print-report'),

        // Printable Modal
        printModal: document.getElementById('print-modal'),
        printableReportContent: document.getElementById('printable-report-content'),
        btnTriggerPrint: document.getElementById('btn-trigger-print'),
        btnClosePrint: document.getElementById('btn-close-print'),

        // Live Camera Modal Elements
        cameraModal: document.getElementById('camera-modal'),
        btnCloseCamera: document.getElementById('btn-close-camera'),
        cameraLiveDot: document.getElementById('camera-live-dot'),
        cameraVideoPreview: document.getElementById('camera-video-preview'),
        cameraCaptureCanvas: document.getElementById('camera-capture-canvas'),
        cameraPlaceholder: document.getElementById('camera-placeholder'),
        cameraDeviceSelect: document.getElementById('camera-device-select'),
        cameraErrorBanner: document.getElementById('camera-error-banner'),
        btnStartCamera: document.getElementById('btn-start-camera'),
        btnStopCamera: document.getElementById('btn-stop-camera'),
        btnCaptureAsRef: document.getElementById('btn-capture-as-ref'),
        btnCaptureAsTest: document.getElementById('btn-capture-as-test'),

        // Modal
        nameModal: document.getElementById('name-modal'),
        compNameInput: document.getElementById('comp-name-input'),
        btnCancelName: document.getElementById('btn-cancel-name'),
        btnSaveName: document.getElementById('btn-save-name'),
        quickTagsContainer: document.getElementById('quick-tags-container'),
    };

    // Canvas drawing state
    let isDrawing = false;
    let startX = 0, startY = 0;
    let currentX = 0, currentY = 0;
    let pendingBox = null;
    let pendingShapeType = 'rectangle'; // 'rectangle', 'pencil', 'polygon'
    let pendingPolygon = null; // [[x, y], ...]
    let freehandStroke = []; // [[x, y], ...]
    let polygonPoints = []; // [[x, y], ...]

    function setActiveTool(tool) {
        state.activeTool = tool;
        if (el.btnToolRect) el.btnToolRect.classList.toggle('active', tool === 'rectangle');
        if (el.btnToolPencil) el.btnToolPencil.classList.toggle('active', tool === 'pencil');
        if (el.btnToolPoly) el.btnToolPoly.classList.toggle('active', tool === 'polygon');

        if (el.canvasToolHint) {
            if (tool === 'rectangle') el.canvasToolHint.textContent = 'Click and drag to draw rectangular bounding box';
            else if (tool === 'pencil') el.canvasToolHint.textContent = 'Click and drag freehand to trace non-linear component contour';
            else if (tool === 'polygon') el.canvasToolHint.textContent = 'Click points around component, double-click or click start point to close';
        }
        polygonPoints = [];
        freehandStroke = [];
        renderAnnotationCanvas();
    }

    if (el.btnToolRect) el.btnToolRect.addEventListener('click', () => setActiveTool('rectangle'));
    if (el.btnToolPencil) el.btnToolPencil.addEventListener('click', () => setActiveTool('pencil'));
    if (el.btnToolPoly) el.btnToolPoly.addEventListener('click', () => setActiveTool('polygon'));

    // --- Health Check ---
    async function checkHealth() {
        try {
            const res = await fetch('/api/health');
            if (res.ok) {
                el.statusDot.className = 'status-indicator online';
                el.statusDot.title = 'Offline Backend Ready';
            } else {
                throw new Error();
            }
        } catch {
            el.statusDot.className = 'status-indicator offline';
            el.statusDot.title = 'Backend Disconnected';
            showAlert('Backend server is currently offline or unreachable.', 'danger');
        }
    }
    checkHealth();

    // --- OPERATOR AUTHENTICATION & RBAC ---
    function getUserRole() {
        return (state.currentUser && state.currentUser.role) ? state.currentUser.role.toUpperCase() : 'INSPECTOR';
    }

    function isInspector() {
        return getUserRole() === 'INSPECTOR';
    }

    function isSupervisor() {
        return getUserRole() === 'SUPERVISOR';
    }

    function isAdmin() {
        return getUserRole() === 'ADMIN';
    }

    function canAuthorFootprints() {
        return !isInspector();
    }

    function canOverrideDefects() {
        return !isInspector();
    }

    function canTuneTolerances() {
        return isAdmin();
    }

    function applyRBACPermissions() {
        const role = getUserRole();
        const roleLabel = state.currentUser ? (state.currentUser.role_label || role) : role;

        // Step 2 Footprint Authoring Controls & Banner
        const step2Banner = document.getElementById('step2-rbac-banner');
        const canvasContainer = el.canvasContainer || document.getElementById('canvas-container');

        if (canAuthorFootprints()) {
            if (step2Banner) {
                step2Banner.className = 'rbac-notice-banner rbac-authorized';
                step2Banner.innerHTML = `
                    <svg class="ui-icon"><use href="#icon-check"></use></svg>
                    <span id="step2-rbac-text"><strong>Layout Modification Authorized:</strong> Footprint authoring and component geometry editing unlocked for ${roleLabel}.</span>
                `;
            }
            if (canvasContainer) canvasContainer.classList.remove('canvas-locked');
            if (el.btnClearComps) el.btnClearComps.disabled = false;
            if (el.btnLoadSampleComps) el.btnLoadSampleComps.disabled = false;
            if (el.btnImportRecipe) el.btnImportRecipe.disabled = false;
        } else {
            if (step2Banner) {
                step2Banner.className = 'rbac-notice-banner rbac-locked';
                step2Banner.innerHTML = `
                    <svg class="ui-icon"><use href="#icon-alert"></use></svg>
                    <span id="step2-rbac-text"><strong>Read-Only Layout Mode:</strong> Component footprint authoring is restricted to SMT Supervisors and QA Admins. Line Inspectors have view-only access.</span>
                `;
            }
            if (canvasContainer) canvasContainer.classList.add('canvas-locked');
            if (el.btnClearComps) el.btnClearComps.disabled = true;
            if (el.btnLoadSampleComps) el.btnLoadSampleComps.disabled = true;
            if (el.btnImportRecipe) el.btnImportRecipe.disabled = true;
        }

        // Update Component List UI if present
        if (state.components && state.components.length > 0) {
            renderComponentsList();
        }

        // Update Result Cards if present
        if (state.lastInspectionData && state.lastInspectionData.results) {
            renderResultCards();
        }
    }

    function updateOperatorHeader(user) {
        if (!user) return;
        state.currentUser = user;
        if (el.headerOperatorName) el.headerOperatorName.textContent = user.name;
        if (el.headerOperatorBadge) {
            el.headerOperatorBadge.textContent = `${user.badge} (${user.role})`;
            const roleClass = user.role === 'ADMIN' ? 'role-admin' : (user.role === 'SUPERVISOR' ? 'role-supervisor' : 'role-inspector');
            el.headerOperatorBadge.className = `header-operator-badge role-badge ${roleClass}`;
        }
        applyRBACPermissions();
    }

    async function loadAuthProfiles() {
        try {
            const res = await fetch('/api/auth/profiles');
            if (!res.ok) return;
            const data = await res.json();
            renderAuthProfiles(data.profiles || []);
        } catch (e) {
            console.warn('Failed to load operator profiles:', e);
        }
    }

    function renderAuthProfiles(profiles) {
        if (!el.authProfilesList) return;
        el.authProfilesList.innerHTML = '';
        profiles.forEach(p => {
            const item = document.createElement('div');
            item.className = 'auth-profile-card';
            const roleColor = p.role === 'ADMIN' ? 'preset-badge-amber' : (p.role === 'SUPERVISOR' ? 'preset-badge-blue' : 'preset-badge-green');
            item.innerHTML = `
                <div class="auth-profile-left">
                    <svg class="ui-icon" style="width:18px;height:18px;color:var(--color-blue);"><use href="#icon-user"></use></svg>
                    <div>
                        <div class="auth-profile-name">${p.name}</div>
                        <div class="auth-profile-role">${p.role_label || p.role}</div>
                    </div>
                </div>
                <div style="display:flex; align-items:center; gap:0.5rem;">
                    <span class="preset-badge ${roleColor}">${p.badge}</span>
                    <span style="font-size:0.8rem; color:var(--color-blue); font-weight:600;">Select &rarr;</span>
                </div>
            `;
            item.addEventListener('click', () => {
                handleLogin({ operator_id: p.operator_id, name: p.name, role: p.role });
            });
            el.authProfilesList.appendChild(item);
        });
    }

    async function handleLogin(credentials) {
        try {
            const res = await fetch('/api/auth/login', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(credentials)
            });
            if (!res.ok) throw new Error('Authentication failed');
            const data = await res.json();
            if (data.success && data.user) {
                updateOperatorHeader(data.user);
                if (el.authModal) el.authModal.classList.add('d-none');
                showAlert(`Operator verified: ${data.user.name} (${data.user.role_label || data.user.role}) [${data.user.badge}]`, 'success');
            }
        } catch (err) {
            showAlert(`Login error: ${err.message}`, 'danger');
        }
    }

    if (el.btnOpenAuthModal) {
        el.btnOpenAuthModal.addEventListener('click', (e) => {
            e.stopPropagation();
            if (el.authModal) el.authModal.classList.remove('d-none');
        });
    }
    if (el.operatorProfilePill) {
        el.operatorProfilePill.addEventListener('click', (e) => {
            if (e.target.tagName !== 'BUTTON' && el.authModal) {
                el.authModal.classList.remove('d-none');
            }
        });
    }
    if (el.btnCloseAuth) {
        el.btnCloseAuth.addEventListener('click', () => {
            if (el.authModal) el.authModal.classList.add('d-none');
        });
    }
    if (el.btnCancelAuth) {
        el.btnCancelAuth.addEventListener('click', () => {
            if (el.authModal) el.authModal.classList.add('d-none');
        });
    }
    if (el.customAuthForm) {
        el.customAuthForm.addEventListener('submit', (e) => {
            e.preventDefault();
            const badge = el.inputOpBadge.value.trim();
            const name = el.inputOpName.value.trim();
            const role = el.selectOpRole.value;
            if (!badge || !name) return;
            handleLogin({ operator_id: badge, name: name, role: role });
        });
    }

    loadAuthProfiles();

    // --- PHYSICAL BOARD PRESETS ---
    async function loadPhysicalPresets() {
        try {
            const res = await fetch('/api/presets');
            if (!res.ok) return;
            const data = await res.json();
            state.presets = data.presets || [];
            renderPresets(state.presets);
        } catch (e) {
            console.warn('Failed to load physical presets:', e);
        }
    }

    function renderPresets(presets) {
        if (!el.presetsContainer) return;
        el.presetsContainer.innerHTML = '';
        if (!presets || presets.length === 0) {
            el.presetsContainer.innerHTML = '<div style="color:var(--text-muted); font-size:0.85rem;">No physical board presets found on server.</div>';
            return;
        }

        presets.forEach(preset => {
            const card = document.createElement('div');
            card.className = 'preset-card';
            if (state.activePreset && state.activePreset.id === preset.id) {
                card.classList.add('active');
            }

            const compCount = preset.components ? preset.components.length : 0;
            const tierBadgeClass = preset.tier === 'High Density' ? 'preset-badge-amber' : (preset.tier === 'Industrial' ? 'preset-badge-blue' : 'preset-badge-green');

            card.innerHTML = `
                <div>
                    <div class="preset-thumb-wrapper">
                        <img src="${preset.reference_url}" class="preset-thumb" alt="${preset.name}" loading="lazy">
                    </div>
                    <span class="preset-badge ${tierBadgeClass}">${preset.tier}</span>
                    <div class="preset-title">${preset.name}</div>
                    <div class="preset-meta">${compCount} Pre-Calibrated Parts &bull; ${preset.resolution[0]}×${preset.resolution[1]} px</div>
                </div>
                <button type="button" class="btn btn-sm btn-outline preset-btn-load" data-preset-id="${preset.id}">
                    Load Golden Preset →
                </button>
            `;

            card.addEventListener('click', () => {
                applyPreset(preset);
            });

            el.presetsContainer.appendChild(card);
        });
    }

    async function applyPreset(preset) {
        try {
            showAlert(`Loading golden physical preset "${preset.name}"...`, 'info');
            const refRes = await fetch(preset.reference_url);
            if (!refRes.ok) throw new Error(`Failed to load preset reference image (${refRes.statusText})`);
            const blob = await refRes.blob();
            const fname = `${preset.id}_reference.png`;
            const file = new File([blob], fname, { type: 'image/png' });

            await handleReferenceFile(file);

            state.components = preset.components.map((c, i) => {
                const [x, y, w, h] = c.bbox;
                return {
                    id: 'preset_comp_' + i,
                    name: c.name,
                    bbox: [x, y, w, h],
                    shape_type: c.shape_type || 'rectangle',
                    polygon: c.polygon || null,
                    warning: getBoxWarning(w, h, state.workingDim.width, state.workingDim.height),
                    normalized: c.normalized_bbox || [
                        Number((x / state.workingDim.width).toFixed(4)),
                        Number((y / state.workingDim.height).toFixed(4)),
                        Number((w / state.workingDim.width).toFixed(4)),
                        Number((h / state.workingDim.height).toFixed(4)),
                    ]
                };
            });

            state.activePreset = preset;

            if (state.sessionId && state.components.length > 0) {
                await fetch(`/api/sessions/${state.sessionId}/components`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        components: state.components.map(c => ({
                            name: c.name,
                            bbox: c.bbox,
                            shape_type: c.shape_type || 'rectangle',
                            polygon: c.polygon || null,
                            is_normalized: false,
                        })),
                    }),
                });
            }

            renderAnnotationCanvas();
            renderComponentsList();
            renderPresets(state.presets);

            showAlert(`Golden Preset "${preset.name}" loaded with ${state.components.length} pre-calibrated SMT components! Ready to inspect.`, 'success');
        } catch (err) {
            showAlert(`Failed to load preset "${preset.name}": ${err.message}`, 'danger');
        }
    }

    loadPhysicalPresets();

    // --- Helper Utilities ---
    function showAlert(msg, type = 'danger') {
        el.globalAlert.textContent = msg;
        el.globalAlert.className = `alert alert-${type}`;
        el.globalAlert.classList.remove('d-none');
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function hideAlert() {
        el.globalAlert.classList.add('d-none');
    }

    function setStep(step) {
        state.currentStep = step;
        hideAlert();

        // Update nav circles
        [el.stepNav1, el.stepNav2, el.stepNav3].forEach((nav, idx) => {
            const stepNum = idx + 1;
            nav.classList.remove('active', 'complete');
            if (stepNum === step) {
                nav.classList.add('active');
            } else if (stepNum < step) {
                nav.classList.add('complete');
            }
        });

        // Toggle panel displays
        el.panelStep1.classList.toggle('d-none', step !== 1);
        el.panelStep2.classList.toggle('d-none', step !== 2);
        el.panelStep3.classList.toggle('d-none', step !== 3);

        if (step === 2 && state.referenceImg) {
            renderAnnotationCanvas();
            renderComponentsList();
        }
    }

    // --- STEP 1: REFERENCE UPLOAD ---
    el.btnBrowseRef.addEventListener('click', () => el.refFileInput.click());

    el.refFileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files[0]) {
            handleReferenceFile(e.target.files[0]);
        }
    });

    el.refDropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        el.refDropzone.classList.add('dragover');
    });

    el.refDropzone.addEventListener('dragleave', () => {
        el.refDropzone.classList.remove('dragover');
    });

    el.refDropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        el.refDropzone.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files[0]) {
            handleReferenceFile(e.dataTransfer.files[0]);
        }
    });

    function computeImageFingerprint(img) {
        try {
            const c = document.createElement('canvas');
            c.width = 16;
            c.height = 16;
            const ctx = c.getContext('2d');
            ctx.drawImage(img, 0, 0, 16, 16);
            const p = ctx.getImageData(0, 0, 16, 16).data;
            let sum = 0;
            const grays = new Float32Array(256);
            for (let i = 0, j = 0; i < p.length; i += 4, j++) {
                const g = 0.299 * p[i] + 0.587 * p[i+1] + 0.114 * p[i+2];
                grays[j] = g;
                sum += g;
            }
            const avg = sum / 256;
            let hash = '';
            for (let i = 0; i < 256; i += 4) {
                let nibble = 0;
                for (let b = 0; b < 4; b++) {
                    if (grays[i + b] >= avg) nibble |= (1 << (3 - b));
                }
                hash += nibble.toString(16);
            }
            return hash;
        } catch {
            return 'ref_hash_fallback';
        }
    }

    async function handleReferenceFile(file) {
        hideAlert();
        if (!file.type.startsWith('image/')) {
            showAlert(`File "${file.name}" is not a valid image format. Please select a PNG or JPEG file.`, 'danger');
            return;
        }

        const formData = new FormData();
        formData.append('file', file);

        try {
            el.btnBrowseRef.disabled = true;
            el.btnBrowseRef.textContent = 'Processing & Normalizing...';

            const resp = await fetch('/api/reference', {
                method: 'POST',
                body: formData,
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Upload failed');
            }

            const data = await resp.json();
            state.sessionId = data.session_id;
            state.workingDim = { width: data.working_width, height: data.working_height };
            state.scaleFactor = data.scale_factor;
            state.referenceFile = file;

            // Load into HTMLImageElement
            const img = new Image();
            img.onload = () => {
                state.referenceImg = img;
                state.referenceFingerprint = computeImageFingerprint(img);
                el.canvasDimInfo.textContent = `Working Canvas: ${data.working_width} × ${data.working_height} px (Scale: ${data.scale_factor.toFixed(3)})`;
                el.activeSessionBadge.textContent = `Session: ${data.session_id.substring(0, 8)}...`;
                setStep(2);
            };
            img.src = URL.createObjectURL(file);

        } catch (err) {
            showAlert(`Error uploading reference: ${err.message}`, 'danger');
        } finally {
            el.btnBrowseRef.disabled = false;
            el.btnBrowseRef.textContent = 'Select Reference Image';
        }
    }

    // Quick sample reference loader (optional fallback)
    if (el.btnLoadSampleRef) {
        el.btnLoadSampleRef.addEventListener('click', async () => {
            try {
                el.btnLoadSampleRef.disabled = true;
                el.btnLoadSampleRef.textContent = 'Loading sample...';
                const res = await fetch('/sample_data/reference.png');
                if (!res.ok) throw new Error('Sample reference not found on server');
                const blob = await res.blob();
                const file = new File([blob], 'reference.png', { type: 'image/png' });
                await handleReferenceFile(file);
            } catch (err) {
                showAlert(`Could not load sample reference: ${err.message}`, 'danger');
            } finally {
                el.btnLoadSampleRef.disabled = false;
                el.btnLoadSampleRef.textContent = 'Load Sample Reference (sample_data/reference.png)';
            }
        });
    }

    // --- STEP 2: CANVAS ANNOTATION ---
    function renderAnnotationCanvas() {
        const canvas = el.annotationCanvas;
        const img = state.referenceImg;
        if (!img) return;

        // Set native canvas dimensions to working canvas resolution
        canvas.width = state.workingDim.width;
        canvas.height = state.workingDim.height;

        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);

        // Draw golden reference image
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

        // Draw existing components
        state.components.forEach((comp) => {
            const [x, y, w, h] = comp.bbox;

            if (comp.polygon && comp.polygon.length >= 3) {
                // Non-linear Polygon / Pencil Contour
                ctx.save();
                ctx.beginPath();
                ctx.moveTo(comp.polygon[0][0], comp.polygon[0][1]);
                for (let i = 1; i < comp.polygon.length; i++) {
                    ctx.lineTo(comp.polygon[i][0], comp.polygon[i][1]);
                }
                ctx.closePath();
                ctx.fillStyle = 'rgba(56, 189, 248, 0.22)';
                ctx.fill();
                ctx.strokeStyle = '#38bdf8';
                ctx.lineWidth = 2.5;
                ctx.stroke();

                // Bounding envelope dashed
                ctx.setLineDash([4, 4]);
                ctx.strokeStyle = 'rgba(56, 189, 248, 0.4)';
                ctx.lineWidth = 1;
                ctx.strokeRect(x, y, w, h);
                ctx.restore();

                // Label banner
                ctx.fillStyle = '#0284c7';
                const label = `${comp.name} (${comp.shape_type === 'pencil' ? '✎' : '⬡'})`;
                ctx.font = 'bold 15px -apple-system, sans-serif';
                const textWidth = ctx.measureText(label).width;
                ctx.fillRect(x, Math.max(0, y - 22), textWidth + 10, 22);
                ctx.fillStyle = '#ffffff';
                ctx.fillText(label, x + 5, Math.max(15, y - 6));
            } else {
                // Standard Rectangle
                ctx.strokeStyle = '#388bfd';
                ctx.lineWidth = 3;
                ctx.strokeRect(x, y, w, h);
                ctx.fillStyle = 'rgba(56, 139, 253, 0.2)';
                ctx.fillRect(x, y, w, h);

                // Label banner
                ctx.fillStyle = '#388bfd';
                const label = comp.name;
                ctx.font = 'bold 16px -apple-system, sans-serif';
                const textWidth = ctx.measureText(label).width;
                ctx.fillRect(x, Math.max(0, y - 24), textWidth + 12, 24);
                ctx.fillStyle = '#ffffff';
                ctx.fillText(label, x + 6, Math.max(16, y - 6));
            }
        });

        // Draw active drawing feedback based on tool
        if (state.activeTool === 'rectangle' && isDrawing && pendingBox) {
            const [x, y, w, h] = pendingBox;
            ctx.save();
            ctx.setLineDash([6, 6]);
            ctx.strokeStyle = '#22c55e';
            ctx.lineWidth = 2.5;
            ctx.strokeRect(x, y, w, h);
            ctx.fillStyle = 'rgba(34, 197, 94, 0.2)';
            ctx.fillRect(x, y, w, h);
            ctx.restore();
        } else if (state.activeTool === 'pencil' && isDrawing && freehandStroke.length > 1) {
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(freehandStroke[0][0], freehandStroke[0][1]);
            for (let i = 1; i < freehandStroke.length; i++) {
                ctx.lineTo(freehandStroke[i][0], freehandStroke[i][1]);
            }
            ctx.strokeStyle = '#22c55e';
            ctx.lineWidth = 3;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            ctx.stroke();
            ctx.fillStyle = 'rgba(34, 197, 94, 0.15)';
            ctx.fill();
            ctx.restore();
        } else if (state.activeTool === 'polygon' && polygonPoints.length > 0) {
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(polygonPoints[0][0], polygonPoints[0][1]);
            for (let i = 1; i < polygonPoints.length; i++) {
                ctx.lineTo(polygonPoints[i][0], polygonPoints[i][1]);
            }
            ctx.lineTo(currentX, currentY);
            ctx.strokeStyle = '#22c55e';
            ctx.lineWidth = 2.5;
            ctx.setLineDash([5, 5]);
            ctx.stroke();

            // Draw vertex handles
            polygonPoints.forEach((pt, pIdx) => {
                ctx.beginPath();
                ctx.arc(pt[0], pt[1], pIdx === 0 ? 6 : 4, 0, Math.PI * 2);
                ctx.fillStyle = pIdx === 0 ? '#38bdf8' : '#22c55e';
                ctx.fill();
                ctx.strokeStyle = '#ffffff';
                ctx.lineWidth = 1.5;
                ctx.stroke();
            });
            ctx.restore();
        }
    }

    function getCanvasCoords(e) {
        const rect = el.annotationCanvas.getBoundingClientRect();
        const scaleX = el.annotationCanvas.width / rect.width;
        const scaleY = el.annotationCanvas.height / rect.height;
        return {
            x: Math.round((e.clientX - rect.left) * scaleX),
            y: Math.round((e.clientY - rect.top) * scaleY),
        };
    }

    el.annotationCanvas.addEventListener('mousedown', (e) => {
        if (!state.referenceImg) return;
        if (!canAuthorFootprints()) {
            showAlert('Read-Only Layout Mode: Footprint authoring is locked to SMT Supervisors and QA Admins. Line Inspectors have view-only access.', 'warning');
            return;
        }
        const pos = getCanvasCoords(e);

        if (state.activeTool === 'rectangle') {
            isDrawing = true;
            startX = pos.x;
            startY = pos.y;
            pendingBox = [startX, startY, 0, 0];
        } else if (state.activeTool === 'pencil') {
            isDrawing = true;
            startX = pos.x;
            startY = pos.y;
            freehandStroke = [[pos.x, pos.y]];
        } else if (state.activeTool === 'polygon') {
            if (polygonPoints.length >= 3) {
                // If clicked close to starting point (within 18px), close polygon!
                const distToStart = Math.hypot(pos.x - polygonPoints[0][0], pos.y - polygonPoints[0][1]);
                if (distToStart < 18) {
                    finishPolygonMarking();
                    return;
                }
            }
            polygonPoints.push([pos.x, pos.y]);
            renderAnnotationCanvas();
        }
    });

    el.annotationCanvas.addEventListener('mousemove', (e) => {
        const pos = getCanvasCoords(e);
        currentX = pos.x;
        currentY = pos.y;

        if (state.activeTool === 'rectangle') {
            if (!isDrawing) return;
            const x = Math.min(startX, currentX);
            const y = Math.min(startY, currentY);
            const w = Math.abs(currentX - startX);
            const h = Math.abs(currentY - startY);
            pendingBox = [x, y, w, h];
            renderAnnotationCanvas();
        } else if (state.activeTool === 'pencil') {
            if (!isDrawing) return;
            freehandStroke.push([pos.x, pos.y]);
            renderAnnotationCanvas();
        } else if (state.activeTool === 'polygon') {
            if (polygonPoints.length > 0) {
                renderAnnotationCanvas();
            }
        }
    });

    el.annotationCanvas.addEventListener('mouseup', () => {
        if (state.activeTool === 'rectangle') {
            if (!isDrawing) return;
            isDrawing = false;
            if (pendingBox && pendingBox[2] >= 10 && pendingBox[3] >= 10) {
                openNameModal(pendingBox, 'rectangle', null);
            } else {
                pendingBox = null;
                renderAnnotationCanvas();
            }
        } else if (state.activeTool === 'pencil') {
            if (!isDrawing) return;
            isDrawing = false;
            if (freehandStroke.length >= 5) {
                const minX = Math.min(...freehandStroke.map(p => p[0]));
                const maxX = Math.max(...freehandStroke.map(p => p[0]));
                const minY = Math.min(...freehandStroke.map(p => p[1]));
                const maxY = Math.max(...freehandStroke.map(p => p[1]));
                const w = maxX - minX;
                const h = maxY - minY;
                if (w >= 10 && h >= 10) {
                    openNameModal([minX, minY, w, h], 'pencil', freehandStroke);
                } else {
                    freehandStroke = [];
                    renderAnnotationCanvas();
                }
            } else {
                freehandStroke = [];
                renderAnnotationCanvas();
            }
        }
    });

    // Double-click to close multi-point polygon
    el.annotationCanvas.addEventListener('dblclick', (e) => {
        if (state.activeTool === 'polygon' && polygonPoints.length >= 3) {
            finishPolygonMarking();
        }
    });

    function finishPolygonMarking() {
        if (polygonPoints.length < 3) return;
        const minX = Math.min(...polygonPoints.map(p => p[0]));
        const maxX = Math.max(...polygonPoints.map(p => p[0]));
        const minY = Math.min(...polygonPoints.map(p => p[1]));
        const maxY = Math.max(...polygonPoints.map(p => p[1]));
        const w = maxX - minX;
        const h = maxY - minY;
        if (w >= 10 && h >= 10) {
            openNameModal([minX, minY, w, h], 'polygon', polygonPoints.slice());
        }
        polygonPoints = [];
        renderAnnotationCanvas();
    }

    function openNameModal(box, shapeType = 'rectangle', poly = null) {
        pendingBox = box;
        pendingShapeType = shapeType;
        pendingPolygon = poly;
        el.compNameInput.value = '';
        el.nameModal.classList.remove('d-none');
        setTimeout(() => el.compNameInput.focus(), 50);
    }

    function closeNameModal() {
        el.nameModal.classList.add('d-none');
        pendingBox = null;
        pendingPolygon = null;
        freehandStroke = [];
        polygonPoints = [];
        renderAnnotationCanvas();
    }

    el.btnCancelName.addEventListener('click', closeNameModal);

    el.quickTagsContainer.addEventListener('click', (e) => {
        if (e.target.classList.contains('tag-chip')) {
            const prefix = e.target.getAttribute('data-prefix');
            const count = state.components.filter(c => c.name.startsWith(prefix)).length + 1;
            el.compNameInput.value = `${prefix}${count}`;
        }
    });

    el.btnSaveName.addEventListener('click', savePendingComponent);
    el.compNameInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') savePendingComponent();
        if (e.key === 'Escape') closeNameModal();
    });

    function getBoxWarning(w, h, canvasW, canvasH) {
        if (w < 20 || h < 16) {
            return 'Tight envelope: Small pad area';
        }
        if (w > canvasW * 0.5 || h > canvasH * 0.5) {
            return 'Large envelope: Excess substrate';
        }
        return null;
    }

    function savePendingComponent() {
        const name = el.compNameInput.value.trim() || `PART_${state.components.length + 1}`;
        if (pendingBox) {
            const [x, y, w, h] = pendingBox;
            const warning = getBoxWarning(w, h, state.workingDim.width, state.workingDim.height);

            state.components.push({
                id: 'comp_' + Date.now(),
                name: name,
                bbox: [x, y, w, h],
                shape_type: pendingShapeType || 'rectangle',
                polygon: pendingPolygon || null,
                warning: warning,
                normalized: [
                    Number((x / state.workingDim.width).toFixed(4)),
                    Number((y / state.workingDim.height).toFixed(4)),
                    Number((w / state.workingDim.width).toFixed(4)),
                    Number((h / state.workingDim.height).toFixed(4)),
                ],
            });
        }
        closeNameModal();
        renderAnnotationCanvas();
        renderComponentsList();
    }

    function renderComponentsList() {
        el.compCount.textContent = state.components.length;
        el.emptyCompsMsg.classList.toggle('d-none', state.components.length > 0);
        el.btnProceedToStep3.disabled = state.components.length === 0;

        // Clear dynamic items
        const existingItems = el.componentListContainer.querySelectorAll('.component-card-item');
        existingItems.forEach(item => item.remove());

        state.components.forEach((comp, idx) => {
            const item = document.createElement('div');
            item.className = 'component-card-item';

            const [x, y, w, h] = comp.bbox;
            const warningBadge = comp.warning ? `<span class="badge badge-amber" title="${comp.warning}">FLAGGED</span>` : '';

            const actionHtml = canAuthorFootprints()
                ? `
                    <div class="comp-item-actions">
                        <button type="button" class="btn-icon btn-rename" title="Rename Footprint" data-idx="${idx}">Edit</button>
                        <button type="button" class="btn-icon btn-icon-danger btn-del" title="Delete" data-idx="${idx}">&times;</button>
                    </div>
                `
                : `
                    <div class="comp-item-actions">
                        <span class="badge" style="background:#1e293b; color:#8b949e; border:1px solid #334155; font-size:0.68rem; font-weight:600;">LOCKED</span>
                    </div>
                `;

            item.innerHTML = `
                <div class="comp-item-info">
                    <div style="display:flex; align-items:center; gap:0.5rem;">
                        <span class="comp-item-name">${comp.name}</span>
                        ${warningBadge}
                    </div>
                    <span class="comp-item-coords">[${x}, ${y}, ${w}×${h} px]</span>
                </div>
                ${actionHtml}
            `;
            el.componentListContainer.appendChild(item);
        });

        // Attach action handlers
        el.componentListContainer.querySelectorAll('.btn-del').forEach(btn => {
            btn.addEventListener('click', (e) => {
                if (!canAuthorFootprints()) return;
                const idx = parseInt(e.target.getAttribute('data-idx'));
                state.components.splice(idx, 1);
                renderAnnotationCanvas();
                renderComponentsList();
            });
        });

        el.componentListContainer.querySelectorAll('.btn-rename').forEach(btn => {
            btn.addEventListener('click', (e) => {
                if (!canAuthorFootprints()) return;
                const idx = parseInt(e.target.getAttribute('data-idx'));
                const newName = prompt('Enter new component name:', state.components[idx].name);
                if (newName && newName.trim()) {
                    state.components[idx].name = newName.trim();
                    renderAnnotationCanvas();
                    renderComponentsList();
                }
            });
        });
    }

    // Quick load standard components (optional fallback)
    if (el.btnLoadSampleComps) {
        el.btnLoadSampleComps.addEventListener('click', async () => {
            if (!canAuthorFootprints()) {
                showAlert('Read-Only Layout Mode: Loading footprints requires Supervisor authorization.', 'warning');
                return;
            }
            try {
                const res = await fetch('/api/sample-components');
                if (!res.ok) throw new Error('Failed to fetch standard components');
                const data = await res.json();
                const comps = data.components;

                state.components = Object.keys(comps).map(cid => {
                    const info = comps[cid];
                    const [x, y, w, h] = info.pixel_bbox;
                    return {
                        id: cid,
                        name: cid,
                        bbox: [x, y, w, h],
                        warning: getBoxWarning(w, h, state.workingDim.width, state.workingDim.height),
                        normalized: [
                            Number((x / state.workingDim.width).toFixed(4)),
                            Number((y / state.workingDim.height).toFixed(4)),
                            Number((w / state.workingDim.width).toFixed(4)),
                            Number((h / state.workingDim.height).toFixed(4)),
                        ],
                    };
                });

                renderAnnotationCanvas();
                renderComponentsList();
            } catch (err) {
                showAlert(`Could not load standard components: ${err.message}`, 'danger');
            }
        });
    }

    el.btnClearComps.addEventListener('click', () => {
        if (!canAuthorFootprints()) {
            showAlert('Read-Only Layout Mode: Clearing footprints requires Supervisor authorization.', 'warning');
            return;
        }
        if (state.components.length === 0) return;
        if (confirm('Clear all marked components?')) {
            state.components = [];
            renderAnnotationCanvas();
            renderComponentsList();
        }
    });

    // --- RECIPE SAVE & LOAD ---
    el.btnExportRecipe.addEventListener('click', () => {
        hideAlert();
        if (state.components.length === 0) {
            showAlert('Cannot save empty recipe: please mark at least one component first.', 'danger');
            return;
        }

        const defaultName = 'PCB_BOARD_RECIPE_' + new Date().toISOString().slice(0, 10).replace(/-/g, '');
        const boardName = prompt('Enter a name for this PCB Board Recipe:', defaultName) || defaultName;

        const recipe = {
            recipe_version: '1.0',
            board_name: boardName.trim(),
            created_at: new Date().toISOString(),
            image_size: {
                width: state.workingDim.width,
                height: state.workingDim.height,
                aspect_ratio: Number((state.workingDim.width / state.workingDim.height).toFixed(4)),
            },
            image_fingerprint: state.referenceFingerprint || null,
            sensitivity: state.activeSensitivity,
            components: state.components.map(c => ({
                name: c.name,
                normalized_bbox: c.normalized,
                pixel_bbox: c.bbox,
            })),
        };

        const jsonStr = JSON.stringify(recipe, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        const safeFilename = (boardName.trim().toLowerCase().replace(/[^a-z0-9_-]/g, '_') || 'pcb_recipe') + '.json';
        a.download = safeFilename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showAlert(`Recipe "${boardName.trim()}" downloaded successfully as ${safeFilename}.`, 'success');
    });

    el.btnImportRecipe.addEventListener('click', () => {
        hideAlert();
        el.recipeFileInput.value = '';
        el.recipeFileInput.click();
    });

    el.recipeFileInput.addEventListener('change', (e) => {
        if (!e.target.files || !e.target.files[0]) return;
        const file = e.target.files[0];

        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const text = event.target.result;
                let recipe;
                try {
                    recipe = JSON.parse(text);
                } catch (parseErr) {
                    throw new Error('File is not valid JSON or syntax is corrupted.');
                }

                // Check board components
                const rawComps = recipe.components;
                if (!rawComps || !Array.isArray(rawComps) || rawComps.length === 0) {
                    throw new Error('Recipe is invalid: missing or empty "components" array.');
                }

                let loadWarnings = [];

                // Check aspect ratio (compare aspect ratio, not exact pixels; warn only, do not block)
                if (recipe.image_size && typeof recipe.image_size === 'object') {
                    const rw = recipe.image_size.width;
                    const rh = recipe.image_size.height;
                    const recipeAR = recipe.image_size.aspect_ratio || (rw && rh ? rw / rh : null);
                    const currentAR = state.workingDim.width / state.workingDim.height;
                    if (recipeAR && Math.abs(currentAR - recipeAR) > 0.02) {
                        loadWarnings.push(`Aspect ratio warning: Recipe was created for aspect ratio ${recipeAR.toFixed(2)} (${rw}×${rh}), but reference board is ${currentAR.toFixed(2)} (${state.workingDim.width}×${state.workingDim.height}). Normalized boxes may stretch.`);
                    }
                }

                // Check reference image fingerprint (warn only, do not block)
                if (recipe.image_fingerprint && state.referenceFingerprint && recipe.image_fingerprint !== state.referenceFingerprint) {
                    loadWarnings.push('Reference board fingerprint mismatch: This recipe was created for a different reference image. Please verify component alignment.');
                }

                // Parse and map components
                const newComps = [];
                for (let i = 0; i < rawComps.length; i++) {
                    const c = rawComps[i];
                    const compName = (c.name && String(c.name).trim()) || `PART_${i + 1}`;
                    let pixelBox = null;

                    if (c.pixel_bbox && Array.isArray(c.pixel_bbox) && c.pixel_bbox.length === 4) {
                        pixelBox = c.pixel_bbox.map(v => Math.round(Number(v)));
                    } else if (c.normalized_bbox && Array.isArray(c.normalized_bbox) && c.normalized_bbox.length === 4) {
                        pixelBox = [
                            Math.round(c.normalized_bbox[0] * state.workingDim.width),
                            Math.round(c.normalized_bbox[1] * state.workingDim.height),
                            Math.round(c.normalized_bbox[2] * state.workingDim.width),
                            Math.round(c.normalized_bbox[3] * state.workingDim.height),
                        ];
                    } else {
                        throw new Error(`Component #${i + 1} (${compName}) has invalid bbox data.`);
                    }

                    const [x, y, w, h] = pixelBox;
                    const warning = getBoxWarning(w, h, state.workingDim.width, state.workingDim.height);

                    newComps.push({
                        id: 'comp_' + Date.now() + '_' + i,
                        name: compName,
                        bbox: [x, y, w, h],
                        warning: warning,
                        normalized: [
                            Number((x / state.workingDim.width).toFixed(4)),
                            Number((y / state.workingDim.height).toFixed(4)),
                            Number((w / state.workingDim.width).toFixed(4)),
                            Number((h / state.workingDim.height).toFixed(4)),
                        ],
                    });
                }

                state.components = newComps;

                // Sync sensitivity if provided in recipe
                if (recipe.sensitivity && ['strict', 'balanced', 'lenient'].includes(recipe.sensitivity)) {
                    state.activeSensitivity = recipe.sensitivity;
                    const radio = document.querySelector(`input[name="sensitivity"][value="${recipe.sensitivity}"]`);
                    if (radio) {
                        radio.checked = true;
                        document.querySelectorAll('.radio-card').forEach(c => c.classList.remove('selected'));
                        radio.closest('.radio-card').classList.add('selected');
                    }
                }

                renderAnnotationCanvas();
                renderComponentsList();
                if (loadWarnings.length > 0) {
                    showAlert(`Recipe loaded (${newComps.length} parts) with warnings: ${loadWarnings.join(' | ')}`, 'warning');
                } else {
                    showAlert(`Successfully loaded recipe "${recipe.board_name || 'Custom'}" with ${newComps.length} components!`, 'success');
                }

            } catch (err) {
                showAlert(`Failed to load recipe: ${err.message}`, 'danger');
            }
        };

        reader.onerror = () => {
            showAlert('Failed to read the selected recipe file from disk.', 'danger');
        };

        reader.readAsText(file);
    });

    // --- LIVE CAMERA CONTROLS ---
    let cameraStream = null;

    async function enumerateCameraDevices() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.enumerateDevices) return;
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const videoDevices = devices.filter(d => d.kind === 'videoinput');
            el.cameraDeviceSelect.innerHTML = '';
            if (videoDevices.length === 0) {
                const opt = document.createElement('option');
                opt.value = '';
                opt.textContent = 'Default Camera';
                el.cameraDeviceSelect.appendChild(opt);
                return;
            }
            videoDevices.forEach((dev, idx) => {
                const opt = document.createElement('option');
                opt.value = dev.deviceId;
                opt.textContent = dev.label || `Camera ${idx + 1}`;
                el.cameraDeviceSelect.appendChild(opt);
            });
        } catch {
            // Devices enumeration may require permission first
        }
    }

    function showCameraError(msg) {
        el.cameraErrorBanner.textContent = msg;
        el.cameraErrorBanner.classList.remove('d-none');
    }

    function hideCameraError() {
        el.cameraErrorBanner.classList.add('d-none');
    }

    function openCameraModal() {
        hideAlert();
        hideCameraError();
        el.cameraModal.classList.remove('d-none');
        enumerateCameraDevices();
    }

    function closeCameraModal() {
        stopCamera();
        el.cameraModal.classList.add('d-none');
    }

    async function startCamera() {
        hideCameraError();
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            showCameraError('Camera API (getUserMedia) is not supported in this browser or context.');
            return;
        }

        const deviceId = el.cameraDeviceSelect.value;
        const constraints = {
            video: {
                deviceId: deviceId ? { exact: deviceId } : undefined,
                width: { ideal: 1920 },
                height: { ideal: 1080 },
            },
        };

        try {
            el.btnStartCamera.disabled = true;
            el.btnStartCamera.textContent = 'Starting Camera...';

            let stream;
            try {
                stream = await navigator.mediaDevices.getUserMedia(constraints);
            } catch (constrErr) {
                // Fallback to generic constraints if exact device or resolution constraints fail
                stream = await navigator.mediaDevices.getUserMedia({ video: true });
            }

            cameraStream = stream;
            el.cameraVideoPreview.srcObject = stream;
            el.cameraPlaceholder.classList.add('d-none');
            el.cameraLiveDot.classList.add('active');

            el.btnStartCamera.classList.add('d-none');
            el.btnStopCamera.classList.remove('d-none');
            el.btnCaptureAsRef.disabled = false;
            el.btnCaptureAsTest.disabled = false;

            // Re-enumerate to get device labels now that permission is granted
            await enumerateCameraDevices();

        } catch (err) {
            let errorMsg = `Could not access camera: ${err.message}`;
            if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
                errorMsg = 'Camera access was blocked by browser or system permissions. Please allow camera access in your browser.';
            } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
                errorMsg = 'No camera hardware device found. Please connect a USB camera or webcam.';
            } else if (err.name === 'NotReadableError' || err.name === 'TrackStartError') {
                errorMsg = 'Camera hardware is currently in use by another application or locked by the OS.';
            }
            showCameraError(errorMsg);
        } finally {
            el.btnStartCamera.disabled = false;
            el.btnStartCamera.textContent = 'Start Camera';
        }
    }

    function stopCamera() {
        if (cameraStream) {
            cameraStream.getTracks().forEach(track => track.stop());
            cameraStream = null;
        }
        el.cameraVideoPreview.srcObject = null;
        el.cameraPlaceholder.classList.remove('d-none');
        el.cameraLiveDot.classList.remove('active');

        el.btnStartCamera.classList.remove('d-none');
        el.btnStopCamera.classList.add('d-none');
        el.btnCaptureAsRef.disabled = true;
        el.btnCaptureAsTest.disabled = true;
    }

    function captureCameraFrame(targetMode) {
        const video = el.cameraVideoPreview;
        const canvas = el.cameraCaptureCanvas;

        const w = video.videoWidth || 1920;
        const h = video.videoHeight || 1080;
        canvas.width = w;
        canvas.height = h;

        const ctx = canvas.getContext('2d');
        ctx.drawImage(video, 0, 0, w, h);

        canvas.toBlob((blob) => {
            if (!blob) {
                showCameraError('Failed to capture frame from video feed.');
                return;
            }
            const filename = `camera_${targetMode}_${Date.now()}.png`;
            const file = new File([blob], filename, { type: 'image/png' });

            closeCameraModal();

            if (targetMode === 'ref') {
                handleReferenceFile(file);
            } else if (targetMode === 'test') {
                addTestFiles([file]);
                if (state.currentStep !== 3) {
                    setStep(3);
                }
                showAlert(`Captured frame "${filename}" added to test board queue.`, 'success');
            }
        }, 'image/png');
    }

    el.btnOpenCamera.addEventListener('click', openCameraModal);
    el.btnCameraRef.addEventListener('click', openCameraModal);
    el.btnCameraTest.addEventListener('click', openCameraModal);
    el.btnCloseCamera.addEventListener('click', closeCameraModal);
    el.btnStartCamera.addEventListener('click', startCamera);
    el.btnStopCamera.addEventListener('click', stopCamera);
    el.cameraDeviceSelect.addEventListener('change', () => {
        if (cameraStream) {
            startCamera(); // Restart with new device
        }
    });
    el.btnCaptureAsRef.addEventListener('click', () => captureCameraFrame('ref'));
    el.btnCaptureAsTest.addEventListener('click', () => captureCameraFrame('test'));

    // Step 2 Proceed to Step 3
    el.btnProceedToStep3.addEventListener('click', async () => {
        if (state.components.length === 0) {
            showAlert('Please mark at least one component before proceeding.', 'danger');
            return;
        }

        try {
            el.btnProceedToStep3.disabled = true;
            el.btnProceedToStep3.textContent = 'Saving annotations...';

            const payload = {
                components: state.components.map(c => ({
                    name: c.name,
                    bbox: c.bbox,
                    shape_type: c.shape_type || 'rectangle',
                    polygon: c.polygon || null,
                    is_normalized: false,
                })),
            };

            const resp = await fetch(`/api/sessions/${state.sessionId}/components`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Failed to save components');
            }

            setStep(3);
        } catch (err) {
            showAlert(`Error saving components: ${err.message}`, 'danger');
        } finally {
            el.btnProceedToStep3.disabled = false;
            el.btnProceedToStep3.textContent = 'Proceed to Inspection →';
        }
    });

    // --- STEP 3: TEST INSPECTION ---
    el.btnBrowseTest.addEventListener('click', () => el.testFileInput.click());

    el.testFileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            addTestFiles(Array.from(e.target.files));
        }
    });

    el.testDropzone.addEventListener('dragover', (e) => {
        e.preventDefault();
        el.testDropzone.classList.add('dragover');
    });

    el.testDropzone.addEventListener('dragleave', () => {
        el.testDropzone.classList.remove('dragover');
    });

    el.testDropzone.addEventListener('drop', (e) => {
        e.preventDefault();
        el.testDropzone.classList.remove('dragover');
        if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
            addTestFiles(Array.from(e.dataTransfer.files));
        }
    });

    function addTestFiles(files) {
        hideAlert();
        files.forEach(f => {
            // Avoid duplicate filenames in batch
            if (!state.testFiles.some(existing => existing.name === f.name)) {
                state.testFiles.push(f);
            }
        });
        renderTestFileList();
    }

    function renderTestFileList() {
        el.testFileList.innerHTML = '';
        state.testFiles.forEach((file, idx) => {
            const tag = document.createElement('span');
            tag.className = 'file-tag';
            tag.innerHTML = `${file.name} <button type="button" class="btn-link" style="color:#f85149; margin-left:4px;" data-idx="${idx}">&times;</button>`;
            el.testFileList.appendChild(tag);
        });

        el.testFileList.querySelectorAll('button').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.target.getAttribute('data-idx'));
                state.testFiles.splice(idx, 1);
                renderTestFileList();
            });
        });

        el.btnRunInspect.disabled = state.testFiles.length === 0;
    }

    // Quick sample batch loader (optional fallback)
    if (el.btnLoadSampleBatch) {
        el.btnLoadSampleBatch.addEventListener('click', async () => {
            const sampleFiles = [
                { name: 'calib_01_all_ok_nominal.png', path: '/sample_data/calibration/calib_01_all_ok_nominal.png' },
                { name: 'calib_08_missing_u1_mcu.png', path: '/sample_data/calibration/calib_08_missing_u1_mcu.png' },
                { name: 'calib_12_missing_adj_c1_c2.png', path: '/sample_data/calibration/calib_12_missing_adj_c1_c2.png' },
            ];

            try {
                el.btnLoadSampleBatch.disabled = true;
                el.btnLoadSampleBatch.textContent = 'Loading sample batch...';

                for (const item of sampleFiles) {
                    const res = await fetch(item.path);
                    if (res.ok) {
                        const blob = await res.blob();
                        const file = new File([blob], item.name, { type: 'image/png' });
                        addTestFiles([file]);
                    }
                }
            } catch (err) {
                showAlert(`Failed to load sample batch: ${err.message}`, 'danger');
            } finally {
                el.btnLoadSampleBatch.disabled = false;
                el.btnLoadSampleBatch.textContent = 'Load Sample Batch';
            }
        });
    }

    // 1-Click Load Physical Test Batch for Active Preset
    if (el.btnLoadPresetBatch) {
        el.btnLoadPresetBatch.addEventListener('click', async () => {
            let preset = state.activePreset;
            if (!preset && state.presets && state.presets.length > 0) {
                preset = state.presets[0];
            }
            if (!preset || !preset.sample_tests || preset.sample_tests.length === 0) {
                showAlert('No pre-configured physical test batch found for this board. Please select a golden board preset first.', 'warning');
                return;
            }

            try {
                el.btnLoadPresetBatch.disabled = true;
                el.btnLoadPresetBatch.textContent = 'Loading physical test boards...';

                const loadedFiles = [];
                for (const item of preset.sample_tests) {
                    const res = await fetch(item.url);
                    if (res.ok) {
                        const blob = await res.blob();
                        const file = new File([blob], item.name, { type: 'image/png' });
                        loadedFiles.push(file);
                    }
                }
                if (loadedFiles.length > 0) {
                    addTestFiles(loadedFiles);
                    showAlert(`Loaded ${loadedFiles.length} physical test boards (nominal, missing, tilted, shifted) for "${preset.name}"!`, 'success');
                } else {
                    showAlert('Could not load physical test images from server.', 'danger');
                }
            } catch (err) {
                showAlert(`Failed to load physical test batch: ${err.message}`, 'danger');
            } finally {
                el.btnLoadPresetBatch.disabled = false;
                el.btnLoadPresetBatch.textContent = 'Load Physical Test Batch for This Board';
            }
        });
    }

    // Run Automated Inspection (Single Click - Balanced Calibrated Operating Standard)
    el.btnRunInspect.addEventListener('click', async () => {
        if (state.testFiles.length === 0) return;

        hideAlert();
        el.inspectionSpinner.classList.remove('d-none');
        el.btnRunInspect.disabled = true;
        el.resultsCardsContainer.innerHTML = '';
        el.inspectionResultsArea.classList.add('d-none');

        const formData = new FormData();
        formData.append('session_id', state.sessionId);
        formData.append('sensitivity', 'balanced');
        formData.append('enable_cascade', true);
        if (state.activeTolerances) {
            if (state.activeTolerances.max_tilt_deg !== undefined) {
                formData.append('max_tilt_deg', state.activeTolerances.max_tilt_deg);
            }
            if (state.activeTolerances.max_shift_px !== undefined) {
                formData.append('max_shift_px', state.activeTolerances.max_shift_px);
            }
        }

        state.testFiles.forEach(file => {
            formData.append('test_images', file);
        });

        try {
            const resp = await fetch('/api/inspect', {
                method: 'POST',
                body: formData,
            });

            if (!resp.ok) {
                const err = await resp.json();
                throw new Error(err.detail || 'Inspection request failed');
            }

            const data = await resp.json();
            renderInspectionResults(data);

        } catch (err) {
            showAlert(`Inspection failed: ${err.message}`, 'danger');
        } finally {
            el.inspectionSpinner.classList.add('d-none');
            el.btnRunInspect.disabled = false;
        }
    });

    // --- RENDER INSPECTION RESULTS & BATCH SUMMARY ---
    function renderInspectionResults(data) {
        state.lastInspectionData = data;
        el.inspectionResultsArea.classList.remove('d-none');
        if (el.batchSummaryPanel) {
            el.batchSummaryPanel.classList.remove('d-none');
        }

        renderResultCards();
        updateBatchSummary();

        // Scroll to results
        el.inspectionResultsArea.scrollIntoView({ behavior: 'smooth' });
    }

    function renderComponentRowsHtml(res, resIdx, bSign) {
        return res.components.map(c => {
            const sign = bSign[c.name];
            let badgeClass = 'badge-success';
            let rowClass = '';
            if (c.status === 'MISSING') {
                badgeClass = 'badge-danger';
                rowClass = 'row-missing';
            } else if (c.status === 'TILTED') {
                badgeClass = 'badge-tilted';
                rowClass = 'row-tilted';
            } else if (c.status === 'MISALIGNED') {
                badgeClass = 'badge-misaligned';
                rowClass = 'row-misaligned';
            } else if (c.status === 'BRIDGED') {
                badgeClass = 'badge-bridged';
                rowClass = 'row-bridged';
            } else if (c.status === 'POLARITY_REVERSED') {
                badgeClass = 'badge-polarity';
                rowClass = 'row-polarity';
            } else if (c.status === 'TOMBSTONED') {
                badgeClass = 'badge-tombstoned';
                rowClass = 'row-tombstoned';
            } else if (c.status === 'UNCERTAIN') {
                badgeClass = 'badge-amber';
                rowClass = 'row-uncertain';
            }

            const tiltStr = (c.scores && c.scores.tilt_deg !== undefined)
                ? (c.scores.tilt_deg > 0 ? `+${c.scores.tilt_deg.toFixed(1)}°` : `${c.scores.tilt_deg.toFixed(1)}°`)
                : '0.0°';
            const shiftStr = (c.scores && c.scores.shift_dist_px !== undefined)
                ? `${c.scores.shift_dist_px.toFixed(1)} px`
                : '0.0 px';

            const isMachineDefect = ['MISSING', 'TILTED', 'MISALIGNED', 'BRIDGED', 'POLARITY_REVERSED', 'TOMBSTONED'].includes(c.status);
            let signoffHtml = '';

            if (c.status === 'UNCERTAIN') {
                if (sign) {
                    const isPres = sign.final_status === 'PRESENT';
                    const signBadge = isPres ? 'badge-signoff-verified' : 'badge-signoff-confirmed';
                    const signIcon = isPres ? 'PASS' : 'DEFECT';
                    signoffHtml = `
                        <div style="margin-top:0.35rem;">
                            <span class="${signBadge}">${signIcon}: ${isPres ? 'VERIFIED PRESENT' : 'CONFIRMED DEFECT'}</span>
                            <span style="font-size:0.75rem; color:#8b949e; margin-left:0.3rem;">(By ${sign.operator_id} [${sign.operator_role || 'INSPECTOR'}]${sign.note ? ' &bull; ' + sign.note : ''})</span>
                            <button type="button" class="btn-link btn-edit-signoff" data-res-idx="${resIdx}" data-fname="${res.filename}" data-comp="${c.name}" style="margin-left:0.5rem; font-size:0.75rem; color:#58a6ff;">Edit</button>
                        </div>
                        <div style="font-size:0.75rem; color:#8b949e; margin-top:2px;">Original Machine Verdict: UNCERTAIN</div>
                    `;
                } else {
                    signoffHtml = `
                        <div class="signoff-box">
                            <div class="signoff-header-text">Operator Sign-Off Required for Discrepancy</div>
                            <div class="signoff-controls-row">
                                <input type="text" class="signoff-input signoff-input-badge" id="badge-${resIdx}-${c.name}" placeholder="Badge ID" value="${state.currentUser ? state.currentUser.badge : 'OP-8402'}">
                                <input type="text" class="signoff-input signoff-input-note" id="note-${resIdx}-${c.name}" placeholder="Optional note (e.g. glare on lead)">
                                <button type="button" class="btn btn-sm btn-success btn-signoff" data-res-idx="${resIdx}" data-fname="${res.filename}" data-comp="${c.name}" data-verdict="PRESENT">Verify Present</button>
                                <button type="button" class="btn btn-sm btn-danger btn-signoff" data-res-idx="${resIdx}" data-fname="${res.filename}" data-comp="${c.name}" data-verdict="MISSING">Confirm Defect</button>
                            </div>
                        </div>
                    `;
                }
            } else if (isMachineDefect) {
                if (sign && sign.final_status === 'PRESENT') {
                    signoffHtml = `
                        <div style="margin-top:0.35rem;">
                            <span class="badge-override-active">OVERRIDE: PRESENT</span>
                            <span style="font-size:0.75rem; color:#8b949e; margin-left:0.3rem;">(By ${sign.operator_id} [${sign.operator_role || 'SUPERVISOR'}]${sign.note ? ' &bull; ' + sign.note : ''})</span>
                            ${canOverrideDefects() ? `<button type="button" class="btn-link btn-edit-signoff" data-res-idx="${resIdx}" data-fname="${res.filename}" data-comp="${c.name}" style="margin-left:0.5rem; font-size:0.75rem; color:#58a6ff;">Revert</button>` : ''}
                        </div>
                        <div style="font-size:0.75rem; color:#8b949e; margin-top:2px;">Original Machine Verdict: ${c.status}</div>
                    `;
                } else if (canOverrideDefects()) {
                    signoffHtml = `
                        <div style="margin-top:0.35rem;">
                            <button type="button" class="btn-trigger-override" data-target="override-${resIdx}-${c.name}">
                                <svg class="ui-icon" style="width:12px;height:12px;"><use href="#icon-settings"></use></svg> Override Defect to PASS
                            </button>
                            <div id="override-${resIdx}-${c.name}" class="override-box d-none">
                                <div class="override-title">
                                    <svg class="ui-icon" style="width:14px;height:14px;"><use href="#icon-alert"></use></svg>
                                    Supervisor Disposition Override (IPC-A-610)
                                </div>
                                <div class="override-controls-row">
                                    <input type="text" class="signoff-input signoff-input-badge" id="ovr-badge-${resIdx}-${c.name}" placeholder="Supervisor ID" value="${state.currentUser ? state.currentUser.badge : 'LEAD-104'}">
                                    <input type="text" class="signoff-input signoff-input-note" id="ovr-note-${resIdx}-${c.name}" placeholder="Mandatory engineering rationale (e.g. verified under loupe)" style="flex:1; min-width:220px;">
                                    <button type="button" class="btn btn-sm btn-primary btn-confirm-override" data-res-idx="${resIdx}" data-fname="${res.filename}" data-comp="${c.name}">Authorize Pass</button>
                                    <button type="button" class="btn btn-sm btn-outline btn-cancel-override" data-target="override-${resIdx}-${c.name}">Cancel</button>
                                </div>
                            </div>
                        </div>
                    `;
                } else {
                    signoffHtml = `
                        <div style="margin-top:0.35rem; font-size:0.75rem; color:#8b949e;">
                            Defect flagged by AOI &bull; Overrides locked to Supervisor / Admin
                        </div>
                    `;
                }
            }

            const shapeBadge = c.shape_type === 'pencil' ? '<span style="color:#38bdf8; font-size:0.75rem;" title="Non-linear pencil contour">✎</span>' : (c.shape_type === 'polygon' ? '<span style="color:#38bdf8; font-size:0.75rem;" title="Polygon contour">⬡</span>' : '');

            return `
                <tr class="result-row clickable-comp-row ${rowClass}" data-res-idx="${resIdx}" data-comp-name="${c.name}" title="Click to inspect in 3× Digital Loupe">
                    <td style="cursor: pointer;">
                        <div style="display:flex; align-items:center; gap:0.45rem;">
                            <svg class="ui-icon" style="width:13px; height:13px; color:var(--color-blue);"><use href="#icon-loupe"></use></svg>
                            <strong>${c.name}</strong> ${shapeBadge}
                        </div>
                    </td>
                    <td>
                        <span class="badge ${badgeClass}">${c.status}</span>
                        ${signoffHtml}
                    </td>
                    <td class="score-num">${c.scores ? c.scores.zncc.toFixed(4) : 'N/A'}</td>
                    <td class="score-num ${c.status === 'TILTED' ? 'val-defect' : ''}">${tiltStr}</td>
                    <td class="score-num ${c.status === 'MISALIGNED' ? 'val-defect' : ''}">${shiftStr}</td>
                    <td>${c.reason}</td>
                </tr>
            `;
        }).join('');
    }

    function drawCarouselReferenceCanvas() {
        const canvas = document.getElementById('carousel-ref-canvas');
        if (!canvas || !state.referenceImg) return;
        canvas.width = state.workingDim.width;
        canvas.height = state.workingDim.height;
        const ctx = canvas.getContext('2d');
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(state.referenceImg, 0, 0, canvas.width, canvas.height);

        // Draw component outlines on reference board
        state.components.forEach(comp => {
            const [x, y, w, h] = comp.bbox;
            if (comp.polygon && comp.polygon.length >= 3) {
                ctx.save();
                ctx.beginPath();
                ctx.moveTo(comp.polygon[0][0], comp.polygon[0][1]);
                for (let i = 1; i < comp.polygon.length; i++) {
                    ctx.lineTo(comp.polygon[i][0], comp.polygon[i][1]);
                }
                ctx.closePath();
                ctx.strokeStyle = '#38bdf8';
                ctx.lineWidth = 2.5;
                ctx.stroke();
                ctx.fillStyle = 'rgba(56, 189, 248, 0.2)';
                ctx.fill();
                ctx.restore();
            } else {
                ctx.strokeStyle = '#38bdf8';
                ctx.lineWidth = 2.5;
                ctx.strokeRect(x, y, w, h);
                ctx.fillStyle = 'rgba(56, 189, 248, 0.15)';
                ctx.fillRect(x, y, w, h);
            }
            // Label
            ctx.fillStyle = '#0284c7';
            ctx.font = 'bold 15px -apple-system, sans-serif';
            const tw = ctx.measureText(comp.name).width;
            ctx.fillRect(x, Math.max(0, y - 20), tw + 8, 20);
            ctx.fillStyle = '#ffffff';
            ctx.fillText(comp.name, x + 4, Math.max(14, y - 5));
        });
    }

    function setupViewportZoom(frameId, btnId) {
        const frame = document.getElementById(frameId);
        const btn = document.getElementById(btnId);
        if (!frame) return;

        let isZoomed = false;
        function toggleZoom() {
            isZoomed = !isZoomed;
            frame.classList.toggle('is-zoomed', isZoomed);
            if (btn) {
                btn.classList.toggle('active', isZoomed);
                btn.innerHTML = `<svg class="ui-icon" style="width:12px;height:12px;"><use href="#icon-loupe"></use></svg> ${isZoomed ? 'Reset Zoom' : 'Zoom In'}`;
            }
        }

        if (btn) {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                toggleZoom();
            });
        }

        frame.addEventListener('click', () => {
            toggleZoom();
        });

        frame.addEventListener('mousemove', (e) => {
            if (!frame.classList.contains('is-zoomed')) return;
            const rect = frame.getBoundingClientRect();
            const xPct = Math.max(0, Math.min(100, ((e.clientX - rect.left) / rect.width) * 100));
            const yPct = Math.max(0, Math.min(100, ((e.clientY - rect.top) / rect.height) * 100));
            const canvas = frame.querySelector('canvas');
            if (canvas) {
                canvas.style.transformOrigin = `${xPct}% ${yPct}%`;
            }
        });
    }

    function renderCarouselStationCard(data) {
        el.resultsCardsContainer.innerHTML = '';
        if (!data || !data.results || data.results.length === 0) return;

        const totalBoards = data.results.length;
        const currIdx = Math.max(0, Math.min(state.carouselIndex || 0, totalBoards - 1));
        state.carouselIndex = currIdx;
        const res = data.results[currIdx];
        const bSign = state.signoffs[res.filename] || {};

        let okCount = 0, defectCount = 0, reviewCount = 0;
        const boardStatuses = data.results.map((r, rIdx) => {
            const rSign = state.signoffs[r.filename] || {};
            let hasD = false, hasU = false;
            r.components.forEach(c => {
                const s = rSign[c.name] ? rSign[c.name].final_status : c.status;
                if (['MISSING', 'TILTED', 'MISALIGNED', 'BRIDGED', 'POLARITY_REVERSED', 'TOMBSTONED'].includes(s)) hasD = true;
                else if (s === 'UNCERTAIN') hasU = true;
            });
            const stat = hasD ? 'DEFECT' : (hasU ? 'REVIEW' : 'OK');
            if (stat === 'OK') okCount++;
            else if (stat === 'DEFECT') defectCount++;
            else if (stat === 'REVIEW') reviewCount++;
            return { rIdx, stat, hasD, hasU };
        });

        el.resultsSummaryBadge.className = defectCount > 0 ? 'badge badge-danger' : (reviewCount > 0 ? 'badge badge-amber' : 'badge badge-success');
        el.resultsSummaryBadge.textContent = `${totalBoards} Board(s): ${okCount} OK, ${defectCount} Defect, ${reviewCount} Review`;

        const curStatus = boardStatuses[currIdx].stat;
        let badgeClass = 'badge-success';
        if (curStatus === 'DEFECT') {
            badgeClass = 'badge-danger';
        } else if (curStatus === 'REVIEW') {
            badgeClass = 'badge-amber';
        }

        const alignNotice = res.alignment && res.alignment.fallback_used
            ? `<div class="alignment-notice" style="margin: 0.5rem 1.25rem 0;">Alignment Notice: ${res.alignment.message} (dx: ${res.alignment.dx_px}px, dy: ${res.alignment.dy_px}px)</div>`
            : '';

        const container = document.createElement('div');
        container.className = 'station-carousel-container';

        container.innerHTML = `
            <!-- Top Bar: Header & Quick Jump Pills -->
            <div class="station-carousel-header">
                <div class="station-title-block">
                    <span class="badge ${badgeClass}" style="font-size:0.85rem; padding: 0.35rem 0.75rem;">${curStatus}</span>
                    <div>
                        <div class="station-board-name">Board ${currIdx + 1} of ${totalBoards}: ${res.filename}</div>
                        <div class="station-board-meta">${res.summary} ${res.elapsed_ms ? `&bull; Tact time: ${res.elapsed_ms} ms` : ''}</div>
                    </div>
                </div>
                <div class="station-jump-pills">
                    ${boardStatuses.map(b => {
                        const pillDefect = b.hasD ? 'pill-defect' : '';
                        const pillActive = b.rIdx === currIdx ? 'active' : '';
                        return `<button type="button" class="station-jump-pill ${pillDefect} ${pillActive}" data-card-idx="${b.rIdx}">Board ${b.rIdx + 1}: ${b.stat}</button>`;
                    }).join('')}
                </div>
            </div>
            ${alignNotice}

            <!-- Side-by-Side Dual Viewport Card (Excalidraw Card Layout) -->
            <div class="station-dual-viewport-card">
                <!-- Left: Reference Image Viewport -->
                <div class="station-viewport-panel">
                    <div class="station-viewport-bar">
                        <div class="station-viewport-title">
                            <span class="indicator-dot-ref"></span> Reference Image
                        </div>
                        <button type="button" class="btn-viewport-zoom" id="btn-zoom-ref">
                            <svg class="ui-icon" style="width:12px;height:12px;"><use href="#icon-loupe"></use></svg> Zoom In
                        </button>
                    </div>
                    <div class="station-canvas-frame" id="frame-carousel-ref" title="Click or hover to zoom">
                        <canvas id="carousel-ref-canvas"></canvas>
                    </div>
                </div>

                <!-- Right: Test Board Viewport -->
                <div class="station-viewport-panel">
                    <div class="station-viewport-bar">
                        <div class="station-viewport-title">
                            <span class="indicator-dot-test"></span> Test Board (${res.filename})
                        </div>
                        <button type="button" class="btn-viewport-zoom" id="btn-zoom-test">
                            <svg class="ui-icon" style="width:12px;height:12px;"><use href="#icon-loupe"></use></svg> Zoom In
                        </button>
                    </div>
                    <div class="station-canvas-frame" id="frame-carousel-test" title="Click or hover to zoom">
                        <canvas id="carousel-test-canvas"></canvas>
                    </div>
                </div>
            </div>

            <!-- Carousel Arrow Controls Bar (as sketched by user: [ ← ] and [ → ]) -->
            <div class="station-carousel-controls">
                <button type="button" class="btn-carousel-arrow" id="btn-carousel-prev" ${currIdx === 0 ? 'disabled' : ''}>
                    <svg class="ui-icon" style="width:14px;height:14px;"><use href="#icon-arrow-left"></use></svg> Previous Board
                </button>
                <span class="station-counter-indicator">Board ${currIdx + 1} of ${totalBoards}</span>
                <button type="button" class="btn-carousel-arrow" id="btn-carousel-next" ${currIdx === totalBoards - 1 ? 'disabled' : ''}>
                    Next Board <svg class="ui-icon" style="width:14px;height:14px;"><use href="#icon-arrow-right"></use></svg>
                </button>
            </div>

            <!-- Connected Component Table Section -->
            <div class="station-table-section">
                <div class="station-table-section-title">
                    <span>Component Breakdown &bull; <strong style="color:#38bdf8;">${res.filename}</strong> (${res.components.length} parts)</span>
                    <span style="font-size:0.75rem; color:#8b949e; font-weight:normal;">Click any row to inspect in 3× Loupe</span>
                </div>
                <div class="result-table-wrap">
                    <table class="result-table">
                        <thead>
                            <tr>
                                <th>Component (3× Loupe)</th>
                                <th>Verdict &amp; Operator Sign-Off</th>
                                <th>ZNCC</th>
                                <th>Tilt (°)</th>
                                <th>Shift (px)</th>
                                <th>Diagnostic Reason</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${renderComponentRowsHtml(res, currIdx, bSign)}
                        </tbody>
                    </table>
                </div>

                <!-- Digital Microscope Loupe Pop-Out Container -->
                <div id="loupe-container-${currIdx}" class="microscope-loupe-card d-none"></div>
            </div>
        `;

        el.resultsCardsContainer.appendChild(container);

        // Draw canvases
        drawCarouselReferenceCanvas();
        drawResultCanvas('carousel-test-canvas', res);

        // Wire zoom & pan
        setupViewportZoom('frame-carousel-ref', 'btn-zoom-ref');
        setupViewportZoom('frame-carousel-test', 'btn-zoom-test');

        // Wire jump pills
        container.querySelectorAll('.station-jump-pill').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const targetIdx = parseInt(e.currentTarget.getAttribute('data-card-idx'));
                if (!isNaN(targetIdx) && targetIdx !== state.carouselIndex) {
                    state.carouselIndex = targetIdx;
                    renderResultCards();
                }
            });
        });

        // Wire arrow navigation
        const btnPrev = document.getElementById('btn-carousel-prev');
        const btnNext = document.getElementById('btn-carousel-next');
        if (btnPrev) {
            btnPrev.addEventListener('click', () => {
                if (state.carouselIndex > 0) {
                    state.carouselIndex--;
                    renderResultCards();
                }
            });
        }
        if (btnNext) {
            btnNext.addEventListener('click', () => {
                if (state.carouselIndex < totalBoards - 1) {
                    state.carouselIndex++;
                    renderResultCards();
                }
            });
        }

        // Attach Sign-Off Handlers, Loupe, and Archive
        attachSignoffHandlers();
        attachMicroscopeLoupeHandlers();
        recordBatchInArchive(data);
    }

    function renderResultCards() {
        if (!state.lastInspectionData) return;
        const data = state.lastInspectionData;

        // Sync view toggle buttons
        if (el.toggleViewCarousel) el.toggleViewCarousel.classList.toggle('active', state.resultsViewMode === 'carousel');
        if (el.toggleViewStacked) el.toggleViewStacked.classList.toggle('active', state.resultsViewMode === 'stacked');

        if (state.resultsViewMode === 'carousel') {
            renderCarouselStationCard(data);
            return;
        }

        // Stacked View:
        el.resultsCardsContainer.innerHTML = '';
        let okCount = 0, defectCount = 0, reviewCount = 0;

        data.results.forEach((res, resIdx) => {
            const bSign = state.signoffs[res.filename] || {};

            let hasDefect = false;
            let hasUncertain = false;
            let hasSignoffs = false;

            res.components.forEach(c => {
                const sign = bSign[c.name];
                const effStatus = sign ? sign.final_status : c.status;
                if (['MISSING', 'TILTED', 'MISALIGNED', 'BRIDGED', 'POLARITY_REVERSED', 'TOMBSTONED'].includes(effStatus)) hasDefect = true;
                else if (effStatus === 'UNCERTAIN') hasUncertain = true;
                if (sign) hasSignoffs = true;
            });

            let effectiveBoardStatus = hasDefect ? 'DEFECT' : (hasUncertain ? 'REVIEW' : 'OK');
            if (res.board_status === 'ERROR') effectiveBoardStatus = 'ERROR';

            if (effectiveBoardStatus === 'OK') okCount++;
            else if (effectiveBoardStatus === 'DEFECT') defectCount++;
            else if (effectiveBoardStatus === 'REVIEW') reviewCount++;

            const card = document.createElement('div');
            card.className = 'result-card';

            let bannerClass = 'banner-ok';
            let iconText = 'PASS';
            let titleText = 'INSPECTION PASSED — ALL COMPONENTS VERIFIED';

            if (effectiveBoardStatus === 'DEFECT') {
                bannerClass = 'banner-defect';
                iconText = 'DEFECT';
                titleText = hasSignoffs && res.board_status === 'REVIEW'
                    ? 'DEFECT CONFIRMED VIA OPERATOR SIGN-OFF'
                    : 'SMT DEFECTS DETECTED (MISSING / SKEW / LATERAL DISPLACEMENT)';
            } else if (effectiveBoardStatus === 'REVIEW') {
                bannerClass = 'banner-review';
                iconText = 'DISCREPANCY';
                titleText = 'DISCREPANCY DETECTED — OPERATOR VERIFICATION REQUIRED';
            } else if (effectiveBoardStatus === 'OK' && hasSignoffs && res.board_status === 'REVIEW') {
                bannerClass = 'banner-ok';
                iconText = 'VERIFIED';
                titleText = 'INSPECTION PASSED (OPERATOR VERIFIED)';
            } else if (effectiveBoardStatus === 'ERROR') {
                bannerClass = 'banner-defect';
                iconText = 'ERROR';
                titleText = 'PROCESSING ERROR';
            }

            const alignNotice = res.alignment && res.alignment.fallback_used
                ? `<div class="alignment-notice">Alignment Notice: ${res.alignment.message} (dx: ${res.alignment.dx_px}px, dy: ${res.alignment.dy_px}px)</div>`
                : '';

            card.innerHTML = `
                <div class="result-banner ${bannerClass}">
                    <div>
                        <div class="banner-status-title"><span class="banner-tag">${iconText}</span> ${titleText}</div>
                        <div class="banner-summary">${res.summary} ${hasSignoffs ? '<span style="opacity:0.9;">(Operator review logged)</span>' : ''}</div>
                    </div>
                    <div style="text-align:right;">
                        <span class="banner-filename">${res.filename}</span>
                        ${res.elapsed_ms ? `<div style="font-size:0.75rem; opacity:0.8;">Tact time: ${res.elapsed_ms} ms</div>` : ''}
                    </div>
                </div>
                ${alignNotice}
                <div class="result-view-header">
                    <div style="display:flex; align-items:center; gap:0.5rem;">
                        <span class="badge badge-outline" style="font-size:0.75rem; color:var(--color-blue); border-color:rgba(56,189,248,0.3);">
                            <svg class="ui-icon btn-svg-icon"><use href="#icon-scan"></use></svg> Optical Defect Overlay
                        </span>
                    </div>
                    <span style="font-size: 0.76rem; color: var(--color-blue); font-weight: 500;">Select any component row below to inspect in 3× Digital Loupe</span>
                </div>

                <div class="result-card-body">
                    <div class="result-image-view">
                        <canvas id="res-canvas-${resIdx}"></canvas>
                    </div>

                    <div class="result-table-wrap">
                        <table class="result-table">
                            <thead>
                                <tr>
                                <th>Component (3× Loupe)</th>
                                <th>Verdict &amp; Operator Sign-Off</th>
                                <th>ZNCC</th>
                                <th>Tilt (°)</th>
                                <th>Shift (px)</th>
                                <th>Diagnostic Reason</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${renderComponentRowsHtml(res, resIdx, bSign)}
                            </tbody>
                        </table>
                    </div>
                </div>

                <!-- Digital Microscope Loupe Pop-Out Container -->
                <div id="loupe-container-${resIdx}" class="microscope-loupe-card d-none"></div>
            `;

            el.resultsCardsContainer.appendChild(card);
            drawResultCanvas(`res-canvas-${resIdx}`, res);
        });

        el.resultsSummaryBadge.className = defectCount > 0 ? 'badge badge-danger' : (reviewCount > 0 ? 'badge badge-amber' : 'badge badge-success');
        el.resultsSummaryBadge.textContent = `${data.results.length} Board(s): ${okCount} OK, ${defectCount} Defect, ${reviewCount} Review`;

        attachSignoffHandlers();
        attachMicroscopeLoupeHandlers();
        recordBatchInArchive(data);
    }

    function attachSignoffHandlers() {
        // Routine signoff buttons (for UNCERTAIN calls)
        el.resultsCardsContainer.querySelectorAll('.btn-signoff').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const target = e.currentTarget;
                const resIdx = target.getAttribute('data-res-idx');
                const fname = target.getAttribute('data-fname');
                const comp = target.getAttribute('data-comp');
                const verdict = target.getAttribute('data-verdict');

                const badgeEl = document.getElementById(`badge-${resIdx}-${comp}`);
                const noteEl = document.getElementById(`note-${resIdx}-${comp}`);
                const badge = (badgeEl && badgeEl.value.trim()) || (state.currentUser ? state.currentUser.badge : 'OP-8402');
                const note = (noteEl && noteEl.value.trim()) || '';
                const role = state.currentUser ? state.currentUser.role : 'INSPECTOR';

                if (!state.signoffs[fname]) state.signoffs[fname] = {};
                state.signoffs[fname][comp] = {
                    final_status: verdict,
                    operator_id: badge,
                    operator_role: role,
                    note: note,
                    timestamp: new Date().toLocaleTimeString(),
                };

                // Sync to backend if session exists
                if (state.sessionId) {
                    try {
                        const resp = await fetch(`/api/sessions/${state.sessionId}/signoff`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                filename: fname,
                                component_name: comp,
                                final_status: verdict,
                                operator_id: badge,
                                operator_role: role,
                                note: note,
                            }),
                        });
                        if (!resp.ok) {
                            const errData = await resp.json().catch(() => ({}));
                            throw new Error(errData.detail || 'Signoff failed');
                        }
                    } catch (err) {
                        showAlert(`Signoff error: ${err.message}`, 'danger');
                    }
                }

                renderResultCards();
                updateBatchSummary();
            });
        });

        // Toggle Defect Override Box
        el.resultsCardsContainer.querySelectorAll('.btn-trigger-override').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const targetId = e.currentTarget.getAttribute('data-target');
                const box = document.getElementById(targetId);
                if (box) {
                    box.classList.toggle('d-none');
                }
            });
        });

        // Cancel Defect Override Box
        el.resultsCardsContainer.querySelectorAll('.btn-cancel-override').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const targetId = e.currentTarget.getAttribute('data-target');
                const box = document.getElementById(targetId);
                if (box) {
                    box.classList.add('d-none');
                }
            });
        });

        // Confirm Defect Override to PASS (Supervisor / Admin)
        el.resultsCardsContainer.querySelectorAll('.btn-confirm-override').forEach(btn => {
            btn.addEventListener('click', async (e) => {
                const target = e.currentTarget;
                const resIdx = target.getAttribute('data-res-idx');
                const fname = target.getAttribute('data-fname');
                const comp = target.getAttribute('data-comp');

                const badgeEl = document.getElementById(`ovr-badge-${resIdx}-${comp}`);
                const noteEl = document.getElementById(`ovr-note-${resIdx}-${comp}`);
                const badge = (badgeEl && badgeEl.value.trim()) || (state.currentUser ? state.currentUser.badge : 'LEAD-104');
                const note = (noteEl && noteEl.value.trim()) || '';
                const role = state.currentUser ? state.currentUser.role : 'SUPERVISOR';

                if (!note) {
                    showAlert('ISO 9001 Compliance: An engineering rationale is required when overriding a machine defect to PASS.', 'warning');
                    if (noteEl) noteEl.focus();
                    return;
                }

                if (!canOverrideDefects()) {
                    showAlert('Unauthorized: Defect overrides require SMT Supervisor or QA Admin authorization.', 'danger');
                    return;
                }

                // Sync to backend
                if (state.sessionId) {
                    try {
                        const resp = await fetch(`/api/sessions/${state.sessionId}/signoff`, {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                filename: fname,
                                component_name: comp,
                                final_status: 'PRESENT',
                                operator_id: badge,
                                operator_role: role,
                                note: note,
                            }),
                        });
                        if (!resp.ok) {
                            const errData = await resp.json().catch(() => ({}));
                            throw new Error(errData.detail || 'Override failed');
                        }
                    } catch (err) {
                        showAlert(`Override rejected: ${err.message}`, 'danger');
                        return;
                    }
                }

                if (!state.signoffs[fname]) state.signoffs[fname] = {};
                state.signoffs[fname][comp] = {
                    final_status: 'PRESENT',
                    operator_id: badge,
                    operator_role: role,
                    note: note,
                    timestamp: new Date().toLocaleTimeString(),
                };

                showAlert(`Defect override recorded: ${comp} dispositioned as PASS by ${badge} (${role}).`, 'success');
                renderResultCards();
                updateBatchSummary();
            });
        });

        // Edit / Revert Sign-Off
        el.resultsCardsContainer.querySelectorAll('.btn-edit-signoff').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const target = e.currentTarget;
                const fname = target.getAttribute('data-fname');
                const comp = target.getAttribute('data-comp');
                if (state.signoffs[fname] && state.signoffs[fname][comp]) {
                    delete state.signoffs[fname][comp];
                    renderResultCards();
                    updateBatchSummary();
                }
            });
        });
    }

    function updateBatchSummary() {
        if (!state.lastInspectionData || !state.lastInspectionData.results) return;
        const results = state.lastInspectionData.results;
        const total = results.length;

        let machineOk = 0, machineDefect = 0, machineReview = 0;
        let finalOk = 0, finalDefect = 0, finalReview = 0;
        const defectCounts = {};

        results.forEach(res => {
            const mStatus = res.board_status;
            if (mStatus === 'OK') machineOk++;
            else if (mStatus === 'DEFECT') machineDefect++;
            else if (mStatus === 'REVIEW') machineReview++;

            const bSign = state.signoffs[res.filename] || {};
            let bHasDefect = false;
            let bHasUncertain = false;

            res.components.forEach(c => {
                const sign = bSign[c.name];
                const effectiveStatus = sign ? sign.final_status : c.status;
                if (['MISSING', 'TILTED', 'MISALIGNED'].includes(effectiveStatus)) {
                    bHasDefect = true;
                    const defectKey = `${c.name} (${effectiveStatus.toLowerCase()})`;
                    defectCounts[defectKey] = (defectCounts[defectKey] || 0) + 1;
                } else if (effectiveStatus === 'UNCERTAIN') {
                    bHasUncertain = true;
                }
            });

            if (bHasDefect) finalDefect++;
            else if (bHasUncertain) finalReview++;
            else finalOk++;
        });

        const fpy = total > 0 ? ((machineOk / total) * 100).toFixed(1) : '0.0';
        const finalYield = total > 0 ? ((finalOk / total) * 100).toFixed(1) : '0.0';

        if (el.kpiTotal) el.kpiTotal.textContent = total;
        if (el.kpiOk) el.kpiOk.textContent = machineOk;
        if (el.kpiDefect) el.kpiDefect.textContent = machineDefect;
        if (el.kpiReview) el.kpiReview.textContent = machineReview;
        if (el.kpiFpy) el.kpiFpy.textContent = `${fpy}%`;
        if (el.kpiFinalYield) el.kpiFinalYield.textContent = `${finalYield}%`;

        // Defect Pareto tally
        if (el.defectTallyList) {
            el.defectTallyList.innerHTML = '';
            const sortedDefects = Object.keys(defectCounts).sort((a, b) => defectCounts[b] - defectCounts[a]);
            if (sortedDefects.length === 0) {
                el.defectTallyList.innerHTML = '<span class="text-muted">No defects (missing/tilted/misaligned) reported in this batch.</span>';
            } else {
                sortedDefects.forEach(key => {
                    const chip = document.createElement('span');
                    chip.className = 'defect-chip';
                    chip.textContent = `${key}: ${defectCounts[key]} defect(s)`;
                    el.defectTallyList.appendChild(chip);
                });
            }
        }
    }

    // --- CSV EXPORT ---
    function downloadCsvReport() {
        if (!state.lastInspectionData || !state.lastInspectionData.results) {
            showAlert('No inspection results available to export.', 'danger');
            return;
        }

        const results = state.lastInspectionData.results;
        const rows = [
            ['Timestamp', 'Board_Filename', 'Board_Machine_Status', 'Board_Final_Status', 'Component', 'Machine_Status', 'Final_Status', 'ZNCC_Score', 'Patch_Diff', 'Tilt_Deg', 'Shift_Px', 'Operator_ID', 'Operator_Note', 'Diagnostic_Reason']
        ];

        const ts = new Date().toISOString();
        results.forEach(res => {
            const bSign = state.signoffs[res.filename] || {};
            let bHasDefect = false, bHasUncertain = false;
            res.components.forEach(c => {
                const sign = bSign[c.name];
                const eff = sign ? sign.final_status : c.status;
                if (['MISSING', 'TILTED', 'MISALIGNED'].includes(eff)) bHasDefect = true;
                else if (eff === 'UNCERTAIN') bHasUncertain = true;
            });
            const finalBStatus = bHasDefect ? 'DEFECT' : (bHasUncertain ? 'REVIEW' : 'OK');

            res.components.forEach(c => {
                const sign = bSign[c.name] || {};
                const eff = sign.final_status || c.status;
                const tiltVal = (c.scores && c.scores.tilt_deg !== undefined) ? c.scores.tilt_deg.toFixed(2) : '0.00';
                const shiftVal = (c.scores && c.scores.shift_dist_px !== undefined) ? c.scores.shift_dist_px.toFixed(2) : '0.00';
                rows.push([
                    ts,
                    res.filename,
                    res.board_status,
                    finalBStatus,
                    c.name,
                    c.status,
                    eff,
                    c.scores.zncc.toFixed(4),
                    c.scores.patch_diff.toFixed(4),
                    tiltVal,
                    shiftVal,
                    sign.operator_id || '',
                    sign.note || '',
                    `"${(c.reason || '').replace(/"/g, '""')}"`
                ]);
            });
        });

        const csvContent = rows.map(r => r.join(',')).join('\n');
        const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `aoi_batch_report_${Date.now()}.csv`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);
    }

    if (el.btnDownloadCsv) {
        el.btnDownloadCsv.addEventListener('click', downloadCsvReport);
    }

    if (el.toggleViewCarousel) {
        el.toggleViewCarousel.addEventListener('click', () => {
            state.resultsViewMode = 'carousel';
            if (el.toggleViewCarousel) el.toggleViewCarousel.classList.add('active');
            if (el.toggleViewStacked) el.toggleViewStacked.classList.remove('active');
            renderResultCards();
        });
    }

    if (el.toggleViewStacked) {
        el.toggleViewStacked.addEventListener('click', () => {
            state.resultsViewMode = 'stacked';
            if (el.toggleViewStacked) el.toggleViewStacked.classList.add('active');
            if (el.toggleViewCarousel) el.toggleViewCarousel.classList.remove('active');
            renderResultCards();
        });
    }

    // --- ESCAPE HTML HELPER ---
    function escapeHtml(str) {
        if (str === null || str === undefined) return '';
        return String(str).replace(/[&<>"']/g, s => ({
            '&': '&amp;',
            '<': '&lt;',
            '>': '&gt;',
            '"': '&quot;',
            "'": '&#39;'
        }[s]));
    }

    // --- PRINTABLE INSPECTION REPORT ---
    function openPrintableReport() {
        if (!state.lastInspectionData || !state.lastInspectionData.results) {
            showAlert('No inspection data available for printing. Please run inspection first.', 'danger');
            return;
        }

        const data = state.lastInspectionData;
        const results = data.results;
        const total = results.length;

        let machineOk = 0, finalOk = 0;
        let totalComponents = 0;
        let totalDefects = 0;
        const defectBreakdown = {
            MISSING: 0,
            TILTED: 0,
            MISALIGNED: 0,
            BRIDGED: 0,
            POLARITY_REVERSED: 0,
            TOMBSTONED: 0,
            UNCERTAIN: 0
        };

        const defectItems = [];
        const boardSummaries = [];
        let fullTelemetryRows = '';

        results.forEach((res, rIdx) => {
            if (res.board_status === 'OK') machineOk++;
            const bSign = state.signoffs[res.filename] || {};
            let hasDefect = false, hasUnc = false;
            let bDefectCount = 0;
            const bDefectNames = [];
            let totalZncc = 0;

            res.components.forEach(c => {
                totalComponents++;
                const sign = bSign[c.name];
                const eff = sign ? sign.final_status : c.status;
                const znccScore = c.scores && c.scores.zncc !== undefined ? c.scores.zncc : 1.0;
                totalZncc += znccScore;

                if (['MISSING', 'TILTED', 'MISALIGNED', 'BRIDGED', 'POLARITY_REVERSED', 'TOMBSTONED'].includes(eff)) {
                    hasDefect = true;
                    bDefectCount++;
                    totalDefects++;
                    if (defectBreakdown[eff] !== undefined) defectBreakdown[eff]++;
                    bDefectNames.push(`${c.name} (${eff})`);

                    defectItems.push({
                        boardIdx: rIdx + 1,
                        filename: res.filename,
                        component: c.name,
                        defectType: eff,
                        zncc: znccScore,
                        tilt: c.scores ? c.scores.tilt_deg : 0,
                        shift: c.scores ? c.scores.shift_dist_px : 0,
                        reason: c.reason || 'Surface/geometry anomaly detected',
                        signText: sign ? `${sign.final_status} (by ${sign.operator_id}${sign.note ? ': ' + sign.note : ''})` : 'Pending disposition'
                    });
                } else if (eff === 'UNCERTAIN') {
                    hasUnc = true;
                    defectBreakdown.UNCERTAIN++;
                }

                // Badges for table
                let verdictBadgeClass = 'print-badge-pass';
                if (['MISSING', 'TILTED', 'MISALIGNED', 'BRIDGED', 'POLARITY_REVERSED', 'TOMBSTONED'].includes(c.status)) {
                    verdictBadgeClass = 'print-badge-defect';
                } else if (c.status === 'UNCERTAIN') {
                    verdictBadgeClass = 'print-badge-review';
                }

                let finalBadgeClass = 'print-badge-pass';
                if (['MISSING', 'TILTED', 'MISALIGNED', 'BRIDGED', 'POLARITY_REVERSED', 'TOMBSTONED'].includes(eff)) {
                    finalBadgeClass = 'print-badge-defect';
                } else if (eff === 'UNCERTAIN') {
                    finalBadgeClass = 'print-badge-review';
                }

                const signText = sign ? `${sign.final_status} [${sign.operator_id}${sign.note ? ': ' + sign.note : ''}]` : 'Auto-Verified';
                const signBadgeClass = sign ? 'print-badge-signoff' : '';
                const tiltStr = (c.scores && c.scores.tilt_deg !== undefined) ? (c.scores.tilt_deg > 0 ? `+${c.scores.tilt_deg.toFixed(1)}°` : `${c.scores.tilt_deg.toFixed(1)}°`) : '0.0°';
                const shiftStr = (c.scores && c.scores.shift_dist_px !== undefined) ? `${c.scores.shift_dist_px.toFixed(1)}px` : '0.0px';
                const isDefectRow = ['MISSING', 'TILTED', 'MISALIGNED', 'BRIDGED', 'POLARITY_REVERSED', 'TOMBSTONED'].includes(eff);

                fullTelemetryRows += `
                    <tr class="${isDefectRow ? 'print-table-row-defect' : ''}">
                        <td class="print-filename">${escapeHtml(res.filename)}</td>
                        <td><strong>${escapeHtml(c.name)}</strong></td>
                        <td><span class="print-badge ${verdictBadgeClass}">${c.status}</span></td>
                        <td><span class="print-badge ${finalBadgeClass}">${eff}</span></td>
                        <td class="print-mono">${znccScore.toFixed(4)}</td>
                        <td class="print-mono">${tiltStr}</td>
                        <td class="print-mono">${shiftStr}</td>
                        <td><span class="${signBadgeClass ? 'print-badge ' + signBadgeClass : ''}" style="font-size:0.68rem;">${escapeHtml(signText)}</span></td>
                    </tr>
                `;
            });

            if (!hasDefect && !hasUnc) finalOk++;
            const finalBStatus = hasDefect ? 'DEFECT' : (hasUnc ? 'REVIEW' : 'OK');
            const avgZncc = res.components.length > 0 ? (totalZncc / res.components.length).toFixed(3) : '1.000';

            boardSummaries.push({
                boardIdx: rIdx + 1,
                filename: res.filename,
                coverage: `${res.components.length}/${res.components.length}`,
                machineStatus: res.board_status,
                finalStatus: finalBStatus,
                defectCount: bDefectCount,
                defectsText: bDefectNames.length > 0 ? bDefectNames.join(', ') : 'None (Zero Defect)',
                avgZncc: avgZncc
            });
        });

        const fpy = total > 0 ? ((machineOk / total) * 100).toFixed(1) : '0.0';
        const finalY = total > 0 ? ((finalOk / total) * 100).toFixed(1) : '0.0';
        const fpyClass = parseFloat(fpy) >= 95.0 ? 'text-green' : (parseFloat(fpy) >= 80.0 ? '' : 'text-red');
        const finalClass = parseFloat(finalY) >= 95.0 ? 'text-green' : (parseFloat(finalY) >= 80.0 ? '' : 'text-red');

        const isBatchClean = totalDefects === 0 && finalOk === total;
        const batchBadgeClass = isBatchClean ? 'badge-sheet-pass' : 'badge-sheet-defect';
        const batchVerdictLabel = isBatchClean 
            ? 'BATCH ACCEPTED — ZERO DEFECTS' 
            : `CRITICAL ANOMALIES DETECTED — ${totalDefects} DEFECT(S) RECORDED`;

        const leadName = state.currentUser ? state.currentUser.name : 'Sarah Jenkins';
        const leadBadge = state.currentUser ? state.currentUser.badge : 'OP-8402';
        const leadRole = state.currentUser ? state.currentUser.role : 'Lead QA Inspector';

        // Defect breakdown chips
        const breakdownParts = [];
        if (defectBreakdown.MISSING > 0) breakdownParts.push(`Missing: ${defectBreakdown.MISSING}`);
        if (defectBreakdown.TILTED > 0) breakdownParts.push(`Tilted: ${defectBreakdown.TILTED}`);
        if (defectBreakdown.MISALIGNED > 0) breakdownParts.push(`Misaligned: ${defectBreakdown.MISALIGNED}`);
        if (defectBreakdown.BRIDGED > 0) breakdownParts.push(`Bridged: ${defectBreakdown.BRIDGED}`);
        if (defectBreakdown.POLARITY_REVERSED > 0) breakdownParts.push(`Rev Polarity: ${defectBreakdown.POLARITY_REVERSED}`);
        if (defectBreakdown.TOMBSTONED > 0) breakdownParts.push(`Tombstoned: ${defectBreakdown.TOMBSTONED}`);
        const defectBreakdownText = breakdownParts.length > 0 ? breakdownParts.join(' &bull; ') : 'All footprints within tolerance';

        // Board summary rows
        const boardSummaryRows = boardSummaries.map(b => {
            const mBadge = b.machineStatus === 'OK' ? 'print-badge-pass' : 'print-badge-defect';
            const fBadge = b.finalStatus === 'OK' ? 'print-badge-pass' : (b.finalStatus === 'REVIEW' ? 'print-badge-review' : 'print-badge-defect');
            return `
                <tr class="${b.defectCount > 0 ? 'print-table-row-defect' : ''}">
                    <td style="text-align:center; font-weight:700;">#${b.boardIdx}</td>
                    <td class="print-filename">${escapeHtml(b.filename)}</td>
                    <td style="text-align:center;">${b.coverage}</td>
                    <td><span class="print-badge ${mBadge}">${b.machineStatus}</span></td>
                    <td><span class="print-badge ${fBadge}">${b.finalStatus}</span></td>
                    <td style="font-size:0.72rem; ${b.defectCount > 0 ? 'color:#b91c1c; font-weight:600;' : 'color:#15803d;'}">${escapeHtml(b.defectsText)}</td>
                </tr>
            `;
        }).join('');

        // Defect Exception Log Section HTML
        let defectLogSectionHtml = '';
        if (defectItems.length > 0) {
            const defectRows = defectItems.map(d => {
                const tiltStr = d.tilt ? (d.tilt > 0 ? `+${d.tilt.toFixed(1)}°` : `${d.tilt.toFixed(1)}°`) : '0.0°';
                const shiftStr = d.shift ? `${d.shift.toFixed(1)}px` : '0.0px';
                return `
                    <tr class="print-table-row-defect">
                        <td style="text-align:center; font-weight:700;">#${d.boardIdx}</td>
                        <td class="print-filename">${escapeHtml(d.filename)}</td>
                        <td><strong>${escapeHtml(d.component)}</strong></td>
                        <td><span class="print-badge print-badge-defect">${d.defectType}</span></td>
                        <td class="print-mono">${d.zncc.toFixed(4)}</td>
                        <td class="print-mono">${tiltStr} / ${shiftStr}</td>
                        <td style="font-size:0.72rem; color:#7f1d1d;">${escapeHtml(d.reason)}</td>
                        <td><span class="print-badge print-badge-signoff">${escapeHtml(d.signText)}</span></td>
                    </tr>
                `;
            }).join('');

            defectLogSectionHtml = `
                <div class="sheet-section">
                    <div class="sheet-section-header" style="border-bottom-color:#f87171;">
                        <h3 style="color:#b91c1c;">2. Critical Component Defect &amp; Exception Log</h3>
                        <span class="sheet-section-count" style="color:#b91c1c; font-weight:700;">${defectItems.length} Defect(s) Flagged</span>
                    </div>
                    <table class="print-table defect-log-table">
                        <thead>
                            <tr>
                                <th style="width: 5%;">Unit</th>
                                <th style="width: 25%;">Board Filename</th>
                                <th style="width: 14%;">Component ID</th>
                                <th style="width: 11%;">Defect Mode</th>
                                <th style="width: 9%;">ZNCC</th>
                                <th style="width: 9%;">Tilt / Shift</th>
                                <th style="width: 15%;">Failure Root Cause</th>
                                <th style="width: 12%;">Sign-Off Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${defectRows}
                        </tbody>
                    </table>
                </div>
            `;
        } else {
            defectLogSectionHtml = `
                <div class="sheet-section">
                    <div class="sheet-section-header" style="border-bottom-color:#86efac;">
                        <h3 style="color:#15803d;">2. Critical Component Defect &amp; Exception Log</h3>
                        <span class="sheet-section-count" style="color:#15803d; font-weight:700;">Zero Defects Detected</span>
                    </div>
                    <div style="background:#f0fdf4; border:1px solid #bbf7d0; border-radius:4px; padding:0.65rem 0.9rem; font-size:0.78rem; color:#166534;">
                        <strong>Pass Attestation:</strong> 100% of component footprints across all ${total} production board(s) matched registered golden reference criteria with zero missing parts, solder bridges, or angular misalignments.
                    </div>
                </div>
            `;
        }

        el.printableReportContent.innerHTML = `
            <div class="sheet-container">
                <!-- 1. CERTIFICATE HEADER -->
                <div class="sheet-header">
                    <div class="sheet-brand-group">
                        <div class="sheet-brand-top">
                            <span class="sheet-facility-tag">SMT LINE 01 &bull; AOI CELL #4</span>
                            <span class="sheet-standard-tag">IPC-A-610 CLASS 2/3 COMPLIANCE</span>
                        </div>
                        <h1 class="sheet-title">PCB AUTOMATED OPTICAL INSPECTION QUALITY SHEET</h1>
                        <p class="sheet-sub">Official Computer Vision Inspection Audit &amp; Hardware Disposition Certificate</p>
                    </div>
                    <div class="sheet-meta-group">
                        <div class="sheet-meta-pill ${batchBadgeClass}">
                            <span class="sheet-meta-pill-dot"></span>
                            <strong>${batchVerdictLabel}</strong>
                        </div>
                        <table class="sheet-meta-table">
                            <tr><th>Audit Date:</th><td>${new Date().toLocaleString()}</td></tr>
                            <tr><th>Session ID:</th><td><code>${(state.sessionId || 'N/A').slice(0, 18)}...</code></td></tr>
                            <tr><th>Certified Lead:</th><td>${escapeHtml(leadName)} (<code>${escapeHtml(leadBadge)}</code>)</td></tr>
                        </table>
                    </div>
                </div>

                <!-- 2. EXECUTIVE QUALITY METRIC CARDS -->
                <div class="sheet-kpi-grid">
                    <div class="sheet-kpi-card">
                        <div class="sheet-kpi-label">BOARDS AUDITED</div>
                        <div class="sheet-kpi-val">${total} <span class="sheet-kpi-unit">Units</span></div>
                        <div class="sheet-kpi-sub">Total Parts: ${totalComponents}</div>
                    </div>
                    <div class="sheet-kpi-card">
                        <div class="sheet-kpi-label">FIRST-PASS YIELD</div>
                        <div class="sheet-kpi-val ${fpyClass}">${fpy}%</div>
                        <div class="sheet-kpi-bar-wrap"><div class="sheet-kpi-bar" style="width:${Math.min(100, Math.max(0, parseFloat(fpy)))}%;"></div></div>
                        <div class="sheet-kpi-sub">${machineOk} of ${total} Machine OK</div>
                    </div>
                    <div class="sheet-kpi-card">
                        <div class="sheet-kpi-label">FINAL RELEASE YIELD</div>
                        <div class="sheet-kpi-val ${finalClass}">${finalY}%</div>
                        <div class="sheet-kpi-bar-wrap"><div class="sheet-kpi-bar sheet-kpi-bar-green" style="width:${Math.min(100, Math.max(0, parseFloat(finalY)))}%;"></div></div>
                        <div class="sheet-kpi-sub">${finalOk} of ${total} Cleared</div>
                    </div>
                    <div class="sheet-kpi-card">
                        <div class="sheet-kpi-label">DEFECT INCIDENCE</div>
                        <div class="sheet-kpi-val ${totalDefects > 0 ? 'text-red' : 'text-green'}">${totalDefects}</div>
                        <div class="sheet-kpi-sub">${defectBreakdownText}</div>
                    </div>
                    <div class="sheet-kpi-card">
                        <div class="sheet-kpi-label">INSPECTION SENSITIVITY</div>
                        <div class="sheet-kpi-val" style="font-size:1.1rem;">${state.activeSensitivity.toUpperCase()}</div>
                        <div class="sheet-kpi-sub">Homography + ZNCC Multi-Scale</div>
                    </div>
                </div>

                <!-- 3. SECTION 1: PRODUCTION BATCH BOARD OVERVIEW -->
                <div class="sheet-section">
                    <div class="sheet-section-header">
                        <h3>1. Batch Production Summary (Board-Level Traceability)</h3>
                        <span class="sheet-section-count">${results.length} Production Units Audited</span>
                    </div>
                    <table class="print-table board-summary-table">
                        <thead>
                            <tr>
                                <th style="width: 6%;">Unit</th>
                                <th style="width: 32%;">Board Filename</th>
                                <th style="width: 12%;">Coverage</th>
                                <th style="width: 14%;">Machine Verdict</th>
                                <th style="width: 14%;">Final Disposition</th>
                                <th style="width: 22%;">Detected Anomalies</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${boardSummaryRows}
                        </tbody>
                    </table>
                </div>

                <!-- 4. SECTION 2: DEFECT & ANOMALY EXCEPTION LOG -->
                ${defectLogSectionHtml}

                <!-- 5. SECTION 3: COMPREHENSIVE COMPONENT-LEVEL TELEMETRY -->
                <div class="sheet-section">
                    <div class="sheet-section-header">
                        <h3>3. Component Inspection Telemetry (Full Traceability Log)</h3>
                        <span class="sheet-section-count">${totalComponents} Footprints Evaluated</span>
                    </div>
                    <table class="print-table full-telemetry-table">
                        <thead>
                            <tr>
                                <th style="width: 23%;">Board Filename</th>
                                <th style="width: 15%;">Component ID</th>
                                <th style="width: 12%;">Machine Verdict</th>
                                <th style="width: 12%;">Final Verdict</th>
                                <th style="width: 9%;">ZNCC</th>
                                <th style="width: 7%;">Tilt (°)</th>
                                <th style="width: 7%;">Shift (px)</th>
                                <th style="width: 15%;">Operator Action</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${fullTelemetryRows}
                        </tbody>
                    </table>
                </div>

                <!-- 6. FORMAL AUDIT SIGN-OFF & IPC COMPLIANCE BLOCK -->
                <div class="sheet-signoff-block">
                    <div class="sheet-signoff-grid">
                        <div class="sheet-signoff-card">
                            <div class="sheet-signoff-title">CERTIFIED OPTICAL INSPECTOR</div>
                            <div class="sheet-signoff-body">
                                <p><strong>Name:</strong> ${escapeHtml(leadName)}</p>
                                <p><strong>Badge ID:</strong> <code>${escapeHtml(leadBadge)}</code> &bull; ${escapeHtml(leadRole)}</p>
                                <div class="sheet-signature-line">
                                    <span>Inspector Signature</span>
                                    <span>Date: ${new Date().toISOString().slice(0, 10)}</span>
                                </div>
                            </div>
                        </div>
                        <div class="sheet-signoff-card">
                            <div class="sheet-signoff-title">QUALITY ASSURANCE VERIFICATION</div>
                            <div class="sheet-signoff-body">
                                <div class="sheet-qa-stamp-box">
                                    <div class="sheet-qa-stamp-title">QA LOT ACCEPTANCE</div>
                                    <div class="sheet-qa-stamp-row">
                                        <span>[ ${finalOk === total ? '&#x2714;' : '&nbsp;&nbsp;'} ] ACCEPTED</span>
                                        <span>[ ${finalOk < total ? '&#x2714;' : '&nbsp;&nbsp;'} ] REWORK HOLD</span>
                                    </div>
                                    <div class="sheet-qa-stamp-date">Date: ${new Date().toISOString().slice(0, 10)}</div>
                                </div>
                                <div class="sheet-signature-line">
                                    <span>Quality Lead Signature</span>
                                </div>
                            </div>
                        </div>
                        <div class="sheet-signoff-card">
                            <div class="sheet-signoff-title">IPC-A-610 REGULATORY ATTESTATION</div>
                            <div class="sheet-signoff-body" style="font-size:0.73rem; color:#475569; line-height:1.45;">
                                <p>This automated optical inspection quality report certifies that the PCB batch listed above was evaluated against registered golden reference CAD/optical criteria.</p>
                                <p style="margin-top:0.4rem;">All surface mount devices (SMD) and through-hole components (THD) were verified for presence, solder bridging, angular skew (&lt;3.5°), and dimensional translation (&lt;5.0px) under IPC-A-610 Rev H standards.</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;

        document.body.classList.add('report-modal-open');
        el.printModal.classList.remove('d-none');
    }

    function closePrintableReport() {
        if (el.printModal) el.printModal.classList.add('d-none');
        document.body.classList.remove('report-modal-open');
    }

    // Expose openPrintableReport globally
    window.openPrintableReport = openPrintableReport;
    window.closePrintableReport = closePrintableReport;

    if (el.btnPrintReport) {
        el.btnPrintReport.addEventListener('click', openPrintableReport);
    }
    if (el.btnTriggerPrint) {
        el.btnTriggerPrint.addEventListener('click', () => window.print());
    }
    if (el.btnClosePrint) {
        el.btnClosePrint.addEventListener('click', closePrintableReport);
    }

    function drawResultCanvas(canvasId, result) {
        const canvas = document.getElementById(canvasId);
        if (!canvas) return;

        // Find the original File object for this result
        const fileObj = state.testFiles.find(f => f.name === result.filename);
        if (!fileObj) return;

        const img = new Image();
        img.onload = () => {
            canvas.width = state.workingDim.width;
            canvas.height = state.workingDim.height;
            const ctx = canvas.getContext('2d');

            // Draw test image
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

            // Overlay colored component boxes
            result.components.forEach(comp => {
                const [x, y, w, h] = comp.box.pixel;

                let color = '#2ea043'; // Green for PRESENT
                let fillColor = 'rgba(46, 160, 67, 0.15)';
                let tagText = `${comp.name} [OK]`;

                if (comp.status === 'MISSING') {
                    color = '#f85149'; // Red for MISSING
                    fillColor = 'rgba(248, 81, 73, 0.35)';
                    tagText = `${comp.name} [MISSING]`;
                } else if (comp.status === 'TILTED') {
                    color = '#f0883e'; // Orange for TILTED
                    fillColor = 'rgba(240, 136, 62, 0.35)';
                    const tDeg = (comp.scores && comp.scores.tilt_deg !== undefined) ? (comp.scores.tilt_deg > 0 ? `+${comp.scores.tilt_deg}°` : `${comp.scores.tilt_deg}°`) : '';
                    tagText = `${comp.name} [TILT ${tDeg}]`;
                } else if (comp.status === 'MISALIGNED') {
                    color = '#a371f7'; // Purple for MISALIGNED
                    fillColor = 'rgba(163, 113, 247, 0.35)';
                    const sDist = (comp.scores && comp.scores.shift_dist_px !== undefined) ? `${comp.scores.shift_dist_px}px` : '';
                    tagText = `${comp.name} [SHIFT ${sDist}]`;
                } else if (comp.status === 'BRIDGED') {
                    color = '#d2a8ff'; // Light purple/magenta for BRIDGED
                    fillColor = 'rgba(210, 168, 255, 0.35)';
                    tagText = `${comp.name} [BRIDGED]`;
                } else if (comp.status === 'POLARITY_REVERSED') {
                    color = '#38bdf8'; // Sky cyan for POLARITY_REVERSED
                    fillColor = 'rgba(56, 189, 248, 0.35)';
                    tagText = `${comp.name} [REV POLARITY]`;
                } else if (comp.status === 'TOMBSTONED') {
                    color = '#fb923c'; // Vivid orange for TOMBSTONED
                    fillColor = 'rgba(251, 146, 60, 0.35)';
                    tagText = `${comp.name} [TOMBSTONED]`;
                } else if (comp.status === 'UNCERTAIN') {
                    color = '#e3b341'; // Amber for UNCERTAIN
                    fillColor = 'rgba(227, 179, 65, 0.25)';
                    tagText = `${comp.name} [UNCERTAIN]`;
                }

                // Draw bounding contour (polygon if defined, else rectangle)
                if (comp.polygon && comp.polygon.length >= 3) {
                    ctx.save();
                    ctx.beginPath();
                    ctx.moveTo(comp.polygon[0][0], comp.polygon[0][1]);
                    for (let i = 1; i < comp.polygon.length; i++) {
                        ctx.lineTo(comp.polygon[i][0], comp.polygon[i][1]);
                    }
                    ctx.closePath();
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 3.5;
                    ctx.stroke();
                    ctx.fillStyle = fillColor;
                    ctx.fill();
                    ctx.restore();
                } else {
                    ctx.strokeStyle = color;
                    ctx.lineWidth = 4;
                    ctx.strokeRect(x, y, w, h);
                    ctx.fillStyle = fillColor;
                    ctx.fillRect(x, y, w, h);
                }

                // Draw solid label pill
                ctx.font = 'bold 15px -apple-system, sans-serif';
                const textWidth = ctx.measureText(tagText).width;
                ctx.fillStyle = color;
                ctx.fillRect(x, Math.max(0, y - 24), textWidth + 12, 24);

                ctx.fillStyle = '#ffffff';
                ctx.fillText(tagText, x + 6, Math.max(16, y - 7));
            });
        };
        img.src = URL.createObjectURL(fileObj);
    }

    // --- WORKSPACE 1: DIGITAL MICROSCOPE LOUPE (3X ZOOM) ---
    function attachMicroscopeLoupeHandlers() {
        document.querySelectorAll('.clickable-comp-row').forEach(row => {
            row.addEventListener('click', (e) => {
                if (e.target.closest('.signoff-box') || e.target.closest('.btn-signoff') || e.target.closest('.btn-edit-signoff') || e.target.closest('input')) {
                    return;
                }
                const resIdx = row.getAttribute('data-res-idx');
                const compName = row.getAttribute('data-comp-name');
                const res = state.lastInspectionData.results[resIdx];
                const comp = res ? res.components.find(c => c.name === compName) : null;
                if (res && comp) {
                    focusViewportOnComponent(comp.box ? comp.box.pixel : null);
                    openMicroscopeLoupe(res, comp, resIdx);
                }
            });
        });
    }

    function focusViewportOnComponent(compBbox) {
        if (!compBbox) return;
        const [x, y, w, h] = compBbox;
        const cx = x + w / 2;
        const cy = y + h / 2;
        const xPct = Math.max(0, Math.min(100, (cx / state.workingDim.width) * 100));
        const yPct = Math.max(0, Math.min(100, (cy / state.workingDim.height) * 100));

        ['frame-carousel-ref', 'frame-carousel-test'].forEach(id => {
            const frame = document.getElementById(id);
            if (frame) {
                frame.classList.add('is-zoomed');
                const canvas = frame.querySelector('canvas');
                if (canvas) {
                    canvas.style.transformOrigin = `${xPct}% ${yPct}%`;
                }
            }
        });
        const zRef = document.getElementById('btn-zoom-ref');
        const zTest = document.getElementById('btn-zoom-test');
        if (zRef) {
            zRef.classList.add('active');
            zRef.innerHTML = `<svg class="ui-icon" style="width:12px;height:12px;"><use href="#icon-loupe"></use></svg> Reset Zoom`;
        }
        if (zTest) {
            zTest.classList.add('active');
            zTest.innerHTML = `<svg class="ui-icon" style="width:12px;height:12px;"><use href="#icon-loupe"></use></svg> Reset Zoom`;
        }
    }

    function openMicroscopeLoupe(res, comp, resIdx) {
        const loupeContainer = document.getElementById(`loupe-container-${resIdx}`);
        if (!loupeContainer) return;

        loupeContainer.classList.remove('d-none');
        const box = comp.box ? comp.box.pixel : [0, 0, 50, 50];
        const [bx, by, bw, bh] = box;

        let badgeClass = 'badge-success';
        if (comp.status === 'MISSING') badgeClass = 'badge-danger';
        else if (comp.status === 'TILTED') badgeClass = 'badge-tilted';
        else if (comp.status === 'MISALIGNED') badgeClass = 'badge-misaligned';
        else if (comp.status === 'BRIDGED') badgeClass = 'badge-bridged';
        else if (comp.status === 'POLARITY_REVERSED') badgeClass = 'badge-polarity';
        else if (comp.status === 'TOMBSTONED') badgeClass = 'badge-tombstoned';
        else if (comp.status === 'UNCERTAIN') badgeClass = 'badge-amber';

        const znccStr = comp.scores && comp.scores.zncc !== undefined ? comp.scores.zncc.toFixed(3) : 'N/A';
        const diffStr = comp.scores && comp.scores.patch_diff !== undefined ? comp.scores.patch_diff.toFixed(3) : 'N/A';
        const tiltStr = comp.scores && comp.scores.tilt_deg !== undefined ? `${comp.scores.tilt_deg > 0 ? '+' : ''}${comp.scores.tilt_deg.toFixed(1)}°` : '0.0°';
        const shiftStr = comp.scores && comp.scores.shift_dist_px !== undefined ? `${comp.scores.shift_dist_px.toFixed(1)} px` : '0.0 px';

        loupeContainer.innerHTML = `
            <div class="loupe-header">
                <div class="loupe-header-title">
                    <svg class="ui-icon" style="width:18px;height:18px;color:var(--color-blue);"><use href="#icon-loupe"></use></svg>
                    <h4>Digital Microscope Loupe: ${comp.name}</h4>
                    <span class="badge ${badgeClass}">${comp.status}</span>
                </div>
                <button type="button" class="btn-xs-link btn-close-loupe" data-card="${resIdx}" style="color:var(--text-muted); font-size:0.85rem; cursor:pointer; text-decoration:none;">&times; Close Loupe</button>
            </div>

            <div class="loupe-crops-grid">
                <div class="loupe-crop-box">
                    <div class="loupe-crop-title">1. Golden Reference Crop</div>
                    <canvas id="loupe-crop-ref-${resIdx}" class="loupe-crop-canvas"></canvas>
                    <span style="font-size:0.7rem; color:var(--text-muted);">${bw}&times;${bh} px nominal template</span>
                </div>
                <div class="loupe-crop-box">
                    <div class="loupe-crop-title">2. Aligned Test Board Crop (3× Zoom)</div>
                    <canvas id="loupe-crop-test-${resIdx}" class="loupe-crop-canvas"></canvas>
                    <span style="font-size:0.7rem; color:var(--text-muted);">Inspected component ROI</span>
                </div>
                <div class="loupe-crop-box">
                    <div class="loupe-crop-title">3. Structural Difference Residual</div>
                    <canvas id="loupe-crop-diff-${resIdx}" class="loupe-crop-canvas"></canvas>
                    <span style="font-size:0.7rem; color:var(--text-muted);">Red pixel deviation heatmap</span>
                </div>
            </div>

            <div class="loupe-metrics-bar">
                <div class="loupe-metric-cell">
                    <span class="loupe-metric-label">ZNCC Similarity</span>
                    <span class="loupe-metric-val" style="color:${comp.status === 'MISSING' ? 'var(--color-red)' : 'var(--color-green-light)'};">${znccStr}</span>
                </div>
                <div class="loupe-metric-cell">
                    <span class="loupe-metric-label">Residual MAE Diff</span>
                    <span class="loupe-metric-val">${diffStr}</span>
                </div>
                <div class="loupe-metric-cell">
                    <span class="loupe-metric-label">Rotational Skew</span>
                    <span class="loupe-metric-val" style="color:${comp.status === 'TILTED' ? 'var(--color-amber)' : 'inherit'};">${tiltStr}</span>
                </div>
                <div class="loupe-metric-cell">
                    <span class="loupe-metric-label">Positional Shift</span>
                    <span class="loupe-metric-val" style="color:${comp.status === 'MISALIGNED' ? 'var(--color-blue)' : 'inherit'};">${shiftStr}</span>
                </div>
            </div>

            <div style="margin-top:0.75rem; font-size:0.83rem; color:var(--text-secondary); background:rgba(0,0,0,0.25); padding:0.5rem 0.75rem; border-radius:4px; border-left:3px solid var(--color-blue);">
                <strong>IPC-A-610 Diagnostic:</strong> ${comp.reason || 'Normal component footprint.'}
            </div>
        `;

        loupeContainer.querySelector('.btn-close-loupe').addEventListener('click', () => {
            loupeContainer.classList.add('d-none');
        });

        renderLoupeCrops(res, comp, resIdx, box);
        loupeContainer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }

    function renderLoupeCrops(res, comp, resIdx, box) {
        const [bx, by, bw, bh] = box;
        const refCanvas = document.getElementById(`loupe-crop-ref-${resIdx}`);
        const testCanvas = document.getElementById(`loupe-crop-test-${resIdx}`);
        const diffCanvas = document.getElementById(`loupe-crop-diff-${resIdx}`);

        if (!refCanvas || !testCanvas || !diffCanvas) return;

        refCanvas.width = bw;
        refCanvas.height = bh;
        testCanvas.width = bw;
        testCanvas.height = bh;
        diffCanvas.width = bw;
        diffCanvas.height = bh;

        const ctxR = refCanvas.getContext('2d');
        const ctxT = testCanvas.getContext('2d');
        const ctxD = diffCanvas.getContext('2d');

        if (state.referenceImg) {
            ctxR.drawImage(state.referenceImg, bx, by, bw, bh, 0, 0, bw, bh);
        }

        const fileObj = state.testFiles.find(f => f.name === res.filename) || state.testFiles[resIdx];
        if (fileObj) {
            const img = new Image();
            img.onload = () => {
                ctxT.drawImage(img, bx, by, bw, bh, 0, 0, bw, bh);

                try {
                    const rData = ctxR.getImageData(0, 0, bw, bh);
                    const tData = ctxT.getImageData(0, 0, bw, bh);
                    const dData = ctxD.createImageData(bw, bh);

                    for (let i = 0; i < rData.data.length; i += 4) {
                        const dr = Math.abs(rData.data[i] - tData.data[i]);
                        const dg = Math.abs(rData.data[i+1] - tData.data[i+1]);
                        const db = Math.abs(rData.data[i+2] - tData.data[i+2]);
                        const avgDiff = (dr + dg + db) / 3;

                        if (avgDiff > 25) {
                            dData.data[i] = Math.min(255, Math.floor(avgDiff * 2.8));
                            dData.data[i+1] = 30;
                            dData.data[i+2] = 30;
                            dData.data[i+3] = 255;
                        } else {
                            dData.data[i] = 15;
                            dData.data[i+1] = 20;
                            dData.data[i+2] = 30;
                            dData.data[i+3] = 255;
                        }
                    }
                    ctxD.putImageData(dData, 0, 0);
                } catch {}
            };
            img.src = URL.createObjectURL(fileObj);
        }
    }

    // --- WORKSPACE 4: BATCH ARCHIVE LOGGING ---
    function recordBatchInArchive(data) {
        if (!state.batchHistory) state.batchHistory = [];
        const batchId = 'BATCH-' + Math.floor(100000 + Math.random() * 900000);
        const bName = (state.activePreset && state.activePreset.name) || 'Custom PCB Board';
        let totalParts = 0, defects = 0;
        data.results.forEach(r => {
            totalParts += (r.components ? r.components.length : 0);
            if (r.board_status === 'DEFECT') defects++;
        });
        state.batchHistory.unshift({
            id: batchId,
            board: bName,
            time: new Date().toLocaleTimeString(),
            parts: totalParts,
            defects: defects,
            verdict: defects > 0 ? 'DEFECT' : 'OK',
            inspector: state.currentUser ? `${state.currentUser.name} (${state.currentUser.badge})` : 'Sarah Jenkins (OP-8402)'
        });
    }

    async function renderMonitoredBoardLogs() {
        // 1. Render batch audit history rows
        const tbody = document.getElementById('archive-table-body');
        if (tbody) {
            if (!state.batchHistory || state.batchHistory.length === 0) {
                state.batchHistory = [
                    { id: 'BATCH-841920', board: 'Arduino Uno R3 Physical MCU', time: '10:42 AM', parts: 82, defects: 3, verdict: 'DEFECT', inspector: 'Sarah Jenkins (OP-8402)' },
                    { id: 'BATCH-841919', board: 'Appliance AC Power Board', time: '10:15 AM', parts: 90, defects: 0, verdict: 'OK', inspector: 'Marcus Vance (OP-9104)' },
                    { id: 'BATCH-841918', board: 'Industrial PMS-63 Scale', time: '09:50 AM', parts: 75, defects: 2, verdict: 'DEFECT', inspector: 'Sarah Jenkins (OP-8402)' },
                    { id: 'BATCH-841917', board: 'Analog Instrumentation', time: '09:22 AM', parts: 64, defects: 0, verdict: 'OK', inspector: 'Dr. Elena Rostova (QM-001)' },
                ];
            }
            tbody.innerHTML = state.batchHistory.map(b => `
                <tr>
                    <td><strong>${b.id}</strong></td>
                    <td>${b.board}</td>
                    <td style="color:var(--text-muted);">${b.time}</td>
                    <td>${b.parts} parts</td>
                    <td>${b.defects > 0 ? `<span style="color:var(--color-red); font-weight:700;">${b.defects} defects</span>` : '<span style="color:var(--color-green-light);">0 defects</span>'}</td>
                    <td><span class="badge ${b.verdict === 'OK' ? 'badge-success' : 'badge-danger'}">${b.verdict}</span></td>
                    <td>${b.inspector}</td>
                    <td><button type="button" class="btn btn-xs btn-outline" onclick="window.openPrintableReport ? window.openPrintableReport() : window.print()">
                        <svg class="ui-icon btn-svg-icon"><use href="#icon-print"></use></svg> Quality Sheet
                    </button></td>
                </tr>
            `).join('');
        }

        // 2. Fetch and render Automated Optical Calibration baselines
        const calibCards = document.getElementById('auto-calib-cards-container');
        if (calibCards) {
            try {
                const res = await fetch('/api/calibration/profiles');
                const data = await res.json();
                const profiles = data.profiles || [];
                calibCards.innerHTML = profiles.map(p => `
                    <div class="auto-calib-card">
                        <div class="auto-calib-card-header">
                            <span class="auto-calib-card-title">${escapeHtml(p.name)}</span>
                            <span class="auto-calib-badge">${p.status}</span>
                        </div>
                        <div style="font-size:0.75rem; color:var(--text-muted); margin-bottom:0.35rem;">
                            <strong>${p.good_units_count} Good Units</strong> Monitored &bull; Normal Variance Learned
                        </div>
                        <div class="auto-calib-metrics">
                            <div class="auto-calib-metric-item">
                                <strong>Learned Skew Limit</strong>
                                <span class="auto-calib-metric-val">±${p.learned_max_tilt}°</span>
                            </div>
                            <div class="auto-calib-metric-item">
                                <strong>Learned Shift Limit</strong>
                                <span class="auto-calib-metric-val">${p.learned_max_shift} px</span>
                            </div>
                        </div>
                        <div class="auto-calib-foot-sub">
                            <span style="color:var(--color-blue); font-weight:600;">Automated Rule:</span> ${escapeHtml(p.human_review_rule)}
                        </div>
                    </div>
                `).join('');
            } catch (err) {
                console.warn('Could not fetch auto-calibration profiles', err);
            }
        }
    }

    const btnExportArchiveCsv = document.getElementById('btn-export-archive-csv');
    if (btnExportArchiveCsv) {
        btnExportArchiveCsv.addEventListener('click', () => {
            if (state.lastInspectionData && state.lastInspectionData.results) {
                downloadCsvReport();
            } else {
                const rows = [
                    ['Batch_ID', 'Board_Architecture', 'Timestamp', 'Parts_Inspected', 'Defects', 'Verdict', 'Lead_Inspector']
                ];
                (state.batchHistory || []).forEach(b => {
                    rows.push([b.id, `"${b.board}"`, b.time, b.parts, b.defects, b.verdict, `"${b.inspector}"`]);
                });
                const csv = rows.map(r => r.join(',')).join('\n');
                const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
                const url = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `monitored_board_logs_${Date.now()}.csv`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(url);
            }
        });
    }

    // --- MULTI-WORKSPACE NAVIGATION ---
    const workspaceLinks = document.querySelectorAll('.sidebar-link');
    const workspaces = document.querySelectorAll('.app-workspace');
    const sidebar = document.getElementById('app-sidebar');
    const btnToggleSidebar = document.getElementById('btn-toggle-sidebar');

    if (btnToggleSidebar && sidebar) {
        btnToggleSidebar.addEventListener('click', () => {
            sidebar.classList.toggle('collapsed');
        });
    }

    function switchWorkspace(targetId) {
        workspaceLinks.forEach(link => {
            if (link.getAttribute('data-workspace') === targetId) {
                link.classList.add('active');
            } else {
                link.classList.remove('active');
            }
        });
        workspaces.forEach(ws => {
            if (ws.id === targetId) {
                ws.classList.remove('d-none');
                ws.classList.add('active');
            } else {
                ws.classList.add('d-none');
                ws.classList.remove('active');
            }
        });

        // Trigger workspace specific updates
        if (targetId === 'workspace-recipe') renderStudioGrid();
        if (targetId === 'workspace-archive') renderMonitoredBoardLogs();
    }

    workspaceLinks.forEach(link => {
        link.addEventListener('click', (e) => {
            e.preventDefault();
            const targetId = link.getAttribute('data-workspace');
            if (targetId) switchWorkspace(targetId);
        });
    });

    // --- KEYBOARD SHORTCUTS ---
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (el.authModal && !el.authModal.classList.contains('d-none')) {
                el.authModal.classList.add('d-none');
            }
            if (el.cameraModal && !el.cameraModal.classList.contains('d-none')) {
                closeCameraModal();
            }
            if (el.printModal && !el.printModal.classList.contains('d-none')) {
                el.printModal.classList.add('d-none');
            }
            if (el.nameModal && !el.nameModal.classList.contains('d-none')) {
                el.nameModal.classList.add('d-none');
            }
        }
    });

    // --- RESET WORKFLOW ---
    el.btnReset.addEventListener('click', () => {
        if (confirm('Start over? This will clear current session annotations and test results.')) {
            state.sessionId = null;
            state.referenceFile = null;
            state.referenceImg = null;
            state.components = [];
            state.testFiles = [];
            state.activePreset = null;
            if (state.presets) renderPresets(state.presets);
            el.testFileList.innerHTML = '';
            el.resultsCardsContainer.innerHTML = '';
            el.inspectionResultsArea.classList.add('d-none');
            setStep(1);
        }
    });

    // --- INITIALIZE RBAC STATE ---
    updateOperatorHeader(state.currentUser);
    applyRBACPermissions();
});
