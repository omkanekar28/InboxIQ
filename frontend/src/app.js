/**
 * =========================================================
 * InboxIQ — Main Application Orchestrator & Router
 * =========================================================
 */

import { store } from "./store.js";
import { renderSidebar } from "./components/sidebar.js";
import { renderChatPage } from "./pages/chatPage.js";
import { renderSetupPage } from "./pages/setupPage.js";
import { renderSettingsPage } from "./pages/settingsPage.js";

class App {
  constructor() {
    this.appEl = document.getElementById("app");
    this.sidebarContainer = null;
    this.viewportContainer = null;
    this.currentCleanups = [];
  }

  init() {
    // 1. Build Base Layout Shell
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

    // 2. Render Sidebar
    renderSidebar(this.sidebarContainer);

    // 3. Subscribe to Route Changes
    store.subscribe("route", (route) => {
      this.navigate(route);
    });

    // 4. Subscribe to Backend Connectivity
    store.subscribe("backendOnline", (online) => {
      if (offlineBanner) {
        offlineBanner.style.display = online ? "none" : "block";
      }
    });

    // 5. Start Background Polling
    store.startPolling();

    // 6. Check Initial Setup State
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
