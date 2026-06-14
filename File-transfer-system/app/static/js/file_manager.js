(function () {
  function init() {
    const serverSelect = document.getElementById("fileServer");
    const pathInput = document.getElementById("currentPath");
    const rows = document.getElementById("fileRows");
    const status = document.getElementById("fileStatus");

    if (!serverSelect || !pathInput || !rows) return;

    // Roles checks
    const userRoles = window.FileBridgeConfig?.userRoles || [];
    const hasWriteAccess = userRoles.includes('Super Admin') || userRoles.includes('Admin');

    const newFolderBtn = document.getElementById("newFolder");
    const fmUploadBtn = document.getElementById("fmUpload");
    if (!hasWriteAccess) {
      if (newFolderBtn) newFolderBtn.style.display = "none";
      if (fmUploadBtn) fmUploadBtn.style.display = "none";
    }

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
      if (size < 1024 * 1024 * 1024) return `${(size / 1024 / 1024).toFixed(1)} MB`;
      return `${(size / 1024 / 1024 / 1024).toFixed(1)} GB`;
    }

    async function createJob(payload) {
      const response = await fetch("/api/file-manager/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      if (!response.ok) {
        const text = await response.text();
        throw new Error(text || "Unable to queue file operation.");
      }
      return response.json();
    }

    async function waitForJob(jobUuid) {
      for (let attempt = 0; attempt < 18; attempt += 1) {
        const response = await fetch(`/api/file-manager/jobs/${jobUuid}`);
        const job = await response.json();
        if (job.status === "success" || job.status === "failed") return job;
        await new Promise((resolve) => setTimeout(resolve, 1500));
      }
      throw new Error("Agent did not finish the operation in time.");
    }

    function renderFiles(files) {
      rows.innerHTML = "";
      files.forEach((file) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td><button class="btn btn-link btn-sm text-start file-open">${file.name}</button></td>
          <td>${file.is_dir ? "Folder" : "File"}</td>
          <td>${file.is_dir ? "-" : formatSize(file.size)}</td>
          <td>${file.modified_at || "-"}</td>
          <td class="text-end">
            ${hasWriteAccess ? `
            <button class="btn btn-outline-secondary btn-sm file-rename">Rename</button>
            <button class="btn btn-outline-danger btn-sm file-delete">Delete</button>
            ` : `<span class="text-secondary small">View Only</span>`}
          </td>`;
        row.querySelector(".file-open").addEventListener("click", () => {
          if (file.is_dir) {
            pathInput.value = file.path;
            loadFiles();
          }
        });
        if (hasWriteAccess) {
          row.querySelector(".file-delete").addEventListener("click", () => runAction("delete", file.path));
          row.querySelector(".file-rename").addEventListener("click", () => {
            const destination = prompt("New full path", file.path);
            if (destination) runAction("rename", file.path, destination);
          });
        }
        rows.appendChild(row);
      });
    }

    async function runAction(jobType, path, destinationPath) {
      try {
        status.textContent = `${jobType} queued...`;
        const job = await createJob({
          job_type: jobType,
          server_id: serverSelect.value,
          path,
          destination_path: destinationPath || ""
        });
        const result = await waitForJob(job.job_uuid);
        if (result.status !== "success") throw new Error(result.message || "Operation failed.");
        status.textContent = result.message || "Operation completed.";
        loadFiles();
      } catch (error) {
        status.textContent = error.message;
      }
    }

    async function loadFiles() {
      if (!serverSelect.value) return;
      try {
        status.textContent = "Loading files from agent...";
        rows.innerHTML = '<tr><td colspan="5" class="text-center py-4"><div class="spinner-border spinner-border-sm text-primary"></div></td></tr>';
        const job = await createJob({ job_type: "list", server_id: serverSelect.value, path: pathInput.value || "/" });
        const result = await waitForJob(job.job_uuid);
        if (result.status !== "success") throw new Error(result.message || result.result?.error || "Unable to list files.");
        renderFiles((result.result && result.result.files) || []);
        status.textContent = result.message || "Files loaded.";
      } catch (error) {
        status.textContent = error.message;
        rows.innerHTML = `<tr><td colspan="5" class="text-center py-4 text-danger">${error.message}</td></tr>`;
      }
    }

    const refreshBtn = document.getElementById("refreshFiles");
    if (refreshBtn) refreshBtn.addEventListener("click", loadFiles);

    const openPathBtn = document.getElementById("openPath");
    if (openPathBtn) openPathBtn.addEventListener("click", loadFiles);

    const goUpBtn = document.getElementById("goUp");
    if (goUpBtn) {
      goUpBtn.addEventListener("click", () => {
        pathInput.value = parentPath(pathInput.value);
        loadFiles();
      });
    }

    const newFolderBtn = document.getElementById("newFolder");
    if (newFolderBtn) {
      newFolderBtn.addEventListener("click", () => {
        const name = prompt("Folder name");
        if (name) runAction("mkdir", joinPath(pathInput.value, name));
      });
    }

    serverSelect.addEventListener("change", () => {
      const opt = serverSelect.selectedOptions[0];
      if (opt && opt.value) {
        pathInput.value = opt.dataset.basePath || "/";
        loadFiles();
      }
    });

    if (serverSelect.value) loadFiles();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
