/**
 * =========================================================
 * Startup Screen Page — Real-time Component Bootloader
 * =========================================================
 */

import { api } from "../api.js";
import { renderLogo } from "../components/logo.js";

export function renderStartupPage(container, onComplete) {
  let pollInterval = null;
  let isDone = false;

  container.innerHTML = `
    <div class="startup-container">
      <div class="startup-card">
        <div class="startup-logo">
          ${renderLogo(56, true)}
        </div>

        <div class="startup-header">
          <h1 class="startup-title">Starting InboxIQ</h1>
          <p class="startup-subtitle">
            Initializing local AI runtime, database, and hardware acceleration...
          </p>
        </div>

        <div class="startup-steps" id="startup-steps-list">
          <!-- Step rows will be rendered here dynamically -->
        </div>

        <div class="startup-footer">
          <div class="live-status-pill">
            <span class="spinner" id="startup-global-spinner"></span>
            <span id="startup-global-message">Booting services...</span>
          </div>
          <span class="mono">localhost:8000</span>
        </div>
      </div>
    </div>
  `;

  const stepsList = container.querySelector("#startup-steps-list");
  const globalSpinner = container.querySelector("#startup-global-spinner");
  const globalMessage = container.querySelector("#startup-global-message");

  function updateSteps(steps) {
    steps.forEach((step) => {
      let row = stepsList.querySelector(`#step-${step.id}`);
      if (!row) {
        row = document.createElement("div");
        row.id = `step-${step.id}`;
        row.className = `startup-step-row ${step.status}`;
        row.innerHTML = `
          <div class="step-info">
            <span class="step-title">${step.label}</span>
            <span class="step-message">${step.message || ""}</span>
          </div>
          <div class="step-indicator" data-status="${step.status}">
            <span class="pending-dot"></span>
          </div>
        `;
        stepsList.appendChild(row);
      }

      // Update row class if status changed
      const expectedRowClass = `startup-step-row ${step.status}`;
      if (row.className !== expectedRowClass) {
        row.className = expectedRowClass;
      }

      // Update message text
      const msgEl = row.querySelector(".step-message");
      if (msgEl && msgEl.textContent !== (step.message || "")) {
        msgEl.textContent = step.message || "";
      }

      // Update status indicator
      const indicator = row.querySelector(".step-indicator");
      if (indicator && indicator.dataset.status !== step.status) {
        indicator.dataset.status = step.status;
        if (step.status === "in_progress") {
          indicator.innerHTML = `<span class="spinner" style="width: 14px; height: 14px;"></span>`;
        } else if (step.status === "completed") {
          indicator.innerHTML = `<span class="check">✓</span>`;
        } else if (step.status === "failed") {
          indicator.innerHTML = `<span class="cross">✕</span>`;
        } else {
          indicator.innerHTML = `<span class="pending-dot"></span>`;
        }
      }

      // Update progress bar
      const infoEl = row.querySelector(".step-info");
      let progressWrapper = row.querySelector(".step-progress-wrapper");

      if (step.status === "in_progress" && step.progress && typeof step.progress.percent === "number") {
        const pct = Math.min(Math.max(step.progress.percent, 0), 100);
        const downloadedStr = step.progress.downloaded_str || "";
        const totalStr = step.progress.total_str || "";
        const speedStr = step.progress.speed_str || "";

        if (!progressWrapper) {
          progressWrapper = document.createElement("div");
          progressWrapper.className = "step-progress-wrapper";
          progressWrapper.innerHTML = `
            <div class="step-progress-track">
              <div class="step-progress-fill" style="width: 0%;"></div>
            </div>
            <div class="step-progress-meta">
              <span class="step-progress-size"></span>
              <span class="step-progress-speed"></span>
              <span class="step-progress-pct"></span>
            </div>
          `;
          infoEl.appendChild(progressWrapper);
        }

        const fillEl = progressWrapper.querySelector(".step-progress-fill");
        const sizeEl = progressWrapper.querySelector(".step-progress-size");
        const speedEl = progressWrapper.querySelector(".step-progress-speed");
        const pctEl = progressWrapper.querySelector(".step-progress-pct");

        if (fillEl) fillEl.style.width = `${pct}%`;
        if (sizeEl) sizeEl.textContent = `${downloadedStr}${totalStr ? " / " + totalStr : ""}`;
        if (speedEl) speedEl.textContent = speedStr;
        if (pctEl) pctEl.textContent = `${pct.toFixed(1)}%`;
      } else if (progressWrapper) {
        progressWrapper.remove();
      }
    });
  }

  async function checkStartup() {
    try {
      const data = await api.getStartupStatus();
      if (!data) return;

      if (data.steps && data.steps.length) {
        updateSteps(data.steps);
      }

      if (data.message) {
        globalMessage.textContent = data.message;
      }

      if (data.error) {
        globalMessage.textContent = `Error: ${data.error}`;
        globalMessage.style.color = "var(--color-danger)";
        if (globalSpinner) globalSpinner.style.display = "none";
        clearInterval(pollInterval);
        return;
      }

      if (data.completed && !isDone) {
        isDone = true;
        clearInterval(pollInterval);
        globalMessage.textContent = "All systems operational! Starting app...";
        if (globalSpinner) globalSpinner.style.display = "none";

        // Brief delay for visual satisfaction before transitioning
        setTimeout(() => {
          if (onComplete) onComplete();
        }, 600);
      }
    } catch (err) {
      globalMessage.textContent = "Connecting to backend...";
    }
  }

  // Initial check and start fast polling for smooth progress
  checkStartup();
  pollInterval = setInterval(checkStartup, 400);

  return () => {
    if (pollInterval) clearInterval(pollInterval);
  };
}
