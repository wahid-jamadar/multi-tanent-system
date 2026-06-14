/**
 * FileBridge Intelligent Synchronization JS (Overhauled)
 */

document.addEventListener('DOMContentLoaded', () => {
    // Roles checks
    const userRoles = window.FileBridgeConfig?.userRoles || [];
    const hasWriteAccess = userRoles.includes('Super Admin') || userRoles.includes('Admin');

    // UI Elements
    const activePairsContainer = document.getElementById('activePairsContainer');
    const pairCount = document.getElementById('pairCount');
    const syncStatus = document.getElementById('syncStatus');
    const activityLog = document.getElementById('activityLog');
    const logEmptyState = document.getElementById('logEmptyState');
    const globalProgressContainer = document.getElementById('globalProgressContainer');
    const globalProgressBar = document.getElementById('globalProgressBar');
    const globalProgressPercent = document.getElementById('globalProgressPercent');
    const currentSyncingFile = document.getElementById('currentSyncingFile');
    const clearLogsBtn = document.getElementById('clearLogsBtn');
    const refreshAllBtn = document.getElementById('refreshAllBtn');

    // Modal Elements
    const syncJobModalEl = document.getElementById('syncJobModal');
    const syncJobModal = new bootstrap.Modal(syncJobModalEl);
    const syncModalTitle = document.getElementById('syncModalTitle');
    const jobNameInput = document.getElementById('jobName');
    const sourceServerSelect = document.getElementById('modalSourceServer');
    const destServerSelect = document.getElementById('modalDestServer');
    const sourcePathInput = document.getElementById('jobSourcePath');
    const destPathInput = document.getElementById('jobDestPath');
    const saveSyncChangesBtn = document.getElementById('saveSyncChangesBtn');
    const applySyncJobBtn = document.getElementById('applySyncJobBtn');
    const previewSyncBtn = document.getElementById('previewSyncBtn');

    // Path Browser Elements
    const pathBrowserModalEl = document.getElementById('pathBrowserModal');
    const pathBrowserModal = new bootstrap.Modal(pathBrowserModalEl);
    const browserList = document.getElementById('browserList');
    const browserBreadcrumbs = document.getElementById('browserBreadcrumbs');
    const browserSelectionInfo = document.getElementById('browserSelectionInfo');
    const selectPathBtn = document.getElementById('selectPathBtn');

    // State
    let currentRuleId = null; // null for New, integer for Edit
    let currentSyncType = 'server';
    let currentInterval = 300;
    let currentDirection = 'bidirectional';
    let browserState = {
        serverId: null,
        currentPath: '/',
        selectedItem: null,
        targetInputId: null,
        selectionMode: 'folder' // 'folder' or 'file'
    };

    // --- Initialization ---

    function init() {
        loadActivePairs();
        setupEventListeners();
        
        // Auto-refresh pairs every 10 seconds to update status badges
        setInterval(loadActivePairs, 10000);
    }

    function setupEventListeners() {
        if (refreshAllBtn) refreshAllBtn.onclick = () => loadActivePairs();
        if (clearLogsBtn) clearLogsBtn.onclick = () => {
            activityLog.innerHTML = '';
            activityLog.appendChild(logEmptyState);
            logEmptyState.classList.remove('d-none');
        };

        // Modal Trigger (New Job)
        const newSyncJobBtn = document.getElementById('newSyncJobBtn');
        if (newSyncJobBtn) {
            newSyncJobBtn.onclick = () => openSyncModal();
        }

        // Card Selection (Sync Type)
        document.querySelectorAll('.sync-type-card').forEach(card => {
            card.onclick = () => {
                document.querySelectorAll('.sync-type-card').forEach(c => c.classList.remove('active'));
                card.classList.add('active');
                currentSyncType = card.dataset.type;
                updateSyncTypeUI();
            };
        });

        // Card Selection (Direction)
        document.querySelectorAll('.sync-direction-card').forEach(card => {
            card.onclick = () => {
                document.querySelectorAll('.sync-direction-card').forEach(c => c.classList.remove('active'));
                card.classList.add('active');
                currentDirection = card.dataset.direction;
            };
        });

        // Card Selection (Scheduler)
        document.querySelectorAll('.scheduler-card').forEach(card => {
            card.onclick = () => {
                document.querySelectorAll('.scheduler-card').forEach(c => {
                    c.classList.remove('active');
                    c.querySelector('.bi-check').classList.add('d-none');
                });
                card.classList.add('active');
                card.querySelector('.bi-check').classList.remove('d-none');
                currentInterval = parseInt(card.dataset.interval);
            };
        });

        // Browse Buttons
        document.querySelectorAll('.browse-btn').forEach(btn => {
            btn.onclick = () => {
                const targetId = btn.dataset.target;
                const serverSelectId = btn.dataset.serverSelect;
                const serverId = document.getElementById(serverSelectId).value;

                if (!serverId) {
                    showToast('Please select a server first', 'warning');
                    return;
                }

                openPathBrowser(serverId, targetId, currentSyncType === 'files' ? 'file' : 'folder');
            };
        });

        // Preview Logic
        previewSyncBtn.onclick = (e) => {
            e.preventDefault();
            runPreview();
        };

        // Save / Apply Logic
        saveSyncChangesBtn.onclick = () => saveSyncRule(false);
        applySyncJobBtn.onclick = () => saveSyncRule(true);

        // Path Browser - Select
        selectPathBtn.onclick = () => {
            if (!browserState.selectedItem && browserState.selectionMode === 'file') {
                showToast('Please select a file', 'warning');
                return;
            }
            const path = browserState.selectedItem ? browserState.selectedItem.path : browserState.currentPath;
            document.getElementById(browserState.targetInputId).value = path;
            pathBrowserModal.hide();
        };
    }

    // --- Sync Modal Logic ---

    function openSyncModal(ruleId = null) {
        currentRuleId = ruleId;
        resetModalUI();

        if (ruleId) {
            syncModalTitle.innerHTML = `<i class="bi bi-pencil-square me-2 text-primary"></i>Edit Synchronization Job`;
            fetchSyncRule(ruleId);
        } else {
            syncModalTitle.innerHTML = `<i class="bi bi-plus-circle-dotted me-2 text-primary"></i>Create New Sync Job`;
        }

        syncJobModal.show();
    }

    function resetModalUI() {
        jobNameInput.value = '';
        sourceServerSelect.value = '';
        destServerSelect.value = '';
        sourcePathInput.value = '';
        destPathInput.value = '';
        
        // Reset Sync Type to 'server'
        document.querySelector('.sync-type-card[data-type="server"]').click();

        // Reset Direction to 'bidirectional'
        const dirCard = document.querySelector('.sync-direction-card[data-direction="bidirectional"]');
        if (dirCard) dirCard.click();
        
        // Reset Interval to 300
        document.querySelector('.scheduler-card[data-interval="300"]').click();

        // Reset Preview
        document.getElementById('previewEmptyState').classList.remove('d-none');
        document.getElementById('previewResults').classList.add('d-none');
        document.getElementById('previewLoading').classList.add('d-none');
        
        const sourceRows = document.getElementById('sourcePreviewRows');
        const destRows = document.getElementById('destPreviewRows');
        if (sourceRows) sourceRows.innerHTML = '';
        if (destRows) destRows.innerHTML = '';
        
        const srcBadge = document.getElementById('sourceServerBadge');
        const destBadge = document.getElementById('destServerBadge');
        if (srcBadge) srcBadge.textContent = 'Source';
        if (destBadge) destBadge.textContent = 'Destination';
        
        const srcPathDisplay = document.getElementById('sourcePathDisplay');
        const destPathDisplay = document.getElementById('destPathDisplay');
        if (srcPathDisplay) srcPathDisplay.textContent = 'Path: ';
        if (destPathDisplay) destPathDisplay.textContent = 'Path: ';
    }

    function updateSyncTypeUI() {
        const infoText = document.querySelector('#previewArea + div p');
        if (!infoText) return;
        switch (currentSyncType) {
            case 'server': infoText.textContent = "Full server-to-server synchronization including all data volumes."; break;
            case 'drive': infoText.textContent = "Synchronizing specific disk drives or mount points between systems."; break;
            case 'folder': infoText.textContent = "Precise folder-level synchronization for specific project data."; break;
            case 'files': infoText.textContent = "Targeted file synchronization. Select individual files for high-priority transfer."; break;
        }
    }

    async function fetchSyncRule(id) {
        try {
            const response = await fetch(`/api/sync/rules/${id}`);
            if (!response.ok) throw new Error('Failed to fetch rule');
            const rule = await response.json();

            jobNameInput.value = rule.name;
            sourceServerSelect.value = rule.left_server_id;
            destServerSelect.value = rule.right_server_id;
            sourcePathInput.value = rule.left_path;
            destPathInput.value = rule.right_path;

            // Set interval card
            const intervalCard = document.querySelector(`.scheduler-card[data-interval="${rule.interval}"]`);
            if (intervalCard) intervalCard.click();
            else {
                document.querySelector('.scheduler-card[data-interval="0"]').click();
            }
            
            // Set direction card
            const dirCard = document.querySelector(`.sync-direction-card[data-direction="${rule.direction}"]`);
            if (dirCard) dirCard.click();

            // Sync type is UI-only for now, default to folder if it looks like a path
            if (rule.left_path.includes('.') && !rule.left_path.endsWith('/')) {
                document.querySelector('.sync-type-card[data-type="files"]').click();
            } else {
                document.querySelector('.sync-type-card[data-type="folder"]').click();
            }

        } catch (error) {
            showToast(error.message, 'danger');
            syncJobModal.hide();
        }
    }

    // --- Path Browser Logic ---

    async function openPathBrowser(serverId, inputId, mode) {
        let startPath = document.getElementById(inputId).value || '/';
        browserState = {
            serverId: serverId,
            currentPath: startPath,
            selectedItem: null,
            targetInputId: inputId,
            selectionMode: mode
        };

        pathBrowserModal.show();
        loadBrowserFiles();
    }

    async function loadBrowserFiles() {
        browserList.innerHTML = '<div class="p-5 text-center"><div class="spinner-border text-primary"></div><p class="mt-2 small text-secondary">Connecting to agent...</p></div>';
        updateBreadcrumbs();
        browserSelectionInfo.textContent = 'Scanning...';

        try {
            const jobResponse = await fetch('/api/file-manager/jobs', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    job_type: 'list',
                    server_id: browserState.serverId,
                    path: browserState.currentPath
                })
            });

            if (!jobResponse.ok) throw new Error('Failed to initiate file listing');
            const job = await jobResponse.json();

            const result = await waitForJob(job.job_uuid);
            if (result.status !== 'success') throw new Error(result.message || 'Listing failed');

            const files = result.result.files || [];
            renderBrowserFiles(files);

        } catch (error) {
            browserList.innerHTML = `<div class="p-5 text-center text-danger"><i class="bi bi-exclamation-triangle fs-1"></i><p class="mt-2">${error.message}</p></div>`;
            browserSelectionInfo.textContent = 'Error';
        }
    }

    function renderBrowserFiles(files) {
        browserList.innerHTML = '';
        browserSelectionInfo.textContent = `Current Path: ${browserState.currentPath}`;

        if (files.length === 0) {
            browserList.innerHTML = '<div class="p-5 text-center text-secondary small">This directory is empty</div>';
            return;
        }

        files.forEach(file => {
            const item = document.createElement('div');
            item.className = 'path-item p-2 px-3 border-bottom border-secondary border-opacity-10 d-flex align-items-center gap-3';
            const icon = file.is_dir ? 'bi-folder-fill text-warning' : 'bi-file-earmark-text text-secondary';
            
            item.innerHTML = `
                <i class="bi ${icon} fs-5"></i>
                <div class="flex-grow-1 text-white small">${file.name}</div>
                <div class="x-small text-muted">${file.is_dir ? 'Dir' : formatSize(file.size)}</div>
            `;

            item.onclick = () => {
                if (file.is_dir) {
                    browserState.currentPath = file.path;
                    loadBrowserFiles();
                } else {
                    document.querySelectorAll('.path-item').forEach(i => i.classList.remove('selected'));
                    item.classList.add('selected');
                    browserState.selectedItem = file;
                    browserSelectionInfo.textContent = `Selected: ${file.name}`;
                }
            };
            
            browserList.appendChild(item);
        });
    }

    function updateBreadcrumbs() {
        const path = browserState.currentPath;
        const isWindows = path.includes('\\') || path.includes(':');
        const parts = path.split(/[\\/]/).filter(p => p);
        browserBreadcrumbs.innerHTML = `<li class="breadcrumb-item"><a href="#" onclick="navigateToPath('/')">Root</a></li>`;
        
        let currentBuildPath = '';
        parts.forEach((part, index) => {
            if (isWindows && index === 0 && part.includes(':')) {
                currentBuildPath = part + '\\';
            } else {
                currentBuildPath += (isWindows ? '\\' : '/') + part;
            }
            const isLast = index === parts.length - 1;
            const li = document.createElement('li');
            li.className = `breadcrumb-item ${isLast ? 'active' : ''}`;
            if (isLast) {
                li.textContent = part;
            } else {
                const a = document.createElement('a');
                a.href = '#';
                const capturedPath = currentBuildPath;
                a.onclick = (e) => { e.preventDefault(); navigateToPath(capturedPath); };
                a.textContent = part;
                li.appendChild(a);
            }
            browserBreadcrumbs.appendChild(li);
        });
    }

    window.navigateToPath = (path) => {
        browserState.currentPath = path;
        loadBrowserFiles();
    };

    // --- Preview Logic ---

    async function runPreview() {
        const sourceId = sourceServerSelect.value;
        const destId = destServerSelect.value;
        const sourcePath = sourcePathInput.value.trim();
        const destPath = destPathInput.value.trim();

        if (!sourceId || !destId || !sourcePath || !destPath) {
            showToast('Please fill in all server and path details first', 'warning');
            return;
        }

        document.getElementById('previewEmptyState').classList.add('d-none');
        document.getElementById('previewResults').classList.add('d-none');
        document.getElementById('previewLoading').classList.remove('d-none');

        try {
            // 1. List Source (Recursive)
            const srcListJob = await createListJob(sourceId, sourcePath, true);
            const srcResult = await waitForJob(srcListJob.job_uuid);
            if (srcResult.status !== 'success') throw new Error(`Source listing failed: ${srcResult.message}`);

            // 2. List Dest (Recursive)
            const destListJob = await createListJob(destId, destPath, true);
            const destResult = await waitForJob(destListJob.job_uuid);
            if (destResult.status !== 'success') throw new Error(`Destination listing failed: ${destResult.message}`);

            // 3. Diff
            const diffResponse = await fetch('/api/sync/diff', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    left_files: srcResult.result.files || [],
                    right_files: destResult.result.files || []
                })
            });

            if (!diffResponse.ok) throw new Error('Diff calculation failed');
            const data = await diffResponse.json();

            updatePreviewSummary(data.summary);
            renderPreviewDiff(data.changes);

        } catch (error) {
            showToast(error.message, 'danger');
            document.getElementById('previewLoading').classList.add('d-none');
            document.getElementById('previewEmptyState').classList.remove('d-none');
        }
    }

    function updatePreviewSummary(summary) {
        const sumNewSource = document.getElementById('sumNewSource');
        const sumNewDest = document.getElementById('sumNewDest');
        const sumModified = document.getElementById('sumModified');
        const sumConflict = document.getElementById('sumConflict');
        const sumIdentical = document.getElementById('sumIdentical');

        if (sumNewSource) sumNewSource.textContent = `${summary.new_source} New Source`;
        if (sumNewDest) sumNewDest.textContent = `${summary.new_dest} New Dest`;
        if (sumModified) sumModified.textContent = `${summary.modified} Modified`;
        if (sumConflict) sumConflict.textContent = `${summary.conflict} Conflicts`;
        if (sumIdentical) sumIdentical.textContent = `${summary.identical} Identical files skipped`;
    }

    async function createListJob(serverId, path, recursive = false) {
        const response = await fetch('/api/file-manager/jobs', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ job_type: 'list', server_id: serverId, path: path, recursive: recursive })
        });
        if (!response.ok) throw new Error('Failed to create list job');
        return response.json();
    }

    function renderPreviewDiff(diff) {
        const sourceBody = document.getElementById('sourcePreviewRows');
        const destBody = document.getElementById('destPreviewRows');
        if (sourceBody) sourceBody.innerHTML = '';
        if (destBody) destBody.innerHTML = '';

        // Dynamically get server names from selectors
        const sourceServerName = sourceServerSelect.options[sourceServerSelect.selectedIndex]?.text || 'Source';
        const destServerName = destServerSelect.options[destServerSelect.selectedIndex]?.text || 'Destination';
        
        // Update server badges & paths
        const srcBadge = document.getElementById('sourceServerBadge');
        const dstBadge = document.getElementById('destServerBadge');
        if (srcBadge) srcBadge.textContent = sourceServerName;
        if (dstBadge) dstBadge.textContent = destServerName;
        
        const sourcePath = sourcePathInput.value.trim();
        const destPath = destPathInput.value.trim();
        
        const srcPathDisplay = document.getElementById('sourcePathDisplay');
        const dstPathDisplay = document.getElementById('destPathDisplay');
        if (srcPathDisplay) {
            srcPathDisplay.textContent = `Path: ${sourcePath}`;
            srcPathDisplay.title = sourcePath;
        }
        if (dstPathDisplay) {
            dstPathDisplay.textContent = `Path: ${destPath}`;
            dstPathDisplay.title = destPath;
        }

        // Helper to render relative paths neatly without vertical character wrapping
        function formatFilePathCell(relPath, isDir) {
            let cleanPath = relPath;
            if (cleanPath.endsWith('/') || cleanPath.endsWith('\\')) {
                cleanPath = cleanPath.slice(0, -1);
            }
            const parts = cleanPath.split(/[\\/]/);
            const fileName = parts.pop() || cleanPath;
            const dirPath = parts.join('/');
            
            const iconClass = isDir ? 'bi-folder2-open text-warning' : 'bi-file-earmark-text text-secondary';
            
            return `
                <div class="text-truncate" title="${relPath}">
                    <span class="text-white fw-semibold"><i class="bi ${iconClass} me-2"></i>${fileName}</span>
                    ${dirPath ? `<div class="text-muted x-small ps-4 mt-0.5" style="font-size: 0.68rem; opacity: 0.75;">${dirPath}</div>` : ''}
                </div>
            `;
        }

        if (diff.length === 0) {
            if (sourceBody) sourceBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-secondary">No differences. Folders are in sync.</td></tr>';
            if (destBody) destBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-secondary">No differences. Folders are in sync.</td></tr>';
        } else {
            let sourceDiffCount = 0;
            let destDiffCount = 0;

            diff.forEach(item => {
                // If present on source (left)
                if (item.left && sourceBody) {
                    sourceDiffCount++;
                    const tr = document.createElement('tr');
                    const file = item.left;
                    let badgeText = '';
                    let badgeClass = '';
                    
                    if (item.type === 'new_source') {
                        badgeText = 'NEW';
                        badgeClass = 'bg-success bg-opacity-10 text-success border border-success border-opacity-25';
                    } else if (item.type === 'modified') {
                        badgeText = 'MODIFIED';
                        badgeClass = 'bg-warning bg-opacity-10 text-warning border border-warning border-opacity-25';
                    } else if (item.type === 'conflict') {
                        badgeText = 'CONFLICT';
                        badgeClass = 'bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25';
                    }

                    tr.innerHTML = `
                        <td class="align-middle" style="max-width: 0;">${formatFilePathCell(item.rel_path, file.is_dir)}</td>
                        <td class="text-secondary text-end align-middle">${file.is_dir ? '-' : formatSize(file.size)}</td>
                        <td class="text-center align-middle"><span class="badge ${badgeClass} x-small" style="font-size: 0.65rem; padding: 3px 6px;">${badgeText}</span></td>
                    `;
                    sourceBody.appendChild(tr);
                }

                // If present on destination (right)
                if (item.right && destBody) {
                    destDiffCount++;
                    const tr = document.createElement('tr');
                    const file = item.right;
                    let badgeText = '';
                    let badgeClass = '';
                    
                    if (item.type === 'new_dest') {
                        badgeText = 'NEW';
                        badgeClass = 'bg-info bg-opacity-10 text-info border border-info border-opacity-25';
                    } else if (item.type === 'modified') {
                        badgeText = 'MODIFIED';
                        badgeClass = 'bg-warning bg-opacity-10 text-warning border border-warning border-opacity-25';
                    } else if (item.type === 'conflict') {
                        badgeText = 'CONFLICT';
                        badgeClass = 'bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25';
                    }

                    tr.innerHTML = `
                        <td class="align-middle" style="max-width: 0;">${formatFilePathCell(item.rel_path, file.is_dir)}</td>
                        <td class="text-secondary text-end align-middle">${file.is_dir ? '-' : formatSize(file.size)}</td>
                        <td class="text-center align-middle"><span class="badge ${badgeClass} x-small" style="font-size: 0.65rem; padding: 3px 6px;">${badgeText}</span></td>
                    `;
                    destBody.appendChild(tr);
                }
            });

            if (sourceDiffCount === 0 && sourceBody) {
                sourceBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-secondary">No differences.</td></tr>';
            }
            if (destDiffCount === 0 && destBody) {
                destBody.innerHTML = '<tr><td colspan="3" class="text-center py-4 text-secondary">No differences.</td></tr>';
            }
        }

        document.getElementById('previewLoading').classList.add('d-none');
        document.getElementById('previewResults').classList.remove('d-none');
    }

    function getStatusBadge(type) {
        switch (type) {
            case 'new_source': return '<span class="badge bg-success bg-opacity-10 text-success border border-success border-opacity-25">NEW SOURCE</span>';
            case 'new_dest': return '<span class="badge bg-info bg-opacity-10 text-info border border-info border-opacity-25">NEW DEST</span>';
            case 'modified': return '<span class="badge bg-warning bg-opacity-10 text-warning border border-warning border-opacity-25">MODIFIED</span>';
            case 'conflict': return '<span class="badge bg-danger bg-opacity-10 text-danger border border-danger border-opacity-25">CONFLICT</span>';
            default: return '<span class="badge bg-secondary">UNKNOWN</span>';
        }
    }

    function getActionText(type) {
        switch (type) {
            case 'new_source': return '→ Sync to Dest';
            case 'new_dest': return '← Sync to Source';
            case 'modified': return '↺ Update';
            case 'conflict': return '⚠ Review';
            default: return 'No action';
        }
    }

    // --- Persistence Logic ---

    async function saveSyncRule(triggerNow = false) {
        const payload = {
            name: jobNameInput.value.trim(),
            left_server_id: sourceServerSelect.value,
            right_server_id: destServerSelect.value,
            left_path: sourcePathInput.value.trim(),
            right_path: destPathInput.value.trim(),
            direction: currentDirection,
            is_realtime: currentInterval !== 0,
            interval: currentInterval
        };

        if (!payload.name || !payload.left_server_id || !payload.right_server_id || !payload.left_path || !payload.right_path) {
            showToast('Please complete all required fields', 'warning');
            return;
        }

        try {
            const method = currentRuleId ? 'PUT' : 'POST';
            const url = currentRuleId ? `/api/sync/rules/${currentRuleId}` : '/api/sync/rules';

            const response = await fetch(url, {
                method: method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) throw new Error('Failed to save synchronization rule');
            const result = await response.json();

            showToast(currentRuleId ? 'Configuration updated' : 'Sync job created successfully', 'success');
            
            const ruleId = currentRuleId || result.id;
            syncJobModal.hide();
            loadActivePairs();

            if (triggerNow && ruleId) {
                addLogEntry(`Initiating immediate sync for "${payload.name}"...`);
                triggerSync(ruleId);
            }

        } catch (error) {
            showToast(error.message, 'danger');
        }
    }

    // --- Helper Functions ---

    async function loadActivePairs() {
        try {
            const response = await fetch('/api/sync/rules');
            if (!response.ok) throw new Error(`HTTP ${response.status}`);
            const rules = await response.json();
            renderPairs(rules);
        } catch (error) {
            console.error('Failed to load pairs:', error);
            if (pairCount) pairCount.textContent = '---';
            activePairsContainer.innerHTML = `<div class="col-12 text-center py-4 glass-panel border-danger border-opacity-25"><p class="text-danger small"><i class="bi bi-exclamation-circle me-2"></i>Failed to load pairs: ${error.message}</p></div>`;
        }
    }

    function renderPairs(rules) {
        activePairsContainer.innerHTML = '';
        if (pairCount) pairCount.textContent = `${rules.length} Pairs Active`;

        if (rules.length === 0) {
            activePairsContainer.innerHTML = '<div class="col-12 text-center py-5 glass-panel border-dashed"><p class="text-secondary small">No permanent pairs established. Click "New Sync Job" to begin.</p></div>';
            return;
        }

        rules.forEach(rule => {
            const col = document.createElement('div');
            col.className = 'col-md-6 col-lg-4 mb-4';
            
            const leftStatus = rule.left_server_status || 'unknown';
            const rightStatus = rule.right_server_status || 'unknown';
            
            col.innerHTML = `
                <div class="glass-panel p-0 border-primary border-opacity-25 h-100 overflow-hidden shadow-sm hover-elevate animate__animated animate__fadeIn">
                    <div class="p-3 border-bottom border-secondary border-opacity-10 d-flex justify-content-between align-items-center bg-dark bg-opacity-25">
                        <h6 class="text-white mb-0 fw-bold"><i class="bi bi-link-45deg text-primary me-2"></i>${rule.name}</h6>
                        <span class="badge ${rule.is_enabled ? 'bg-success' : 'bg-secondary'} bg-opacity-10 text-${rule.is_enabled ? 'success' : 'muted'} border border-${rule.is_enabled ? 'success' : 'secondary'} border-opacity-25 x-small">
                            ${rule.is_enabled ? 'ACTIVE' : 'DISABLED'}
                        </span>
                    </div>
                    
                    <div class="p-3">
                        <div class="row g-3 mb-3">
                            <div class="col-6 border-end border-secondary border-opacity-10 pe-3">
                                <div class="d-flex align-items-center gap-2 mb-2">
                                    <div class="status-indicator ${leftStatus === 'online' ? 'bg-success' : 'bg-danger'}" style="width: 8px; height: 8px; border-radius: 50%; box-shadow: 0 0 6px ${leftStatus === 'online' ? 'var(--fb-success)' : 'var(--fb-danger)'}"></div>
                                    <span class="fw-bold text-white small text-truncate" title="${rule.left_server_name}">${rule.left_server_name}</span>
                                </div>
                                <div class="x-small text-muted text-truncate mb-1"><i class="bi bi-cpu me-1"></i>${rule.left_server_hostname}</div>
                            </div>
                            <div class="col-6 ps-3">
                                <div class="d-flex align-items-center gap-2 mb-2">
                                    <div class="status-indicator ${rightStatus === 'online' ? 'bg-success' : 'bg-danger'}" style="width: 8px; height: 8px; border-radius: 50%; box-shadow: 0 0 6px ${rightStatus === 'online' ? 'var(--fb-success)' : 'var(--fb-danger)'}"></div>
                                    <span class="fw-bold text-white small text-truncate" title="${rule.right_server_name}">${rule.right_server_name}</span>
                                </div>
                                <div class="x-small text-muted text-truncate mb-1"><i class="bi bi-cpu me-1"></i>${rule.right_server_hostname}</div>
                            </div>
                        </div>
                        
                        <div class="bg-dark bg-opacity-50 rounded p-2 mb-3 border border-secondary border-opacity-10">
                            <div class="d-flex align-items-center justify-content-between x-small px-1">
                                <span class="text-secondary text-truncate" style="max-width: 42%;" title="${rule.left_path}">${rule.left_path}</span>
                                <i class="bi bi-arrow-left-right text-primary"></i>
                                <span class="text-secondary text-truncate" style="max-width: 42%;" title="${rule.right_path}">${rule.right_path}</span>
                            </div>
                        </div>
                        
                        <div class="d-flex justify-content-between align-items-center pt-2 border-top border-secondary border-opacity-10">
                            <div>
                                <div class="d-flex align-items-center gap-2 mb-1">
                                    <div class="x-small text-muted text-uppercase fw-bold">${rule.direction.replace(/_/g, ' ')}</div>
                                    <span class="badge ${getStatusClass(rule.status)} bg-opacity-10 border border-opacity-25 x-small px-1" style="font-size: 0.6rem;">${rule.status.toUpperCase()}</span>
                                </div>
                                <div class="x-small text-secondary">Last Sync: ${rule.last_run_at ? new Date(rule.last_run_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' }) : 'Never'}</div>
                                ${rule.last_summary && rule.last_summary.summary ? `
                                <div class="x-small text-info mt-1" style="font-size: 0.65rem;">
                                    <i class="bi ${rule.last_summary.verified ? 'bi-shield-check' : 'bi-info-circle'} me-1"></i>${rule.last_summary.summary.created || 0} New, ${rule.last_summary.summary.updated || 0} Updated${rule.last_summary.verified ? ', Verified' : ''}
                                </div>` : ''}
                            </div>
                            ${hasWriteAccess ? `
                            <div class="d-flex gap-1">
                                <button class="btn btn-sm btn-dark p-2 edit-rule-btn" data-rule-id="${rule.id}" title="Edit Configuration">
                                    <i class="bi bi-pencil-square fs-6"></i>
                                </button>
                                <button class="btn btn-sm btn-dark p-2 sync-now-btn" data-rule-id="${rule.id}" title="Run Sync Now"><i class="bi bi-play-fill fs-6"></i></button>
                                <button class="btn btn-sm btn-outline-danger p-2 delete-pair-btn" data-rule-id="${rule.id}" title="Remove Pair"><i class="bi bi-trash fs-6"></i></button>
                            </div>
                            ` : `
                            <span class="text-secondary small">View Only</span>
                            `}
                        </div>
                    </div>
                </div>
            `;
            activePairsContainer.appendChild(col);
        });

        if (hasWriteAccess) {
            activePairsContainer.querySelectorAll('.edit-rule-btn').forEach(btn => btn.onclick = () => openSyncModal(btn.dataset.ruleId));
            activePairsContainer.querySelectorAll('.sync-now-btn').forEach(btn => btn.onclick = () => triggerSync(btn.dataset.ruleId));
            activePairsContainer.querySelectorAll('.delete-pair-btn').forEach(btn => btn.onclick = () => deletePair(btn.dataset.ruleId));
        }
    }

    async function triggerSync(ruleId) {
        try {
            syncStatus.textContent = 'RUNNING';
            syncStatus.className = 'operation-state small status-online animate-pulse';
            globalProgressContainer.classList.remove('d-none');
            logEmptyState.classList.add('d-none');

            const response = await fetch(`/api/sync/rules/${ruleId}/trigger`, { method: 'POST' });
            const result = await response.json();
            
            if (result.status === 'success') {
                showToast(result.message || 'Synchronization scan initiated', 'success');
                addLogEntry(`Sync initiated: ${result.message || 'Scanning phase started'}`);
                // Since it's background synced, we just let the auto-refresh update the UI cards
                setTimeout(() => {
                    syncStatus.textContent = 'IDLE';
                    syncStatus.className = 'operation-state small';
                    globalProgressContainer.classList.add('d-none');
                }, 3000);
            } else {
                showToast(result.message || 'Trigger failed', 'warning');
                finishSync(false);
            }
        } catch (error) {
            addLogEntry(`Error: ${error.message}`, 'danger');
            finishSync(false);
        }
    }

    async function pollSyncJob(uuid) {
        let lastStatus = '';
        while (true) {
            const response = await fetch(`/api/file-manager/jobs/${uuid}`);
            if (!response.ok) break;
            const job = await response.json();
            
            if (job.status !== lastStatus || (job.result && job.result.message)) {
                const msg = job.result?.message || job.message || job.status;
                if (msg !== lastStatus) {
                    addLogEntry(`Sync status: ${msg.toUpperCase()}`);
                    lastStatus = msg;
                }
            }
            
            updateProgress(job.progress || 0);
            if (job.status === 'success') break;
            if (job.status === 'failed') throw new Error(job.result?.message || job.message || 'Job failed');
            await new Promise(r => setTimeout(r, 2000));
        }
    }

    async function waitForJob(jobUuid) {
        for (let i = 0; i < 30; i++) {
            const response = await fetch(`/api/file-manager/jobs/${jobUuid}`);
            const job = await response.json();
            if (job.status === 'success' || job.status === 'failed') return job;
            await new Promise(r => setTimeout(r, 1500));
        }
        throw new Error('Timeout waiting for agent response');
    }

    function updateProgress(percent) {
        percent = Math.min(percent, 100);
        globalProgressBar.style.width = `${percent}%`;
        globalProgressPercent.textContent = `${Math.floor(percent)}%`;
    }

    function finishSync(isSuccess) {
        syncStatus.textContent = 'IDLE';
        syncStatus.className = 'operation-state small';
        if (isSuccess) showToast('Synchronization Completed Successfully', 'success');
        else showToast('Synchronization Failed', 'danger');
        setTimeout(() => {
            globalProgressContainer.classList.add('d-none');
            updateProgress(0);
        }, 5000);
    }

    function addLogEntry(message, type = 'success') {
        const entry = document.createElement('div');
        entry.className = 'list-group-item bg-transparent border-secondary border-opacity-10 text-white small d-flex justify-content-between animate__animated animate__fadeInLeft';
        entry.innerHTML = `<span><i class="bi bi-check2-circle text-success me-2"></i>${message}</span><span class="text-secondary">${new Date().toLocaleTimeString()}</span>`;
        activityLog.insertBefore(entry, activityLog.firstChild);
        logEmptyState.classList.add('d-none');
    }

    async function deletePair(id) {
        if (!confirm('Are you sure you want to remove this synchronization pair?')) return;
        try {
            await fetch(`/api/sync/rules/${id}/delete`, { method: 'POST' });
            showToast('Pair removed successfully', 'info');
            loadActivePairs();
        } catch (error) { showToast('Failed to remove pair', 'danger'); }
    }

    function formatSize(size) {
        if (!size) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
        const i = Math.floor(Math.log(size) / Math.log(k));
        return parseFloat((size / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
    }

    function getStatusClass(status) {
        switch (status) {
            case 'idle': return 'bg-secondary text-secondary border-secondary';
            case 'scanning': return 'bg-info text-info border-info animate-pulse';
            case 'syncing': return 'bg-primary text-primary border-primary animate-pulse';
            case 'verifying': return 'bg-warning text-warning border-warning animate-pulse';
            case 'error': return 'bg-danger text-danger border-danger';
            default: return 'bg-secondary text-secondary border-secondary';
        }
    }

    function showToast(message, type = 'info') {
        const id = 'toast-' + Math.random().toString(36).substr(2, 9);
        const toastHtml = `<div id="${id}" class="toast glass-panel border-${type} animate__animated animate__fadeInUp" role="alert"><div class="toast-header bg-transparent border-bottom border-secondary border-opacity-10 text-white"><strong class="me-auto">Notification</strong><button type="button" class="btn-close btn-close-white" data-bs-dismiss="toast"></button></div><div class="toast-body text-white">${message}</div></div>`;
        let container = document.querySelector('.toast-container') || (() => {
            const c = document.createElement('div');
            c.className = 'toast-container position-fixed bottom-0 end-0 p-3';
            c.style.zIndex = '9999';
            document.body.appendChild(c);
            return c;
        })();
        container.insertAdjacentHTML('beforeend', toastHtml);
        const toastEl = document.getElementById(id);
        if (toastEl) {
            new bootstrap.Toast(toastEl, { delay: 4000 }).show();
            toastEl.addEventListener('hidden.bs.toast', () => toastEl.remove());
        }
    }

    init();
});
