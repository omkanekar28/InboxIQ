/**
 * =========================================================
 * Sidebar Component — Navigation & Live Status Footer
 * =========================================================
 */

import { store } from "../store.js";
import { api } from "../api.js";
import { toast } from "../toast.js";
import { renderLogo } from "./logo.js";

export function renderSidebar(container) {
  container.innerHTML = `
    <aside class="app-sidebar">
      <!-- Top Brand Header -->
      <div class="sidebar-header">
        ${renderLogo(32, true)}
        <div class="brand-info">
          <div class="brand-title">
            InboxIQ
            <span class="brand-badge">LOCAL</span>
          </div>
          <div class="brand-subtitle">AI Email Assistant</div>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <nav class="sidebar-nav">
        <a class="nav-link" data-route="chat">
          <svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
          <span>Chat</span>
        </a>
        <a class="nav-link" data-route="settings">
          <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"></circle><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z"></path></svg>
          <span>Settings</span>
        </a>
        <a class="nav-link" data-route="setup">
          <svg viewBox="0 0 24 24"><polygon points="12 2 2 7 12 12 22 7 12 2"></polygon><polyline points="2 17 12 22 22 17"></polyline><polyline points="2 12 12 17 22 12"></polyline></svg>
          <span>Setup Wizard</span>
        </a>
      </nav>

      <!-- Live Status Footer -->
      <div class="sidebar-footer">
        <div class="status-row">
          <span class="status-label">
            <span class="status-dot" id="footer-llm-dot"></span>
            LLM Runtime
          </span>
          <span class="status-value" id="footer-llm-text">Checking</span>
        </div>

        <div class="status-row">
          <span class="status-label">
            <span class="status-dot" id="footer-sync-dot"></span>
            Gmail Sync
          </span>
          <span class="status-value" id="footer-sync-text">Idle</span>
        </div>

        <div class="status-row">
          <span class="status-label">Indexed Emails</span>
          <span class="status-value text-green" id="footer-emails-count">0</span>
        </div>

        <button class="btn btn-outline-green footer-sync-btn" id="footer-sync-btn">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
          <span id="footer-sync-btn-label">Sync Now</span>
        </button>
      </div>
    </aside>
  `;

  // Attach nav handlers
  const navLinks = container.querySelectorAll(".nav-link");
  navLinks.forEach((link) => {
    link.addEventListener("click", () => {
      const targetRoute = link.getAttribute("data-route");
      store.set("route", targetRoute);
    });
  });

  // Attach sync button handler
  const syncBtn = container.querySelector("#footer-sync-btn");
  const syncBtnLabel = container.querySelector("#footer-sync-btn-label");
  syncBtn.addEventListener("click", async () => {
    try {
      syncBtn.disabled = true;
      syncBtnLabel.textContent = "Syncing...";
      await api.triggerSync();
      toast.success("Background Gmail sync started.", "Sync Triggered");
      store.refreshSync();
    } catch (err) {
      toast.error(err.message, "Sync Failed");
    } finally {
      syncBtn.disabled = false;
      syncBtnLabel.textContent = "Sync Now";
    }
  });

  // Subscribe to route changes for active styling
  store.subscribe("route", (currentRoute) => {
    navLinks.forEach((link) => {
      if (link.getAttribute("data-route") === currentRoute) {
        link.classList.add("active");
      } else {
        link.classList.remove("active");
      }
    });
  });

  // Subscribe to health state
  store.subscribe("health", (health) => {
    const dot = container.querySelector("#footer-llm-dot");
    const txt = container.querySelector("#footer-llm-text");
    if (!dot || !txt) return;

    dot.className = "status-dot";
    if (health.llm_ready) {
      dot.classList.add("green");
      txt.textContent = "Ready";
    } else {
      dot.classList.add("amber", "pulse");
      txt.textContent = "Warming";
    }
  });

  // Subscribe to sync state
  store.subscribe("sync", (sync) => {
    const dot = container.querySelector("#footer-sync-dot");
    const txt = container.querySelector("#footer-sync-text");
    const emailsCount = container.querySelector("#footer-emails-count");
    if (!dot || !txt || !emailsCount) return;

    dot.className = "status-dot";
    if (sync.job_running) {
      dot.classList.add("amber", "pulse");
      txt.textContent = sync.percent ? `${sync.percent}%` : "Running";
    } else if (sync.last_error) {
      dot.classList.add("red");
      txt.textContent = "Error";
    } else {
      dot.classList.add("green");
      txt.textContent = sync.last_sync_at ? "Synced" : "Idle";
    }

    emailsCount.textContent = (sync.total_emails || 0).toLocaleString();
  });
}
