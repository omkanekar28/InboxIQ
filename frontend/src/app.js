import { store } from "./store.js";
import { api } from "./api.js";
import { renderSidebar } from "./components/sidebar.js";
import { renderChatPage } from "./pages/chatPage.js";
import { renderSetupPage } from "./pages/setupPage.js";
import { renderSettingsPage } from "./pages/settingsPage.js";
import { renderStartupPage } from "./pages/startupPage.js";

class App {
  constructor() {
    this.appEl = document.getElementById("app");
    this.sidebarContainer = null;
    this.viewportContainer = null;
    this.currentCleanups = [];
    this.hasBooted = false;
  }

  async init() {
    // 1. Check startup state immediately
    try {
      const startup = await api.getStartupStatus();
      if (startup && !startup.completed) {
        // Show live startup screen until services are ready
        const cleanup = renderStartupPage(this.appEl, () => {
          if (cleanup) cleanup();
          this.bootApp();
        });
        return;
      }
    } catch (_) {
      // If endpoint not reachable yet, show startup screen to poll
      const cleanup = renderStartupPage(this.appEl, () => {
        if (cleanup) cleanup();
        this.bootApp();
      });
      return;
    }

    // Already completed or ready
    this.bootApp();
  }

  bootApp() {
    if (this.hasBooted) return;
    this.hasBooted = true;

    // Build Base Layout Shell
    this.appEl.innerHTML = `
      <div id="sidebar-mount"></div>
      <main class="main-viewport" id="viewport-mount"></main>
      <div id="offline-banner" style="display: none; position: fixed; bottom: 0; left: 0; right: 0; background: rgba(255, 68, 68, 0.95); color: white; padding: 10px 20px; font-weight: 600; text-align: center; z-index: 10000; box-shadow: 0 -4px 12px rgba(0,0,0,0.5);">
        ⚠ Cannot connect to InboxIQ backend server at localhost:8000. Ensure 'python main.py' is running.
      </div>
    `;

    this.sidebarContainer = this.appEl.querySelector("#sidebar-mount");
    this.viewportContainer = this.appEl.querySelector("#viewport-mount");
    const offlineBanner = this.appEl.querySelector("#offline-banner");

    // Render Sidebar
    renderSidebar(this.sidebarContainer);

    // Subscribe to Route Changes
    store.subscribe("route", (route) => {
      this.navigate(route);
    });

    // Subscribe to Backend Connectivity
    store.subscribe("backendOnline", (online) => {
      if (offlineBanner) {
        offlineBanner.style.display = online ? "none" : "block";
      }
    });

    // Start Background Polling
    store.startPolling();

    // Check Initial Setup State
    this.checkInitialRoute();
  }

  async checkInitialRoute() {
    try {
      const setup = await store.refreshSetup();
      if (setup && (!setup.credentials_ok || !setup.authenticated || !setup.initial_sync_done)) {
        // If not fully set up, guide user directly to the setup wizard
        store.set("route", "setup");
      } else {
        store.set("route", "chat");
      }
    } catch (_) {
      store.set("route", "chat");
    }
  }

  navigate(route) {
    // Run cleanups from previous page
    this.currentCleanups.forEach((cleanup) => {
      if (typeof cleanup === "function") cleanup();
    });
    this.currentCleanups = [];

    // Clear viewport
    this.viewportContainer.innerHTML = "";

    // Mount target page
    if (route === "chat") {
      const cleanup = renderChatPage(this.viewportContainer);
      if (cleanup) this.currentCleanups.push(cleanup);
    } else if (route === "setup") {
      const cleanup = renderSetupPage(this.viewportContainer);
      if (cleanup) this.currentCleanups.push(cleanup);
    } else if (route === "settings") {
      const cleanup = renderSettingsPage(this.viewportContainer);
      if (cleanup) this.currentCleanups.push(cleanup);
    }
  }
}

// Bootstrap on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  const app = new App();
  app.init();
});
