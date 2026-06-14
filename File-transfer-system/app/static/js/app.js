(function () {
  const socket = window.io ? io() : null;

  function setTheme(theme) {
    document.documentElement.setAttribute("data-bs-theme", theme);
    localStorage.setItem("filebridge-theme", theme);
  }

  setTheme(localStorage.getItem("filebridge-theme") || "dark");

  const themeToggle = document.getElementById("themeToggle");
  if (themeToggle) {
    themeToggle.addEventListener("click", () => {
      const current = document.documentElement.getAttribute("data-bs-theme") || "light";
      setTheme(current === "light" ? "dark" : "light");
    });
  }

  function updateJobRow(job) {
    const row = document.querySelector(`[data-job="${job.job_uuid}"]`);
    if (!row) return;

    const progress = job.status === "success" ? 100 : Number(job.progress || 0);
    
    // Update status badge
    const statusBadge = row.querySelector(".status-badge");
    if (statusBadge) {
      statusBadge.className = `badge status-badge status-${job.status}`;
      statusBadge.textContent = job.status.charAt(0).toUpperCase() + job.status.slice(1);
    }

    // Update progress bar
    const progressBar = row.querySelector(".progress-bar");
    if (progressBar) {
      progressBar.style.width = `${progress}%`;
      // Target the percentage text specifically by looking for the one that already has a % or is the last small element
      const progressText = row.querySelector(".progress-text");
      if (progressText) {
        progressText.textContent = `${Math.round(progress)}%`;
      }
    }

    // Update started and completed times
    const startedCell = row.querySelector(".started-cell");
    if (startedCell) {
      if (job.started_at) {
        startedCell.setAttribute("data-utc", job.started_at);
        const format = startedCell.getAttribute("data-format") || "datetime";
        const dateObj = new Date(job.started_at);
        let formatted = "";
        if (format === "time") {
          formatted = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                      dateObj.getMinutes().toString().padStart(2, '0') + ':' + 
                      dateObj.getSeconds().toString().padStart(2, '0');
        } else if (format === "datetime-seconds") {
          const d = dateObj.getFullYear() + '-' + 
                    String(dateObj.getMonth() + 1).padStart(2, '0') + '-' + 
                    String(dateObj.getDate()).padStart(2, '0');
          const t = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                    dateObj.getMinutes().toString().padStart(2, '0') + ':' + 
                    dateObj.getSeconds().toString().padStart(2, '0');
          formatted = `${d} ${t}`;
        } else if (format === "datetime-seconds-twoline") {
          const d = String(dateObj.getDate()).padStart(2, '0') + '-' + 
                    String(dateObj.getMonth() + 1).padStart(2, '0') + '-' + 
                    dateObj.getFullYear();
          const t = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                    dateObj.getMinutes().toString().padStart(2, '0') + ':' + 
                    dateObj.getSeconds().toString().padStart(2, '0');
          startedCell.innerHTML = `<div>${t}</div><div>${d}</div>`;
        } else {
          const d = dateObj.getFullYear() + '-' + 
                    String(dateObj.getMonth() + 1).padStart(2, '0') + '-' + 
                    String(dateObj.getDate()).padStart(2, '0');
          const t = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                    dateObj.getMinutes().toString().padStart(2, '0');
          formatted = `${d} ${t}`;
        }
        if (format !== "datetime-seconds-twoline") {
          startedCell.textContent = formatted;
        }
      } else {
        startedCell.removeAttribute("data-utc");
        startedCell.textContent = "-";
      }
    }

    const completedCell = row.querySelector(".completed-cell");
    if (completedCell) {
      if (job.completed_at) {
        completedCell.setAttribute("data-utc", job.completed_at);
        const format = completedCell.getAttribute("data-format") || "datetime";
        const dateObj = new Date(job.completed_at);
        let formatted = "";
        if (format === "time") {
          formatted = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                      dateObj.getMinutes().toString().padStart(2, '0') + ':' + 
                      dateObj.getSeconds().toString().padStart(2, '0');
        } else if (format === "datetime-seconds") {
          const d = dateObj.getFullYear() + '-' + 
                    String(dateObj.getMonth() + 1).padStart(2, '0') + '-' + 
                    String(dateObj.getDate()).padStart(2, '0');
          const t = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                    dateObj.getMinutes().toString().padStart(2, '0') + ':' + 
                    dateObj.getSeconds().toString().padStart(2, '0');
          formatted = `${d} ${t}`;
        } else if (format === "datetime-seconds-twoline") {
          const d = String(dateObj.getDate()).padStart(2, '0') + '-' + 
                    String(dateObj.getMonth() + 1).padStart(2, '0') + '-' + 
                    dateObj.getFullYear();
          const t = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                    dateObj.getMinutes().toString().padStart(2, '0') + ':' + 
                    dateObj.getSeconds().toString().padStart(2, '0');
          completedCell.innerHTML = `<div>${t}</div><div>${d}</div>`;
        } else {
          const d = dateObj.getFullYear() + '-' + 
                    String(dateObj.getMonth() + 1).padStart(2, '0') + '-' + 
                    String(dateObj.getDate()).padStart(2, '0');
          const t = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                    dateObj.getMinutes().toString().padStart(2, '0');
          formatted = `${d} ${t}`;
        }
        if (format !== "datetime-seconds-twoline") {
          completedCell.textContent = formatted;
        }
      } else {
        completedCell.removeAttribute("data-utc");
        completedCell.textContent = "-";
      }
    }
  }

  if (socket) {
    socket.on("job:changed", updateJobRow);
    socket.on("job:progress", (data) => {
      // Sometimes progress is sent separately
      updateJobRow({ job_uuid: data.job_uuid, progress: data.progress, status: data.status || "running" });
    });
    socket.on("alert:new", (alert) => {
      console.info("New alert", alert);
    });
    socket.on("agents:status", (status) => {
      const onlineAgents = document.getElementById("onlineAgents");
      if (onlineAgents) {
        onlineAgents.textContent = status.online_agents;
      }
      if (Array.isArray(status.agents)) {
        status.agents.forEach(updateAgentCard);
      }
    });
    socket.on("agent:heartbeat", updateAgentCard);
    socket.on("agent:changed", updateAgentCard);
    socket.on("activity:new", () => {
      const feed = document.getElementById("activityFeed");
      if (feed) {
        feed.dataset.dirty = "true";
      }
    });
  }

  function updateAgentCard(agent) {
    if (!agent || !agent.agent_uuid) return;
    const card = document.querySelector(`[data-agent-card="${agent.agent_uuid}"]`);
    if (!card) return;
    const badge = card.querySelector(".badge");
    if (badge) {
      badge.className = `badge status-${agent.status}`;
      badge.textContent = agent.status;
    }
    const dot = card.querySelector(".agent-dot");
    if (dot) dot.className = `agent-dot status-${agent.status}`;
    const metrics = agent.metrics || {};
    const values = card.querySelectorAll(".metric-grid strong");
    const nextValues = [
      `${metrics.cpu_percent || 0}%`,
      `${metrics.ram_percent || 0}%`,
      `${metrics.disk_percent || 0}%`,
      `${metrics.queue_depth || 0}`,
    ];
    values.forEach((node, index) => {
      node.textContent = nextValues[index] || node.textContent;
    });
    const diskBar = card.querySelector(".progress-bar");
    if (diskBar) diskBar.style.width = `${metrics.disk_percent || 0}%`;
  }

  const agentSearch = document.getElementById("agentSearch");
  if (agentSearch) {
    agentSearch.addEventListener("input", () => {
      const needle = agentSearch.value.trim().toLowerCase();
      document.querySelectorAll(".agent-card-wrap").forEach(card => {
        const haystack = card.getAttribute("data-agent-search") || "";
        card.classList.toggle("d-none", needle && !haystack.includes(needle));
      });
    });
  }

  document.querySelectorAll(".sync-schedule .btn").forEach(button => {
    button.addEventListener("click", () => {
      document.querySelectorAll(".sync-schedule .btn").forEach(btn => btn.classList.remove("active"));
      button.classList.add("active");
    });
  });

  let sessionWarningTimer;
  let sessionTimeoutTimer;

  function resetSessionTimers() {
    if (sessionWarningTimer) clearTimeout(sessionWarningTimer);
    if (sessionTimeoutTimer) clearTimeout(sessionTimeoutTimer);

    const sessionModalEl = document.getElementById("sessionModal");
    if (sessionModalEl && window.bootstrap && window.FileBridgeConfig) {
      const sessionModal = bootstrap.Modal.getInstance(sessionModalEl) || new bootstrap.Modal(sessionModalEl);
      
      sessionWarningTimer = setTimeout(() => {
        sessionModal.show();
      }, window.FileBridgeConfig.sessionWarningMs);

      sessionTimeoutTimer = setTimeout(() => {
        window.location.href = "/logout";
      }, window.FileBridgeConfig.sessionTimeoutMs);
    }
  }

  // Reset timers on load and on common user interactions
  resetSessionTimers();
  ["click", "mousemove", "keypress", "touchstart"].forEach(evt => {
    document.addEventListener(evt, resetSessionTimers, { passive: true });
  });

  // Global Refresh Button
  const globalRefreshBtn = document.getElementById("globalRefreshBtn");
  if (globalRefreshBtn) {
    globalRefreshBtn.addEventListener("click", function() {
      const icon = document.getElementById("refreshIcon");
      const text = document.getElementById("refreshText");
      if (icon) icon.classList.add("spin-animation");
      if (text) text.textContent = "Refreshing...";
      this.disabled = true;
      setTimeout(() => {
        location.reload();
      }, 300);
    });
  }

  function convertUtcToLocal() {
    const elements = document.querySelectorAll(".local-time");
    elements.forEach(el => {
      const utcStr = el.getAttribute("data-utc");
      if (!utcStr) return;
      
      const format = el.getAttribute("data-format") || "datetime";
      const dateObj = new Date(utcStr);
      if (isNaN(dateObj.getTime())) return;
      
      let formatted = "";
      if (format === "time") {
        formatted = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                    dateObj.getMinutes().toString().padStart(2, '0') + ':' + 
                    dateObj.getSeconds().toString().padStart(2, '0');
      } else if (format === "short-time") {
        formatted = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                    dateObj.getMinutes().toString().padStart(2, '0');
      } else if (format === "datetime") {
        const d = dateObj.getFullYear() + '-' + 
                  String(dateObj.getMonth() + 1).padStart(2, '0') + '-' + 
                  String(dateObj.getDate()).padStart(2, '0');
        const t = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                  dateObj.getMinutes().toString().padStart(2, '0');
        formatted = `${d} ${t}`;
      } else if (format === "datetime-seconds") {
        const d = dateObj.getFullYear() + '-' + 
                  String(dateObj.getMonth() + 1).padStart(2, '0') + '-' + 
                  String(dateObj.getDate()).padStart(2, '0');
        const t = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                  dateObj.getMinutes().toString().padStart(2, '0') + ':' + 
                  dateObj.getSeconds().toString().padStart(2, '0');
        formatted = `${d} ${t}`;
      } else if (format === "datetime-seconds-twoline") {
        const d = String(dateObj.getDate()).padStart(2, '0') + '-' + 
                  String(dateObj.getMonth() + 1).padStart(2, '0') + '-' + 
                  dateObj.getFullYear();
        const t = dateObj.getHours().toString().padStart(2, '0') + ':' + 
                  dateObj.getMinutes().toString().padStart(2, '0') + ':' + 
                  dateObj.getSeconds().toString().padStart(2, '0');
        el.innerHTML = `<div>${t}</div><div>${d}</div>`;
        return;
      } else if (format === "date") {
        formatted = dateObj.getFullYear() + '-' + 
                    String(dateObj.getMonth() + 1).padStart(2, '0') + '-' + 
                    String(dateObj.getDate()).padStart(2, '0');
      }
      
      el.textContent = formatted;
    });
  }

  // Call it immediately to localize server-rendered times
  convertUtcToLocal();
})();
