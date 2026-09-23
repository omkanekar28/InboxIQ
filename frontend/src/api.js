/**
 * =========================================================
 * InboxIQ — Centralized API Client Module
 * =========================================================
 * Manages all HTTP communication with the FastAPI backend,
 * including SSE text-stream processing for chat responses.
 */

// If served by FastAPI on port 8000, relative URLs work directly;
// if accessed via Vite/other dev server, fallback to localhost:8000.
const BASE_URL = window.location.port === "8000" ? "" : "http://localhost:8000";

export const api = {
  /**
   * Health check and LLM readiness probe.
   * GET /api/health
   */
  async health() {
    const res = await fetch(`${BASE_URL}/api/health`);
    if (!res.ok) throw new Error(`Health check failed: ${res.statusText}`);
    return await res.json();
  },

  /**
   * System startup and boot progress probe.
   * GET /api/system/startup
   */
  async getStartupStatus() {
    const res = await fetch(`${BASE_URL}/api/system/startup`);
    if (!res.ok) throw new Error(`Startup check failed: ${res.statusText}`);
    return await res.json();
  },

  /**
   * SSE Streaming Chat completion endpoint.
   * POST /api/chat { messages, stream: true }
   */
  async chatStream(messages, { onToken, onToolCall, onDone, onError }) {
    try {
      const response = await fetch(`${BASE_URL}/api/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Accept": "text/event-stream",
        },
        body: JSON.stringify({
          messages,
          stream: true,
        }),
      });

      if (!response.ok) {
        let errDetail = `HTTP ${response.status}: ${response.statusText}`;
        try {
          const errJson = await response.json();
          if (errJson.detail) errDetail = errJson.detail;
        } catch (_) {}
        throw new Error(errDetail);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      let hasReceivedDone = false;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || ""; // Keep partial trailing line

        let currentEvent = null;

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed) {
            currentEvent = null;
            continue;
          }

          if (trimmed.startsWith("event:")) {
            currentEvent = trimmed.replace("event:", "").trim();
          } else if (trimmed.startsWith("data:")) {
            const rawData = trimmed.replace("data:", "").trim();
            try {
              const parsed = JSON.parse(rawData);
              if (currentEvent === "token" && onToken) {
                const tokenText = parsed.text ?? parsed.content ?? parsed.token ?? "";
                if (tokenText) onToken(tokenText);
              } else if (currentEvent === "tool_call" && onToolCall) {
                onToolCall(parsed);
              } else if (currentEvent === "done") {
                hasReceivedDone = true;
                if (onDone) onDone(parsed);
              } else if (currentEvent === "error" && onError) {
                onError(new Error(parsed.error || "Streaming error"));
              }
            } catch (err) {
              console.warn("Failed to parse SSE JSON chunk:", rawData, err);
            }
          }
        }
      }

      if (!hasReceivedDone && onDone) {
        onDone({});
      }
    } catch (error) {
      if (onError) onError(error);
    }
  },

  /**
   * Trigger background Gmail synchronization.
   * POST /api/sync
   */
  async triggerSync() {
    const res = await fetch(`${BASE_URL}/api/sync`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to trigger sync");
    return data;
  },

  /**
   * Query status of Gmail sync job and database metrics.
   * GET /api/sync/status
   */
  async getSyncStatus() {
    const res = await fetch(`${BASE_URL}/api/sync/status`);
    if (!res.ok) throw new Error("Failed to fetch sync status");
    return await res.json();
  },

  /**
   * Query hardware profile (GPU name, VRAM, active model).
   * GET /api/system/hardware
   */
  async getHardwareProfile() {
    const res = await fetch(`${BASE_URL}/api/system/hardware`);
    if (!res.ok) throw new Error("Failed to fetch hardware profile");
    return await res.json();
  },

  /**
   * Switch active LLM model ('lightweight' or 'balanced').
   * POST /api/system/model
   */
  async switchModel(model) {
    const res = await fetch(`${BASE_URL}/api/system/model`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ model }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to switch model");
    return data;
  },

  /**
   * Query first-run setup status.
   * GET /api/setup/status
   */
  async getSetupStatus() {
    const res = await fetch(`${BASE_URL}/api/setup/status`);
    if (!res.ok) throw new Error("Failed to fetch setup status");
    return await res.json();
  },

  /**
   * Upload credentials.json for OAuth2 setup.
   * POST /api/setup/credentials
   */
  async uploadCredentials(fileOrJson) {
    let options = {};
    if (fileOrJson instanceof File) {
      const formData = new FormData();
      formData.append("file", fileOrJson);
      options = {
        method: "POST",
        body: formData,
      };
    } else {
      options = {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: typeof fileOrJson === "string" ? fileOrJson : JSON.stringify(fileOrJson),
      };
    }

    const res = await fetch(`${BASE_URL}/api/setup/credentials`, options);
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Failed to upload credentials");
    return data;
  },

  /**
   * Trigger Google OAuth browser authorization flow.
   * POST /api/setup/auth
   */
  async triggerAuth() {
    const res = await fetch(`${BASE_URL}/api/setup/auth`, { method: "POST" });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Authentication flow failed");
    return data;
  },
};
