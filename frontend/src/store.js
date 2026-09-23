/**
 * =========================================================
 * InboxIQ — Reactive Application Store
 * =========================================================
 */

import { api } from "./api.js";

class Store {
  constructor() {
    this.state = {
      route: "chat", // 'chat' | 'setup' | 'settings'
      health: {
        status: "checking",
        llm_ready: false,
        active_model: "lightweight",
      },
      sync: {
        state: "idle",
        total_emails: 0,
        last_sync_at: null,
        job_running: false,
        last_error: null,
      },
      hardware: {
        gpu_available: false,
        gpu_name: "Detecting...",
        vram_mb: 0,
        active_model: "lightweight",
      },
      setup: {
        credentials_ok: false,
        authenticated: false,
        models_downloaded: false,
        initial_sync_done: false,
      },
      backendOnline: true,
    };

    this.listeners = new Map();
    this.pollInterval = null;
  }

  get(key) {
    return this.state[key];
  }

  set(key, value) {
    this.state[key] = value;
    this.emit(key, value);
  }

  subscribe(key, callback) {
    if (!this.listeners.has(key)) {
      this.listeners.set(key, new Set());
    }
    this.listeners.get(key).add(callback);
    // Immediately call callback with current value
    callback(this.state[key]);
    return () => this.listeners.get(key).delete(callback);
  }

  emit(key, value) {
    if (this.listeners.has(key)) {
      this.listeners.get(key).forEach((cb) => {
        try {
          cb(value);
        } catch (e) {
          console.error("Store subscriber error:", e);
        }
      });
    }
  }

  async refreshHealth() {
    try {
      const data = await api.health();
      this.set("health", data);
      this.set("backendOnline", true);
    } catch (err) {
      this.set("health", { ...this.state.health, llm_ready: false });
      this.set("backendOnline", false);
    }
  }

  async refreshSync() {
    try {
      const data = await api.getSyncStatus();
      this.set("sync", data);
    } catch (_) {}
  }

  async refreshHardware() {
    try {
      const data = await api.getHardwareProfile();
      this.set("hardware", data);
    } catch (_) {}
  }

  async refreshSetup() {
    try {
      const data = await api.getSetupStatus();
      this.set("setup", data);
      return data;
    } catch (_) {
      return null;
    }
  }

  startPolling() {
    this.refreshHealth();
    this.refreshSync();
    this.refreshHardware();

    if (this.pollInterval) clearInterval(this.pollInterval);
    this.pollInterval = setInterval(() => {
      this.refreshHealth();
      this.refreshSync();
    }, 10000);
  }

  stopPolling() {
    if (this.pollInterval) clearInterval(this.pollInterval);
  }
}

export const store = new Store();
