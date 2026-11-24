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
    function updateOperatorHeader(user) {
        if (!user) return;
        state.currentUser = user;
        if (el.headerOperatorName) el.headerOperatorName.textContent = user.name;
        if (el.headerOperatorBadge) el.headerOperatorBadge.textContent = `${user.badge} (${user.role})`;
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
                    <span style="font-size:1.2rem;">👤</span>
                    <div>
                        <div class="auth-profile-name">${p.name}</div>
                        <div class="auth-profile-role">${p.role_label || p.role}</div>
                    </div>
                </div>
                <div style="display:flex; align-items:center; gap:0.5rem;">
                    <span class="preset-badge ${roleColor}">${p.badge}</span>
                    <span style="font-size:0.8rem; color:var(--color-blue); font-weight:600;">Sign In →</span>
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

            // Box outline
            ctx.strokeStyle = '#388bfd';
            ctx.lineWidth = 3;
            ctx.strokeRect(x, y, w, h);

            // Translucent fill
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
        });

        // Draw active drag rectangle
        if (isDrawing && pendingBox) {
            const [x, y, w, h] = pendingBox;
            ctx.save();
            ctx.setLineDash([6, 6]);
            ctx.strokeStyle = '#2ea043';
            ctx.lineWidth = 3;
            ctx.strokeRect(x, y, w, h);
            ctx.fillStyle = 'rgba(46, 160, 67, 0.25)';
            ctx.fillRect(x, y, w, h);
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
        const pos = getCanvasCoords(e);
        isDrawing = true;
        startX = pos.x;
        startY = pos.y;
        pendingBox = [startX, startY, 0, 0];
    });

    el.annotationCanvas.addEventListener('mousemove', (e) => {
        if (!isDrawing) return;
        const pos = getCanvasCoords(e);
        currentX = pos.x;
        currentY = pos.y;

        const x = Math.min(startX, currentX);
        const y = Math.min(startY, currentY);
        const w = Math.abs(currentX - startX);
        const h = Math.abs(currentY - startY);

        pendingBox = [x, y, w, h];
        renderAnnotationCanvas();
    });

    el.annotationCanvas.addEventListener('mouseup', () => {
        if (!isDrawing) return;
        isDrawing = false;

        if (pendingBox && pendingBox[2] >= 12 && pendingBox[3] >= 12) {
            // Open modal to name the component
            openNameModal(pendingBox);
        } else {
            pendingBox = null;
            renderAnnotationCanvas();
        }
    });

    function openNameModal(box) {
        pendingBox = box;
        el.compNameInput.value = '';
        el.nameModal.classList.remove('d-none');
        setTimeout(() => el.compNameInput.focus(), 50);
    }

    function closeNameModal() {
        el.nameModal.classList.add('d-none');
        pendingBox = null;
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
        if (w < 25 || h < 20) {
            return 'Tight box: May clip solder pads (high risk of false alarms under lighting shifts)';
        }
        if (w > canvasW * 0.4 || h > canvasH * 0.4) {
            return 'Large box: Excess background substrate may mask missing parts';
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
            const warningBadge = comp.warning ? `<span class="badge badge-amber" title="${comp.warning}">⚠ Warning: Tight/Loose</span>` : '';

            item.innerHTML = `
                <div class="comp-item-info">
                    <div style="display:flex; align-items:center; gap:0.5rem;">
                        <span class="comp-item-name">${comp.name}</span>
                        ${warningBadge}
                    </div>
                    <span class="comp-item-coords">[${x}, ${y}, ${w}×${h} px]</span>
                </div>
                <div class="comp-item-actions">
                    <button type="button" class="btn-icon btn-rename" title="Rename" data-idx="${idx}">✎</button>
                    <button type="button" class="btn-icon btn-icon-danger btn-del" title="Delete" data-idx="${idx}">&times;</button>
                </div>
            `;
            el.componentListContainer.appendChild(item);
        });

        // Attach action handlers
        el.componentListContainer.querySelectorAll('.btn-del').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const idx = parseInt(e.target.getAttribute('data-idx'));
                state.components.splice(idx, 1);
                renderAnnotationCanvas();
                renderComponentsList();
            });
        });

        el.componentListContainer.querySelectorAll('.btn-rename').forEach(btn => {
            btn.addEventListener('click', (e) => {
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
                el.btnLoadPresetBatch.textContent = '📦 1-Click Load Physical Test Batch for This Board';
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

    function renderResultCards() {
        if (!state.lastInspectionData) return;
        const data = state.lastInspectionData;
        el.resultsCardsContainer.innerHTML = '';

        let okCount = 0, defectCount = 0, reviewCount = 0;

        data.results.forEach((res, resIdx) => {
            const bSign = state.signoffs[res.filename] || {};

            // Compute effective status for this board considering sign-offs
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

            // Determine Banner Styling & Icons
            let bannerClass = 'banner-ok';
            let icon = '✓';
            let titleText = 'OK — PASSED';

            if (effectiveBoardStatus === 'DEFECT') {
                bannerClass = 'banner-defect';
                icon = '✗';
                titleText = hasSignoffs && res.board_status === 'REVIEW'
                    ? 'DEFECT — DEFECTIVE SMT PARTS CONFIRMED VIA SIGN-OFF'
                    : 'DEFECT — SMT DEFECTS DETECTED (MISSING/TILT/SHIFT)';
            } else if (effectiveBoardStatus === 'REVIEW') {
                bannerClass = 'banner-review';
                icon = '⚠';
                titleText = 'REVIEW — OPERATOR SIGN-OFF REQUIRED';
            } else if (effectiveBoardStatus === 'OK' && hasSignoffs && res.board_status === 'REVIEW') {
                bannerClass = 'banner-ok';
                icon = '✓';
                titleText = 'OK — PASSED (SIGN-OFF VERIFIED)';
            } else if (effectiveBoardStatus === 'ERROR') {
                bannerClass = 'banner-defect';
                icon = '⚠';
                titleText = 'PROCESSING ERROR';
            }

            // Alignment Notice
            const alignNotice = res.alignment && res.alignment.fallback_used
                ? `<div class="alignment-notice">⚠ Alignment Notice: ${res.alignment.message} (dx: ${res.alignment.dx_px}px, dy: ${res.alignment.dy_px}px)</div>`
                : '';

            card.innerHTML = `
                <div class="result-banner ${bannerClass}">
                    <div>
                        <div class="banner-status-title"><span>${icon}</span> ${titleText}</div>
                        <div class="banner-summary">${res.summary} ${hasSignoffs ? '<span style="opacity:0.9;">(Human review logged)</span>' : ''}</div>
                    </div>
                    <div style="text-align:right;">
                        <span class="banner-filename">${res.filename}</span>
                        ${res.elapsed_ms ? `<div style="font-size:0.75rem; opacity:0.8;">Inspection time: ${res.elapsed_ms} ms</div>` : ''}
                    </div>
                </div>
                ${alignNotice}
                <div class="result-card-body">
                    <!-- Annotated Visual Viewport -->
                    <div class="result-image-view">
                        <canvas id="res-canvas-${resIdx}"></canvas>
                    </div>

                    <!-- Detailed Table -->
                    <div class="result-table-wrap">
                        <table class="result-table">
                            <thead>
                                <tr>
                                    <th>Component</th>
                                    <th>Verdict & Operator Sign-Off</th>
                                    <th>ZNCC</th>
                                    <th>Tilt (°)</th>
                                    <th>Shift (px)</th>
                                    <th>Diagnostic Reason</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${res.components.map(c => {
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

                                    let signoffHtml = '';
                                    if (c.status === 'UNCERTAIN') {
                                        if (sign) {
                                            const isPres = sign.final_status === 'PRESENT';
                                            const signBadge = isPres ? 'badge-signoff-verified' : 'badge-signoff-confirmed';
                                            const signIcon = isPres ? '✓' : '✗';
                                            signoffHtml = `
                                                <div style="margin-top:0.35rem;">
                                                    <span class="${signBadge}">${signIcon} ${isPres ? 'VERIFIED PRESENT' : 'CONFIRMED DEFECT'}</span>
                                                    <span style="font-size:0.75rem; color:#8b949e; margin-left:0.3rem;">(By ${sign.operator_id}${sign.note ? ' &bull; ' + sign.note : ''})</span>
                                                    <button type="button" class="btn-link btn-edit-signoff" data-res-idx="${resIdx}" data-fname="${res.filename}" data-comp="${c.name}" style="margin-left:0.5rem; font-size:0.75rem; color:#58a6ff;">✎ Edit</button>
                                                </div>
                                                <div style="font-size:0.75rem; color:#8b949e; margin-top:2px;">Original Machine Verdict: UNCERTAIN</div>
                                            `;
                                        } else {
                                            signoffHtml = `
                                                <div class="signoff-box">
                                                    <div class="signoff-header-text">⚠ Operator Sign-Off Required for This Part</div>
                                                    <div class="signoff-controls-row">
                                                        <input type="text" class="signoff-input signoff-input-badge" id="badge-${resIdx}-${c.name}" placeholder="Badge ID" value="${state.currentUser ? state.currentUser.badge : 'OP-8402'}">
                                                        <input type="text" class="signoff-input signoff-input-note" id="note-${resIdx}-${c.name}" placeholder="Optional note (e.g. glare on lead)">
                                                        <button type="button" class="btn btn-sm btn-success btn-signoff" data-res-idx="${resIdx}" data-fname="${res.filename}" data-comp="${c.name}" data-verdict="PRESENT">✓ Verify Present</button>
                                                        <button type="button" class="btn btn-sm btn-danger btn-signoff" data-res-idx="${resIdx}" data-fname="${res.filename}" data-comp="${c.name}" data-verdict="MISSING">✗ Confirm Defect</button>
                                                    </div>
                                                </div>
                                            `;
                                        }
                                    }

                                    return `
                                        <tr class="${rowClass}">
                                            <td><strong>${c.name}</strong></td>
                                            <td>
                                                <span class="badge ${badgeClass}">${c.status}</span>
                                                ${signoffHtml}
                                            </td>
                                            <td class="score-num">${c.scores.zncc.toFixed(4)}</td>
                                            <td class="score-num">${tiltStr}</td>
                                            <td class="score-num">${shiftStr}</td>
                                            <td>${c.reason}</td>
                                        </tr>
                                    `;
                                }).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;

            el.resultsCardsContainer.appendChild(card);

            // Draw annotated test board image on canvas
            drawResultCanvas(`res-canvas-${resIdx}`, res);
        });

        // Summary badge
        el.resultsSummaryBadge.className = defectCount > 0 ? 'badge badge-danger' : (reviewCount > 0 ? 'badge badge-amber' : 'badge badge-success');
        el.resultsSummaryBadge.textContent = `${data.results.length} Board(s): ${okCount} OK, ${defectCount} Defect, ${reviewCount} Review`;

        // Attach Sign-Off Handlers
        attachSignoffHandlers();
    }

    function attachSignoffHandlers() {
        el.resultsCardsContainer.querySelectorAll('.btn-signoff').forEach(btn => {
            btn.addEventListener('click', (e) => {
                const target = e.currentTarget;
                const resIdx = target.getAttribute('data-res-idx');
                const fname = target.getAttribute('data-fname');
                const comp = target.getAttribute('data-comp');
                const verdict = target.getAttribute('data-verdict');

                const badgeEl = document.getElementById(`badge-${resIdx}-${comp}`);
                const noteEl = document.getElementById(`note-${resIdx}-${comp}`);
                const badge = (badgeEl && badgeEl.value.trim()) || 'OPERATOR';
                const note = (noteEl && noteEl.value.trim()) || '';

                if (!state.signoffs[fname]) state.signoffs[fname] = {};
                state.signoffs[fname][comp] = {
                    final_status: verdict,
                    operator_id: badge,
                    note: note,
                    timestamp: new Date().toLocaleTimeString(),
                };

                // Sync to backend if session exists
                if (state.sessionId) {
                    fetch(`/api/sessions/${state.sessionId}/signoff`, {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({
                            filename: fname,
                            component_name: comp,
                            final_status: verdict,
                            operator_id: badge,
                            note: note,
                        }),
                    }).catch(() => {});
                }

                renderResultCards();
                updateBatchSummary();
            });
        });

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

    // --- PRINTABLE INSPECTION REPORT ---
    function openPrintableReport() {
        if (!state.lastInspectionData) {
            showAlert('No inspection data available for printing.', 'danger');
            return;
        }

        const data = state.lastInspectionData;
        const results = data.results;
        const total = results.length;

        let machineOk = 0, finalOk = 0;
        results.forEach(res => {
            if (res.board_status === 'OK') machineOk++;
            const bSign = state.signoffs[res.filename] || {};
            let hasDefect = false, hasUnc = false;
            res.components.forEach(c => {
                const eff = (bSign[c.name] && bSign[c.name].final_status) || c.status;
                if (['MISSING', 'TILTED', 'MISALIGNED', 'BRIDGED', 'POLARITY_REVERSED', 'TOMBSTONED'].includes(eff)) hasDefect = true;
                else if (eff === 'UNCERTAIN') hasUnc = true;
            });
            if (!hasDefect && !hasUnc) finalOk++;
        });

        const fpy = total > 0 ? ((machineOk / total) * 100).toFixed(1) : '0.0';
        const finalY = total > 0 ? ((finalOk / total) * 100).toFixed(1) : '0.0';

        let tableRows = '';
        results.forEach(res => {
            const bSign = state.signoffs[res.filename] || {};
            let hasDefect = false, hasUnc = false;
            res.components.forEach(c => {
                const eff = (bSign[c.name] && bSign[c.name].final_status) || c.status;
                if (['MISSING', 'TILTED', 'MISALIGNED', 'BRIDGED', 'POLARITY_REVERSED', 'TOMBSTONED'].includes(eff)) hasDefect = true;
                else if (eff === 'UNCERTAIN') hasUnc = true;
            });
            const finalBStatus = hasDefect ? 'DEFECT' : (hasUnc ? 'REVIEW' : 'OK');

            res.components.forEach(c => {
                const sign = bSign[c.name];
                const eff = sign ? sign.final_status : c.status;
                const signText = sign ? `${sign.final_status} (by ${sign.operator_id}${sign.note ? ': ' + sign.note : ''})` : '-';
                const tiltStr = (c.scores && c.scores.tilt_deg !== undefined) ? (c.scores.tilt_deg > 0 ? `+${c.scores.tilt_deg.toFixed(1)}°` : `${c.scores.tilt_deg.toFixed(1)}°`) : '0.0°';
                const shiftStr = (c.scores && c.scores.shift_dist_px !== undefined) ? `${c.scores.shift_dist_px.toFixed(1)}px` : '0.0px';
                tableRows += `
                    <tr>
                        <td>${res.filename}</td>
                        <td><strong>${c.name}</strong></td>
                        <td>${c.status}</td>
                        <td><strong>${eff}</strong></td>
                        <td>${c.scores.zncc.toFixed(4)}</td>
                        <td>${tiltStr}</td>
                        <td>${shiftStr}</td>
                        <td>${signText}</td>
                    </tr>
                `;
            });
        });

        el.printableReportContent.innerHTML = `
            <div class="print-cert-header">
                <div>
                    <h1>PCB AUTOMATED OPTICAL INSPECTION REPORT</h1>
                    <p>Batch Inspection & Audit Record</p>
                </div>
                <div style="text-align:right;">
                    <p><strong>Inspection Date:</strong> ${new Date().toLocaleString()}</p>
                    <p><strong>Session ID:</strong> ${state.sessionId || 'N/A'}</p>
                    <p><strong>Certified Lead:</strong> ${state.currentUser ? `${state.currentUser.name} (${state.currentUser.badge} &bull; ${state.currentUser.role})` : 'Sarah Jenkins (OP-8402)'}</p>
                </div>
            </div>
            <div class="print-meta-grid">
                <div class="print-meta-item"><strong>Boards Inspected</strong>${total}</div>
                <div class="print-meta-item"><strong>Sensitivity Mode</strong>${state.activeSensitivity.toUpperCase()}</div>
                <div class="print-meta-item"><strong>First-Pass Yield (Machine)</strong>${fpy}%</div>
                <div class="print-meta-item"><strong>Final Yield (Post Sign-Off)</strong>${finalY}%</div>
            </div>
            <table class="print-table">
                <thead>
                    <tr>
                        <th>Board Filename</th>
                        <th>Component</th>
                        <th>Machine Verdict</th>
                        <th>Final Verdict</th>
                        <th>ZNCC</th>
                        <th>Tilt (°)</th>
                        <th>Shift (px)</th>
                        <th>Operator Sign-Off</th>
                    </tr>
                </thead>
                <tbody>
                    ${tableRows}
                </tbody>
            </table>
            <div class="print-footer-sign">
                <div><strong>Certified Inspector:</strong> ${state.currentUser ? state.currentUser.name : 'Sarah Jenkins'} [ID: ${state.currentUser ? state.currentUser.badge : 'OP-8402'}]</div>
                <div><strong>Line Supervisor:</strong> ______________________ (QA Verification)</div>
                <div><strong>Audit Date:</strong> ${new Date().toISOString().slice(0, 10)}</div>
            </div>
        `;

        el.printModal.classList.remove('d-none');
    }

    if (el.btnPrintReport) {
        el.btnPrintReport.addEventListener('click', openPrintableReport);
    }
    if (el.btnTriggerPrint) {
        el.btnTriggerPrint.addEventListener('click', () => window.print());
    }
    if (el.btnClosePrint) {
        el.btnClosePrint.addEventListener('click', () => el.printModal.classList.add('d-none'));
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

                // Draw bounding box
                ctx.strokeStyle = color;
                ctx.lineWidth = 4;
                ctx.strokeRect(x, y, w, h);

                ctx.fillStyle = fillColor;
                ctx.fillRect(x, y, w, h);

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
});
