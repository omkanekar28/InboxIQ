/**
 * =========================================================
 * Settings Page — Model Switcher, Hardware Guard & Readout
 * =========================================================
 */

import { store } from "../store.js";
import { api } from "../api.js";
import { toast } from "../toast.js";

export function renderSettingsPage(container) {
  let isSwitching = false;

  container.innerHTML = `
    <div class="settings-container">
      <!-- Section 1: Model Selection -->
      <section class="settings-section">
        <div class="section-header">
          <h2 class="section-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2a10 10 0 1 0 10 10H12V2z"></path><path d="M12 2a10 10 0 0 1 10 10h-10V2z"></path><path d="M12 12 2.1 12a10 10 0 0 0 19.8 0H12z"></path></svg>
            AI Model Selection
          </h2>
          <p class="section-desc">
            Switch between local GGUF models running in the background via llama.cpp. No cloud tokens are consumed.
          </p>
        </div>

        <div class="models-grid">
          <!-- Lightweight Model Card -->
          <div class="model-card active" id="card-lightweight">
            <div class="model-card-header">
              <div>
                <div class="model-name">
                  <span>Lightweight</span>
                  <span class="status-dot green" id="dot-lightweight" style="width: 6px; height: 6px;"></span>
                </div>
                <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">Liquid AI LFM2.5 1.2B Thinking</div>
              </div>
              <span class="model-param-badge">1.2B Params</span>
            </div>

            <p class="model-desc">
              Ultra-fast local model with native thinking and rapid tool-calling capabilities. Optimized for quick searches, 
              low latency, and standard CPU or laptop hardware.
            </p>

            <div class="model-specs">
              <div class="spec-item"><span>VRAM / RAM:</span> <span>~1.2 GB</span></div>
              <div class="spec-item"><span>Hardware Req:</span> <span>Any CPU or GPU</span></div>
              <div class="spec-item"><span>Context:</span> <span>16,000 tokens</span></div>
            </div>

            <button class="btn btn-primary" id="btn-select-lightweight" style="width: 100%;">
              Active Model
            </button>
          </div>

          <!-- Balanced Model Card -->
          <div class="model-card" id="card-balanced">
            <div class="model-card-header">
              <div>
                <div class="model-name">
                  <span>Balanced</span>
                  <span class="status-dot" id="dot-balanced" style="width: 6px; height: 6px;"></span>
                </div>
                <div style="font-size: 11px; color: var(--text-muted); margin-top: 2px;">Liquid AI LFM2.5 2.6B</div>
              </div>
              <span class="model-param-badge">2.6B Params</span>
            </div>

            <p class="model-desc">
              Efficient multi-turn reasoning and synthesis model. Delivers deep multi-turn reasoning, complex thread 
              synthesis, and advanced query disambiguation.
            </p>

            <div class="model-specs">
              <div class="spec-item"><span>VRAM Required:</span> <span>~2.6 GB Dedicated</span></div>
              <div class="spec-item"><span>Hardware Req:</span> <span>NVIDIA GPU (CUDA)</span></div>
              <div class="spec-item"><span>Context:</span> <span>16,000 tokens</span></div>
            </div>

            <div id="balanced-guard-warning" class="hardware-guard-warning" style="display: none;">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>
              <span>Requires NVIDIA GPU. Disabled to prevent slow CPU inference.</span>
            </div>

            <button class="btn btn-secondary" id="btn-select-balanced" style="width: 100%;">
              Switch to Balanced
            </button>
          </div>
        </div>
      </section>

      <!-- Section 2: Hardware Profile Terminal Readout -->
      <section class="settings-section">
        <div class="section-header">
          <h2 class="section-title">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="14" rx="2" ry="2"></rect><line x1="8" y1="21" x2="16" y2="21"></line><line x1="12" y1="17" x2="12" y2="21"></line></svg>
            System & Hardware Profile
          </h2>
          <p class="section-desc">
            Hardware acceleration detected by the local llama-server backend.
          </p>
        </div>

        <div class="terminal-card">
          <div class="terminal-header">
            <div class="terminal-dots">
              <span class="term-dot green"></span>
              <span class="term-dot"></span>
              <span class="term-dot"></span>
            </div>
            <span>$ inboxiq sysinfo --probe-hardware</span>
          </div>

          <div class="terminal-grid">
            <div class="term-item">
              <span class="term-label">ACCELERATION</span>
              <span class="term-value" id="term-accel">Probing...</span>
            </div>

            <div class="term-item">
              <span class="term-label">GPU DEVICE</span>
              <span class="term-value" id="term-gpu-name">Probing...</span>
            </div>

            <div class="term-item">
              <span class="term-label">DEDICATED VRAM</span>
              <span class="term-value" id="term-vram">Probing...</span>
            </div>

            <div class="term-item">
              <span class="term-label">SERVER RUNTIME</span>
              <span class="term-value">llama.cpp b11050 (Win-x64)</span>
            </div>

            <div class="term-item">
              <span class="term-label">CONTEXT WINDOW</span>
              <span class="term-value">16,000 tokens (512 batch)</span>
            </div>

            <div class="term-item">
              <span class="term-label">STORAGE ENGINE</span>
              <span class="term-value">SQLite (inboxiq.db)</span>
            </div>
          </div>
        </div>
      </section>
    </div>
  `;

  const cardLightweight = container.querySelector("#card-lightweight");
  const cardBalanced = container.querySelector("#card-balanced");
  const btnLightweight = container.querySelector("#btn-select-lightweight");
  const btnBalanced = container.querySelector("#btn-select-balanced");
  const dotLightweight = container.querySelector("#dot-lightweight");
  const dotBalanced = container.querySelector("#dot-balanced");
  const balancedWarning = container.querySelector("#balanced-guard-warning");

  const termAccel = container.querySelector("#term-accel");
  const termGpuName = container.querySelector("#term-gpu-name");
  const termVram = container.querySelector("#term-vram");

  // Model switch handler
  async function handleSwitch(targetModel) {
    if (isSwitching) return;
    try {
      isSwitching = true;
      const targetBtn = targetModel === "balanced" ? btnBalanced : btnLightweight;
      targetBtn.disabled = true;
      targetBtn.innerHTML = `<span class="spinner"></span> Switching runtime...`;

      await api.switchModel(targetModel);
      toast.success(`Switched active model to ${targetModel}`, "Model Changed");
      await store.refreshHealth();
      await store.refreshHardware();
    } catch (err) {
      toast.error(err.message, "Model Switch Failed");
    } finally {
      isSwitching = false;
      renderActiveModelCards();
    }
  }

  btnLightweight.addEventListener("click", () => handleSwitch("lightweight"));
  btnBalanced.addEventListener("click", () => handleSwitch("balanced"));

  function renderActiveModelCards() {
    const currentModel = store.get("health")?.active_model || "lightweight";
    const hardware = store.get("hardware") || {};

    if (currentModel === "lightweight") {
      cardLightweight.className = "model-card active";
      btnLightweight.className = "btn btn-primary";
      btnLightweight.textContent = "Active Model";
      btnLightweight.disabled = true;
      dotLightweight.className = "status-dot green";

      cardBalanced.className = "model-card";
      btnBalanced.className = "btn btn-secondary";
      btnBalanced.textContent = "Switch to Balanced";
      btnBalanced.disabled = false;
      dotBalanced.className = "status-dot";
    } else {
      cardBalanced.className = "model-card active";
      btnBalanced.className = "btn btn-primary";
      btnBalanced.textContent = "Active Model";
      btnBalanced.disabled = true;
      dotBalanced.className = "status-dot green";

      cardLightweight.className = "model-card";
      btnLightweight.className = "btn btn-secondary";
      btnLightweight.textContent = "Switch to Lightweight";
      btnLightweight.disabled = false;
      dotLightweight.className = "status-dot";
    }

    // Hardware Guard: Disable Balanced if no GPU
    if (!hardware.gpu_available) {
      if (currentModel !== "balanced") {
        cardBalanced.classList.add("disabled");
        btnBalanced.disabled = true;
        btnBalanced.textContent = "GPU Required";
        balancedWarning.style.display = "flex";
      }
    } else {
      balancedWarning.style.display = "none";
    }

    // Terminal Readout Updates
    termAccel.textContent = hardware.gpu_available ? "NVIDIA CUDA (Full Layer Offload)" : "CPU Fallback (4 Threads)";
    termGpuName.textContent = hardware.gpu_name || "None (CPU Only)";
    termVram.textContent = hardware.vram_mb ? `${hardware.vram_mb.toLocaleString()} MB` : "N/A (Host RAM)";
  }

  store.subscribe("health", renderActiveModelCards);
  store.subscribe("hardware", renderActiveModelCards);

  // Trigger initial hardware probe
  store.refreshHardware();
}
