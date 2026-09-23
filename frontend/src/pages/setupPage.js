/**
 * =========================================================
 * Setup Wizard Page — 4-Step Guided Onboarding
 * =========================================================
 */

import { store } from "../store.js";
import { api } from "../api.js";
import { toast } from "../toast.js";
import { renderLogo } from "../components/logo.js";

export function renderSetupPage(container) {
  let selectedFile = null;
  let syncPollTimer = null;
  let authPollTimer = null;

  container.innerHTML = `
    <div class="setup-container">
      <div class="setup-header">
        <div class="setup-logo-badge">
          ${renderLogo(18, false)}
          <span>SETUP & ONBOARDING</span>
        </div>
        <h1 class="setup-title">Welcome to InboxIQ</h1>
        <p class="setup-subtitle">
          Complete the quick steps below to connect your local assistant to your Gmail account with read-only permissions.
        </p>
      </div>

      <div class="stepper-list">
        <!-- Step 1: Upload Credentials -->
        <div class="step-card active" id="step-1-card">
          <div class="step-header-row" data-step="1">
            <div class="step-title-group">
              <div class="step-index-badge" id="step-1-badge">1</div>
              <div class="step-name">Google OAuth Credentials</div>
            </div>
            <div class="step-status-chip" id="step-1-status">In Progress</div>
          </div>
          <div class="step-body" id="step-1-body">
            <p class="step-desc">
              Download your <code>credentials.json</code> from the <strong>Google Cloud Console</strong> 
              (OAuth 2.0 Client ID for <em>Desktop Application</em>) and upload it here.
            </p>
            <div class="dropzone" id="credentials-dropzone">
              <svg class="dropzone-icon" viewBox="0 0 24 24" fill="none" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path><polyline points="17 8 12 3 7 8"></polyline><line x1="12" y1="3" x2="12" y2="15"></line></svg>
              <div class="dropzone-text" id="dropzone-label">Click to select or drag & drop credentials.json</div>
              <div class="dropzone-sub">Accepts valid Google OAuth JSON files only</div>
              <input type="file" id="credentials-file-input" accept=".json,application/json" style="display: none;" />
            </div>
            <div id="file-preview-box" style="display: none;" class="file-preview">
              <span id="preview-filename">credentials.json</span>
              <button class="btn btn-primary" id="upload-creds-btn" style="padding: 4px 12px; font-size: 11px;">Upload & Save</button>
            </div>
          </div>
        </div>

        <!-- Step 2: Google Authentication -->
        <div class="step-card locked" id="step-2-card">
          <div class="step-header-row" data-step="2">
            <div class="step-title-group">
              <div class="step-index-badge" id="step-2-badge">2</div>
              <div class="step-name">Authenticate with Google</div>
            </div>
            <div class="step-status-chip" id="step-2-status">Locked</div>
          </div>
          <div class="step-body" id="step-2-body" style="display: none;">
            <p class="step-desc">
              Click below to launch Google's OAuth consent screen in your default browser. 
              Sign in with your Google account and grant <strong>read-only access</strong> to your Gmail inbox.
            </p>
            <div style="display: flex; align-items: center; gap: 12px;">
              <button class="btn btn-primary" id="start-auth-btn">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path><polyline points="10 17 15 12 10 7"></polyline><line x1="15" y1="12" x2="3" y2="12"></line></svg>
                <span>Connect Gmail Account</span>
              </button>
              <div id="auth-spinner-status" style="display: none; align-items: center; gap: 8px; font-size: 12px; color: var(--accent-green);" class="mono">
                <span class="spinner"></span>
                <span>Waiting for browser authorization...</span>
              </div>
            </div>
          </div>
        </div>

        <!-- Step 3: Initial Sync -->
        <div class="step-card locked" id="step-3-card">
          <div class="step-header-row" data-step="3">
            <div class="step-title-group">
              <div class="step-index-badge" id="step-3-badge">3</div>
              <div class="step-name">Initial Email Indexing</div>
            </div>
            <div class="step-status-chip" id="step-3-status">Locked</div>
          </div>
          <div class="step-body" id="step-3-body" style="display: none;">
            <p class="step-desc">
              Index recent email metadata into your local SQLite store. Only headers and snippets are fetched, 
              keeping bandwidth usage negligible.
            </p>
            <div class="sync-progress-box">
              <span class="spinner" id="step-sync-spinner" style="width: 24px; height: 24px; border-width: 3px;"></span>
              <div class="sync-status-details">
                <div style="font-weight: 600; font-size: 13px;" id="step-sync-heading">Ready to sync</div>
                <div class="mono" style="font-size: 11px; color: var(--text-secondary);" id="step-sync-sub">
                  Total indexed: <span class="text-green" id="step-sync-count">0</span> emails
                </div>
              </div>
              <button class="btn btn-primary" id="step-sync-action-btn" style="margin-left: auto;">
                Start Indexing
              </button>
            </div>
          </div>
        </div>

        <!-- Step 4: Ready -->
        <div class="step-card locked" id="step-4-card">
          <div class="step-header-row" data-step="4">
            <div class="step-title-group">
              <div class="step-index-badge" id="step-4-badge">4</div>
              <div class="step-name">Setup Complete</div>
            </div>
            <div class="step-status-chip" id="step-4-status">Pending</div>
          </div>
          <div class="step-body" id="step-4-body" style="display: none;">
            <div class="ready-box">
              <div class="ready-dial-icon">
                ${renderLogo(56, true)}
              </div>
              <div>
                <h3 style="font-size: 18px; font-weight: 700; margin-bottom: 4px;">InboxIQ is Ready</h3>
                <p class="step-desc">
                  Your credentials are saved, authentication is verified, and email metadata is indexed locally.
                </p>
              </div>
              <button class="btn btn-primary" id="finish-setup-btn" style="padding: 10px 24px; font-size: 14px;">
                Start Chatting →
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  `;

  // UI Element references
  const dropzone = container.querySelector("#credentials-dropzone");
  const fileInput = container.querySelector("#credentials-file-input");
  const filePreviewBox = container.querySelector("#file-preview-box");
  const previewFilename = container.querySelector("#preview-filename");
  const uploadCredsBtn = container.querySelector("#upload-creds-btn");
  const startAuthBtn = container.querySelector("#start-auth-btn");
  const authSpinnerStatus = container.querySelector("#auth-spinner-status");
  const stepSyncActionBtn = container.querySelector("#step-sync-action-btn");
  const stepSyncHeading = container.querySelector("#step-sync-heading");
  const stepSyncCount = container.querySelector("#step-sync-count");
  const finishSetupBtn = container.querySelector("#finish-setup-btn");

  // Dropzone drag-and-drop
  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dragover");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dragover"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dragover");
    if (e.dataTransfer.files.length) {
      handleFileChosen(e.dataTransfer.files[0]);
    }
  });

  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) {
      handleFileChosen(fileInput.files[0]);
    }
  });

  function handleFileChosen(file) {
    if (!file.name.endsWith(".json")) {
      toast.error("Please select a valid .json credentials file", "Invalid File");
      return;
    }
    selectedFile = file;
    previewFilename.textContent = file.name;
    filePreviewBox.style.display = "flex";
  }

  // Upload Credentials button
  uploadCredsBtn.addEventListener("click", async () => {
    if (!selectedFile) return;
    try {
      uploadCredsBtn.disabled = true;
      uploadCredsBtn.textContent = "Uploading...";
      await api.uploadCredentials(selectedFile);
      toast.success("Credentials saved successfully.", "Credentials Stored");
      await checkStatus();
    } catch (err) {
      toast.error(err.message, "Upload Failed");
    } finally {
      uploadCredsBtn.disabled = false;
      uploadCredsBtn.textContent = "Upload & Save";
    }
  });

  // Start Auth button
  startAuthBtn.addEventListener("click", async () => {
    try {
      startAuthBtn.disabled = true;
      authSpinnerStatus.style.display = "flex";
      await api.triggerAuth();
      toast.success("Google OAuth authorization verified!", "Connected");
      await checkStatus();
    } catch (err) {
      toast.error(err.message, "OAuth Error");
    } finally {
      startAuthBtn.disabled = false;
      authSpinnerStatus.style.display = "none";
    }
  });

  // Step 3 Sync Action button
  stepSyncActionBtn.addEventListener("click", async () => {
    try {
      stepSyncActionBtn.disabled = true;
      stepSyncHeading.textContent = "Sync in progress...";
      await api.triggerSync();
      toast.success("Initial synchronization job started.", "Sync Triggered");
      pollSyncStep();
    } catch (err) {
      toast.error(err.message, "Sync Failed");
      stepSyncActionBtn.disabled = false;
    }
  });

  function pollSyncStep() {
    if (syncPollTimer) clearInterval(syncPollTimer);
    syncPollTimer = setInterval(async () => {
      try {
        const syncStatus = await api.getSyncStatus();
        stepSyncCount.textContent = (syncStatus.total_emails || 0).toLocaleString();
        store.set("sync", syncStatus);

        if (!syncStatus.job_running) {
          clearInterval(syncPollTimer);
          stepSyncActionBtn.disabled = false;
          if (syncStatus.last_error) {
            stepSyncHeading.textContent = "Sync failed: " + syncStatus.last_error;
          } else {
            stepSyncHeading.textContent = `Completed! ${syncStatus.total_emails} emails indexed.`;
            toast.success("Mailbox indexing complete!", "Sync Done");
            await checkStatus();
          }
        }
      } catch (_) {}
    }, 2000);
  }

  // Finish setup button -> redirect to chat
  finishSetupBtn.addEventListener("click", () => {
    store.set("route", "chat");
  });

  // Helper to activate a step and collapse others
  function setStepState(stepNum, state) { // state: 'active' | 'completed' | 'locked'
    const card = container.querySelector(`#step-${stepNum}-card`);
    const badge = container.querySelector(`#step-${stepNum}-badge`);
    const statusChip = container.querySelector(`#step-${stepNum}-status`);
    const body = container.querySelector(`#step-${stepNum}-body`);

    if (!card) return;

    card.className = `step-card ${state}`;
    if (state === "completed") {
      badge.innerHTML = "✓";
      statusChip.className = "step-status-chip done";
      statusChip.textContent = "Done ✓";
      if (body) body.style.display = "none";
    } else if (state === "active") {
      badge.textContent = stepNum;
      statusChip.className = "step-status-chip";
      statusChip.textContent = "Active";
      if (body) body.style.display = "flex";
    } else {
      badge.textContent = stepNum;
      statusChip.className = "step-status-chip";
      statusChip.textContent = "Locked";
      if (body) body.style.display = "none";
    }
  }

  // Check setup status and advance stepper automatically
  async function checkStatus() {
    try {
      const status = await api.getSetupStatus();
      if (!status) return;

      // Step 1
      if (status.credentials_ok) {
        setStepState(1, "completed");
        // Step 2
        if (status.authenticated) {
          setStepState(2, "completed");
          // Step 3
          if (status.initial_sync_done) {
            setStepState(3, "completed");
            // Step 4
            setStepState(4, "active");
          } else {
            setStepState(3, "active");
            setStepState(4, "locked");
          }
        } else {
          setStepState(2, "active");
          setStepState(3, "locked");
          setStepState(4, "locked");
        }
      } else {
        setStepState(1, "active");
        setStepState(2, "locked");
        setStepState(3, "locked");
        setStepState(4, "locked");
      }
    } catch (e) {
      console.warn("Failed checking setup status:", e);
    }
  }

  // Run status probe on mount
  checkStatus();

  return () => {
    if (syncPollTimer) clearInterval(syncPollTimer);
    if (authPollTimer) clearInterval(authPollTimer);
  };
}
