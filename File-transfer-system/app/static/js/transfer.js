(function () {
  function init() {
    const sourceServer = document.getElementById("sourceServer");
    const sourcePath = document.getElementById("sourcePath");
    const sourceRows = document.getElementById("sourceRows");
    const sourceStatus = document.getElementById("sourceStatus");

    const destServer = document.getElementById("destinationServer");
    const destPath = document.getElementById("destinationPath");
    const destRows = document.getElementById("destRows");
    const destStatus = document.getElementById("destStatus");

    const submitBtn = document.getElementById("submitTransfer");
    if (!submitBtn || !sourceServer || !destServer) return;

    let currentJobType = "copy";
    let activeJobStartedAt = null;
    window.currentSourceFiles = [];
    window.currentMatchedFiles = [];

    function joinPath(base, name) {
      const separator = base.includes("\\") ? "\\" : "/";
      return base.replace(/[\\/]+$/, "") + separator + name;
    }

    function parentPath(path) {
      const trimmed = path.replace(/[\\/]+$/, "");
      const index = Math.max(trimmed.lastIndexOf("/"), trimmed.lastIndexOf("\\"));
      if (index <= 0) {
        return trimmed.includes("\\") ? trimmed.slice(0, 3) : "/";
      }
      return trimmed.slice(0, index);
    }

    function formatSize(size) {
      if (size === null || size === undefined) return "-";
      if (size < 1024) return `${size} B`;
      if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
      return `${(size / 1024 / 1024).toFixed(1)} MB`;
    }

    function formatPath(path) {
      if (!path) return "-";
      const parts = path.split(/[\\/]/).filter(Boolean);
      return parts.slice(-2).join("/") || path;
    }

    function formatTimestamp(date = new Date()) {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
    }

    function operationLabel(status, jobType = currentJobType) {
      const verb = jobType === "sync" ? "SYNCING FILES" : jobType === "move" ? "MOVING FILES" : "COPYING FILES";
      if (status === "success") return "OPERATION COMPLETE";
      if (status === "failed") return "OPERATION FAILED";
      if (status === "queued" || status === "assigned") return `${verb} QUEUED`;
      return `${verb}...`;
    }

    function estimateOperationalMetrics(progress, job = null) {
      const elapsedSeconds = activeJobStartedAt ? Math.max(1, (Date.now() - activeJobStartedAt) / 1000) : 1;
      let speed = progress > 0 ? Math.max(8, Math.min(96, progress * 2.4 / elapsedSeconds + 18)) : 0;

      let transferredText = "0 B / 0 B";
      if (job && (job.total_bytes > 0 || job.transferred_bytes > 0)) {
        transferredText = `${formatSize(job.transferred_bytes || 0)} / ${formatSize(job.total_bytes || 0)}`;
        if (elapsedSeconds > 0 && job.transferred_bytes > 0) {
           speed = (job.transferred_bytes / 1024 / 1024) / elapsedSeconds;
        }
      }

      const remainingSeconds = progress > 0 ? Math.max(0, Math.round(((100 - progress) / progress) * elapsedSeconds)) : 0;
      const minutes = Math.floor(remainingSeconds / 60).toString().padStart(2, "0");
      const seconds = Math.floor(remainingSeconds % 60).toString().padStart(2, "0");
      return {
        dataText: transferredText,
        speed: speed ? `${speed.toFixed(1)} MB/s` : "-- MB/s",
        eta: progress >= 100 ? "ETA: 00:00" : progress > 0 ? `ETA: ${minutes}:${seconds}` : "ETA: --:--"
      };
    }

    function setWorkflowActive(isActive, isSyncing = false) {
      document.querySelector(".node-workflow")?.classList.toggle("is-transferring", isActive);
      document.querySelector(".node-workflow")?.classList.toggle("is-syncing", isSyncing);
    }

    function updateProgressPanel(status, progress, message, jobType = currentJobType, job = null) {
      const metrics = estimateOperationalMetrics(progress, job);
      if (progressLabel) progressLabel.textContent = operationLabel(status, jobType);
      if (progressPercent) progressPercent.textContent = `${Math.round(progress)}%`;
      if (progressBar) progressBar.style.width = `${progress}%`;
      if (progressMessage) progressMessage.textContent = message || `Transferring data... (${Math.round(progress)}%)`;
      const fileCount = document.getElementById("operationFileCount");
      const speed = document.getElementById("operationSpeed");
      const eta = document.getElementById("operationEta");
      if (fileCount) fileCount.textContent = metrics.dataText;
      if (speed) speed.textContent = metrics.speed;
      if (eta) eta.textContent = metrics.eta;
    }

    function updateQueueCount() {
      const queueCount = document.getElementById("queueCount");
      const rows = document.querySelectorAll("#transferJobs tr[data-job]");
      if (queueCount) queueCount.textContent = rows.length.toString();
    }

    function updateQueueRow(job, source = sourcePath.value, destination = destPath.value) {
      const row = document.querySelector(`[data-job="${job.job_uuid}"]`);
      if (!row) return;
      const progress = job.status === "success" ? 100 : Math.round(Number(job.progress || 0));
      const metrics = estimateOperationalMetrics(progress, job);
      const status = job.status || "queued";
      const badge = row.querySelector("[data-queue-status]");
      const bar = row.querySelector(".progress-bar");
      const text = row.querySelector(".progress-text");
      const speed = row.querySelector("[data-queue-speed]");
      const sourceCell = row.querySelector("[data-queue-source]");
      const destCell = row.querySelector("[data-queue-destination]");
      if (sourceCell) sourceCell.textContent = formatPath(source);
      if (destCell) destCell.textContent = formatPath(destination);
      if (badge) {
        badge.className = `badge status-${status === "running" && currentJobType === "sync" ? "syncing" : status}`;
        badge.textContent = status === "running" && currentJobType === "sync" ? "Syncing" : status.charAt(0).toUpperCase() + status.slice(1);
      }
      if (bar) bar.style.width = `${progress}%`;
      if (text) text.textContent = `${progress}%`;
      if (speed) speed.textContent = metrics.speed;
    }

    async function createApiJob(payload, endpoint = "/api/file-manager/jobs") {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Operation failed.");
      }
      return response.json();
    }

    async function waitForJob(jobUuid) {
      for (let attempt = 0; attempt < 20; attempt++) {
        const response = await fetch(`/api/file-manager/jobs/${jobUuid}`);
        const job = await response.json();
        if (job.status === "success" || job.status === "failed") return job;
        await new Promise(r => setTimeout(r, 1000));
      }
      throw new Error("Job timeout.");
    }

    function renderRows(files, container, pathInput, statusEl, loadFn) {
      container.innerHTML = "";
      files.forEach(f => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td><button class="btn btn-link btn-sm p-0 text-start">${f.name}</button></td>
          <td class="small text-muted">${f.is_dir ? "Dir" : formatSize(f.size)}</td>
        `;
        tr.querySelector("button").onclick = () => {
          if (f.is_dir) {
            pathInput.value = f.path;
            loadFn();
          } else {
            pathInput.value = f.path;
          }
        };
        container.appendChild(tr);
      });
    }

    async function loadSource() {
      if (!sourceServer.value) return;
      try {
        sourceStatus.textContent = "Loading...";
        sourceRows.innerHTML = '<tr><td colspan="2" class="text-center py-4"><div class="spinner-border spinner-border-sm text-primary"></div></td></tr>';
        const job = await createApiJob({ job_type: "list", server_id: sourceServer.value, path: sourcePath.value || "/" });
        const res = await waitForJob(job.job_uuid);
        if (res.status === "failed") throw new Error(res.result?.error || "Listing failed");
        window.currentSourceFiles = res.result.files || [];
        renderRows(window.currentSourceFiles, sourceRows, sourcePath, sourceStatus, loadSource);
        sourceStatus.textContent = "Ready";
      } catch (e) { 
        sourceStatus.textContent = e.message;
        sourceRows.innerHTML = `<tr><td colspan="2" class="text-center py-4 text-danger">${e.message}</td></tr>`;
      }
    }

    async function loadDest() {
      if (!destServer.value) return;
      try {
        destStatus.textContent = "Loading...";
        destRows.innerHTML = '<tr><td colspan="2" class="text-center py-4"><div class="spinner-border spinner-border-sm text-primary"></div></td></tr>';
        const job = await createApiJob({ job_type: "list", server_id: destServer.value, path: destPath.value || "/" });
        const res = await waitForJob(job.job_uuid);
        if (res.status === "failed") throw new Error(res.result?.error || "Listing failed");
        renderRows(res.result.files || [], destRows, destPath, destStatus, loadDest);
        destStatus.textContent = "Ready";
      } catch (e) { 
        destStatus.textContent = e.message;
        destRows.innerHTML = `<tr><td colspan="2" class="text-center py-4 text-danger">${e.message}</td></tr>`;
      }
    }

    document.querySelectorAll("[data-job-type]").forEach(btn => {
      btn.onclick = () => {
        document.querySelectorAll("[data-job-type]").forEach(b => {
          b.classList.remove("active");
          b.setAttribute("aria-pressed", "false");
        });
        btn.classList.add("active");
        btn.setAttribute("aria-pressed", "true");
        currentJobType = btn.dataset.jobType;
      };
    });

    const progressContainer = document.getElementById("transferProgressContainer");
    const progressLabel = document.getElementById("transferStatusLabel");
    const progressPercent = document.getElementById("transferProgressPercent");
    const progressBar = document.getElementById("transferProgressBar");
    const progressMessage = document.getElementById("transferStatusMessage");

    const filterType = document.getElementById("filterType");
    const customPatternContainer = document.getElementById("customPatternContainer");
    const customPattern = document.getElementById("customPattern");
    const previewFilterBtn = document.getElementById("previewFilterBtn");
    const matchResultsContainer = document.getElementById("matchResultsContainer");

    if (filterType) {
      filterType.onchange = () => {
        if (filterType.value === "all") {
          customPatternContainer.style.display = "none";
          matchResultsContainer.style.display = "none";
        } else if (filterType.value === "custom") {
          customPatternContainer.style.display = "block";
          customPattern.value = "";
        } else {
          customPatternContainer.style.display = "none";
        }
      };
    }

    if (previewFilterBtn) {
      previewFilterBtn.onclick = async () => {
        if (filterType.value === "all") {
          matchResultsContainer.style.display = "none";
          return;
        }
        
        let pattern = filterType.value === "custom" ? customPattern.value : filterType.value;
        if (!pattern) return;

        previewFilterBtn.disabled = true;
        previewFilterBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Loading...';

        try {
          const response = await fetch("/api/filter-files", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              files: window.currentSourceFiles || [],
              pattern: pattern
            })
          });
          const data = await response.json();
          
          const tbody = document.getElementById("matchPreviewRows");
          tbody.innerHTML = "";
          
          if (data.matched.length === 0) {
            tbody.innerHTML = `<tr><td class="text-center text-warning py-3">No files matched the pattern</td></tr>`;
          } else {
            data.matched.forEach(f => {
               tbody.innerHTML += `<tr><td class="text-white">${f.name}</td><td class="text-end text-secondary">${formatSize(f.size)}</td></tr>`;
            });
          }
          
          document.getElementById("matchCountBadge").textContent = `${data.count} files`;
          const matchCountText = document.getElementById("matchCountText");
          if (matchCountText) matchCountText.textContent = data.count;
          const matchSizeText = document.getElementById("matchSizeText");
          if (matchSizeText) matchSizeText.textContent = formatSize(data.total_size);
          matchResultsContainer.style.display = "block";
          
          window.currentMatchedFiles = data.matched;
        } catch (e) {
          alert("Filter preview failed: " + e.message);
        } finally {
          previewFilterBtn.disabled = false;
          previewFilterBtn.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" fill="currentColor" class="me-2 mb-1" viewBox="0 0 16 16"><path d="M10.5 8a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0z"/><path d="M0 8s3-5.5 8-5.5S16 8 16 8s-3 5.5-8 5.5S0 8 0 8zm8 3.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z"/></svg>Preview';
        }
      };
    }

    function appendJobToTable(job, sourcePathVal, destPathVal) {
        const tr = document.createElement("tr");
        tr.setAttribute("data-job", job.job_uuid);
        tr.innerHTML = `
          <td><span class="operation-chip">${job.job_type}</span></td>
          <td class="truncate queue-path" data-queue-source title="${sourcePathVal}">${formatPath(sourcePathVal)}</td>
          <td class="truncate queue-path" data-queue-destination title="${destPathVal}">${formatPath(destPathVal)}</td>
          <td>
            <div class="queue-progress-wrap">
              <div class="progress"><div class="progress-bar" style="width:0%"></div></div>
              <span class="progress-text">0%</span>
            </div>
          </td>
          <td data-queue-speed>-- MB/s</td>
          <td><span class="badge status-queued" data-queue-status>Queued</span></td>
          <td class="text-secondary">${job.created_at ? formatTimestamp(new Date(job.created_at)) : formatTimestamp()}</td>
        `;
        const emptyQueue = document.getElementById("emptyQueue");
        if (emptyQueue) emptyQueue.style.display = "none";
        const container = document.getElementById("transferJobs");
        if (container) container.prepend(tr);
        updateQueueCount();
    }

    submitBtn.onclick = async () => {
      try {
        if (!sourceServer.value || !destServer.value || !sourcePath.value || !destPath.value) {
          alert("Please select servers and paths for both source and destination.");
          return;
        }

        const isFilterActive = filterType && filterType.value !== "all";
        if (isFilterActive) {
          if (!window.currentMatchedFiles || window.currentMatchedFiles.length === 0) {
            alert("No files matched the filter. Please adjust your pattern or preview first.");
            return;
          }
        }

        submitBtn.disabled = true;
        const originalBtnText = submitBtn.innerHTML;

        // 1. Validate Source Path
        try {
          submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Validating source...';
          const valJob = await createApiJob({
            job_type: "validate",
            server_id: sourceServer.value,
            path: sourcePath.value,
            expect_exists: true
          });
          const valRes = await waitForJob(valJob.job_uuid);
          if (valRes.status === "failed") {
            alert(`Error: The source path "${sourcePath.value}" does not exist on the source server. Please verify the path.`);
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
            return;
          }
        } catch (e) {
          alert(`Validation Error: ${e.message || e}. Please verify that the source server agent is online and the path is valid.`);
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalBtnText;
          return;
        }

        // 2. Validate Destination Path
        try {
          submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Validating destination...';
          const valJob = await createApiJob({
            job_type: "validate",
            server_id: destServer.value,
            path: destPath.value,
            expect_exists: true
          });
          const valRes = await waitForJob(valJob.job_uuid);
          if (valRes.status === "failed") {
            alert(`Error: The destination path "${destPath.value}" does not exist on the target server. Please verify the path.`);
            submitBtn.disabled = false;
            submitBtn.innerHTML = originalBtnText;
            return;
          }
        } catch (e) {
          alert(`Validation Error: ${e.message || e}. Please verify that the target server agent is online and the path is valid.`);
          submitBtn.disabled = false;
          submitBtn.innerHTML = originalBtnText;
          return;
        }

        submitBtn.innerHTML = originalBtnText;
        submitBtn.disabled = true;
        activeJobStartedAt = Date.now();
        setWorkflowActive(true, false);
        
        if (progressContainer) {
          progressContainer.classList.remove("d-none");
          updateProgressPanel("queued", 0, "Registering job(s) with control plane...");
          progressBar.style.width = "0%";
          progressBar.classList.add("progress-bar-animated", "progress-bar-striped");
          progressBar.classList.remove("bg-success", "bg-danger");
          progressBar.classList.add("bg-primary");
        }

        const conflictHandling = document.getElementById("conflictHandling")?.value || "overwrite";

        if (isFilterActive) {
          const submittedUuids = new Set();
          
          for (const f of window.currentMatchedFiles) {
             if (f.is_dir) continue;
             const job = await createApiJob({
                job_type: currentJobType,
                source_server_id: sourceServer.value,
                destination_server_id: destServer.value,
                source_path: f.path,
                destination_path: destPath.value,
                destination_is_dir: true,
                overwrite: conflictHandling !== "skip"
             }, "/api/jobs");
             submittedUuids.add(job.job_uuid);
             appendJobToTable(job, f.path, destPath.value);
          }
          
          if (progressMessage) progressMessage.textContent = `${submittedUuids.size} jobs queued. Waiting for agent...`;

          if (window.io && submittedUuids.size > 0) {
             const socket = io();
             let completed = 0;
             let failed = 0;
             socket.on("job:changed", (updatedJob) => {
                if (submittedUuids.has(updatedJob.job_uuid)) {
                   updateQueueRow(updatedJob);
                   if (updatedJob.status === "success") completed++;
                   if (updatedJob.status === "failed") failed++;
                   
                   const total = submittedUuids.size;
                   const done = completed + failed;
                   const progress = Math.round((done / total) * 100);
                   
                   if (progressMessage) {
                      if (done === total) {
                         const status = failed > 0 ? "failed" : "success";
                         updateProgressPanel(status, 100, `Completed ${completed} files, ${failed} failed.`, currentJobType);
                         progressBar.classList.remove("progress-bar-animated", "progress-bar-striped");
                         progressBar.classList.replace("bg-primary", status === "success" ? "bg-success" : "bg-danger");
                         submitBtn.disabled = false;
                         setWorkflowActive(false);
                      } else {
                         updateProgressPanel("running", progress, `Transferring ${done}/${total} files...`, currentJobType);
                      }
                   }
                }
             });
          } else {
             submitBtn.disabled = false;
             setWorkflowActive(false);
          }

        } else {
          // Standard single job
          const job = await createApiJob({
            job_type: currentJobType,
            source_server_id: sourceServer.value,
            destination_server_id: destServer.value,
            source_path: sourcePath.value,
            destination_path: destPath.value,
            destination_is_dir: document.getElementById("destinationIsDir")?.checked || false,
            overwrite: conflictHandling !== "skip"
          }, "/api/jobs");
          
          appendJobToTable(job, sourcePath.value, destPath.value);
          if (progressMessage) progressMessage.textContent = "Job queued. Waiting for agent...";

          if (window.io) {
            const socket = io();
            socket.on("job:changed", (updatedJob) => {
              if (updatedJob.job_uuid === job.job_uuid) {
                const progress = Math.round(updatedJob.progress || 0);
                updateQueueRow(updatedJob);
                
                if (progressMessage) {
                  if (updatedJob.status === "success") {
                    updateProgressPanel(updatedJob.status, 100, "Transfer completed successfully!", updatedJob.job_type || currentJobType, updatedJob);
                    progressBar.classList.remove("progress-bar-animated", "progress-bar-striped");
                    progressBar.classList.replace("bg-primary", "bg-success");
                    submitBtn.disabled = false;
                    setWorkflowActive(false);
                  } else if (updatedJob.status === "failed") {
                    updateProgressPanel(updatedJob.status, progress, `Error: ${updatedJob.message || "Transfer failed"}`, updatedJob.job_type || currentJobType, updatedJob);
                    progressBar.classList.remove("progress-bar-animated", "progress-bar-striped");
                    progressBar.classList.replace("bg-primary", "bg-danger");
                    submitBtn.disabled = false;
                    setWorkflowActive(false);
                  } else {
                    updateProgressPanel(updatedJob.status, progress, updatedJob.message || `Transferring data... (${progress}%)`, updatedJob.job_type || currentJobType, updatedJob);
                  }
                }
              }
            });
          }
        }

      } catch (e) { 
        alert(e.message); 
        submitBtn.disabled = false;
        setWorkflowActive(false);
        if (progressContainer) progressContainer.classList.add("d-none");
      }
    };

    const sourceOpen = document.getElementById("sourceOpen");
    if (sourceOpen) sourceOpen.onclick = loadSource;

    const sourceUp = document.getElementById("sourceUp");
    if (sourceUp) sourceUp.onclick = () => { 
      if (sourcePath.value) { sourcePath.value = parentPath(sourcePath.value); loadSource(); }
    };

    sourceServer.onchange = () => { 
      const opt = sourceServer.selectedOptions[0];
      if (opt && opt.value) {
        sourcePath.value = opt.dataset.basePath || "/";
        loadSource(); 
      }
    };

    const destOpen = document.getElementById("destOpen");
    if (destOpen) destOpen.onclick = loadDest;

    const destUp = document.getElementById("destUp");
    if (destUp) destUp.onclick = () => { 
      if (destPath.value) { destPath.value = parentPath(destPath.value); loadDest(); }
    };

    destServer.onchange = () => { 
      const opt = destServer.selectedOptions[0];
      if (opt && opt.value) {
        destPath.value = opt.dataset.basePath || "/";
        loadDest(); 
      }
    };

    if (sourceServer.value) loadSource();
    if (destServer.value) loadDest();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
