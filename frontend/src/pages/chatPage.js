/**
 * =========================================================
 * Chat Page — Real-time Assistant Conversation with SSE Streaming
 * =========================================================
 */

import { store } from "../store.js";
import { api } from "../api.js";
import { toast } from "../toast.js";
import { renderLogo } from "../components/logo.js";

export function renderChatPage(container) {
  // Conversation history in memory
  let conversationHistory = [];
  let isStreaming = false;

  container.innerHTML = `
    <div class="chat-container">
      <!-- Chat Header -->
      <header class="chat-header">
        <div class="chat-header-left">
          <div class="chat-header-title">
            <span class="status-dot green" id="chat-status-dot"></span>
            InboxIQ Assistant
          </div>
          <div class="chat-model-badge active-green" id="chat-model-badge">
            <span class="status-dot green" style="width: 6px; height: 6px;"></span>
            <span id="chat-model-name">lightweight</span>
          </div>
        </div>

        <div class="chat-header-right">
          <button class="btn btn-secondary" id="chat-sync-btn" style="padding: 6px 12px; font-size: 12px;">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="23 4 23 10 17 10"></polyline><polyline points="1 20 1 14 7 14"></polyline><path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"></path></svg>
            <span id="chat-sync-text">Sync</span>
          </button>
        </div>
      </header>

      <!-- LLM Warming Banner -->
      <div class="llm-warning-banner" id="llm-warmup-banner" style="display: none;">
        <span>⚠ Local LLM server is starting up or loading weights into VRAM. Responses may take a moment.</span>
        <button class="btn btn-secondary" id="banner-check-btn" style="padding: 2px 8px; font-size: 11px;">Check Health</button>
      </div>

      <!-- Messages Thread -->
      <div class="chat-messages" id="chat-messages">
        <!-- Render empty state by default -->
        <div class="chat-empty-state" id="empty-state">
          <div class="empty-dial">
            ${renderLogo(64, true)}
          </div>
          <h2 class="empty-title">InboxIQ Assistant Ready</h2>
          <p class="empty-subtitle">
            Ask natural language questions about your indexed emails. Your data stays 100% private and never leaves this computer.
          </p>
          <div class="date-range-tip">
            <span class="tip-icon">💡</span>
            <span class="tip-text">
              <strong>Tip:</strong> For best results, specify a time frame like <code>this week</code>, <code>last month</code>, or <code>in the past 3 days</code>.
            </span>
          </div>
          <div class="suggested-queries">
            <button class="query-chip" data-query="Show my unread emails from this week">
              <span>"Show my unread emails from this week"</span>
              <span class="text-green">→</span>
            </button>
            <button class="query-chip" data-query="Find emails from GitHub in the past 7 days">
              <span>"Find emails from GitHub in the past 7 days"</span>
              <span class="text-green">→</span>
            </button>
            <button class="query-chip" data-query="Search for receipts from last month">
              <span>"Search for receipts from last month"</span>
              <span class="text-green">→</span>
            </button>
          </div>
        </div>
      </div>

      <!-- Bottom Input Bar -->
      <div class="chat-input-bar">
        <div class="input-box-wrapper">
          <textarea 
            class="chat-textarea" 
            id="chat-textarea" 
            rows="1" 
            placeholder="Ask anything about your Gmail inbox..."
          ></textarea>
          <button class="send-btn" id="send-btn" disabled>
            <svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"></line><polygon points="22 2 15 22 11 13 2 9 22 2"></polygon></svg>
          </button>
        </div>
        <div class="input-hints">
          <span>Press <strong>Enter</strong> to send, <strong>Shift + Enter</strong> for new line</span>
          <span class="mono" id="input-privacy-badge">🔒 100% Local Inference</span>
        </div>
      </div>
    </div>
  `;

  const messagesContainer = container.querySelector("#chat-messages");
  const textarea = container.querySelector("#chat-textarea");
  const sendBtn = container.querySelector("#send-btn");
  const modelBadgeName = container.querySelector("#chat-model-name");
  const warmupBanner = container.querySelector("#llm-warmup-banner");
  const chatSyncBtn = container.querySelector("#chat-sync-btn");
  const chatSyncText = container.querySelector("#chat-sync-text");

  // Sync button in chat header
  chatSyncBtn.addEventListener("click", async () => {
    try {
      chatSyncBtn.disabled = true;
      chatSyncText.textContent = "Syncing...";
      await api.triggerSync();
      toast.success("Sync started in background.", "Gmail Sync");
      store.refreshSync();
    } catch (err) {
      toast.error(err.message, "Sync Failed");
    } finally {
      chatSyncBtn.disabled = false;
      chatSyncText.textContent = "Sync";
    }
  });

  // Recheck health banner button
  container.querySelector("#banner-check-btn")?.addEventListener("click", async () => {
    await store.refreshHealth();
  });

  // Auto-resize textarea
  textarea.addEventListener("input", () => {
    textarea.style.height = "auto";
    textarea.style.height = Math.min(textarea.scrollHeight, 140) + "px";
    sendBtn.disabled = !textarea.value.trim() || isStreaming;
  });

  // Enter to send
  textarea.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (!sendBtn.disabled) {
        handleSendMessage();
      }
    }
  });

  sendBtn.addEventListener("click", handleSendMessage);

  // Suggested chips
  container.querySelectorAll(".query-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      const q = chip.getAttribute("data-query");
      if (q) {
        textarea.value = q;
        textarea.dispatchEvent(new Event("input"));
        handleSendMessage();
      }
    });
  });

  // Helper to scroll to bottom
  function scrollToBottom() {
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
  }

  // Helper to format basic markdown (bold, list, code)
  function formatMarkdown(text) {
    if (!text) return "";
    let safe = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // Replace bold **text**
    safe = safe.replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>");

    // Replace code `code`
    safe = safe.replace(/`([^`]+)`/g, "<code>$1</code>");

    // Line breaks
    return safe.replace(/\n/g, "<br>");
  }

  // Handle Send Message
  async function handleSendMessage() {
    const text = textarea.value.trim();
    if (!text || isStreaming) return;

    // Remove empty state if present
    const emptyState = container.querySelector("#empty-state");
    if (emptyState) emptyState.remove();

    // 1. Add User Message
    const userMsg = { role: "user", content: text };
    conversationHistory.push(userMsg);

    const userRow = document.createElement("div");
    userRow.className = "message-row user";
    userRow.innerHTML = `
      <div class="user-bubble">
        ${formatMarkdown(text)}
      </div>
    `;
    messagesContainer.appendChild(userRow);

    // Reset textarea
    textarea.value = "";
    textarea.style.height = "auto";
    sendBtn.disabled = true;
    isStreaming = true;
    scrollToBottom();

    // 2. Prepare Assistant Bubble with Typing / Streaming Indicator
    const assistantRow = document.createElement("div");
    assistantRow.className = "message-row assistant";
    assistantRow.innerHTML = `
      <div class="assistant-card">
        <div class="tool-calls-container"></div>
        <div class="assistant-text">
          <div class="typing-indicator">
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
            <span class="typing-dot"></span>
          </div>
        </div>
        <div class="message-meta" style="display: none;"></div>
      </div>
    `;
    messagesContainer.appendChild(assistantRow);
    scrollToBottom();

    const toolContainer = assistantRow.querySelector(".tool-calls-container");
    const textContainer = assistantRow.querySelector(".assistant-text");
    const metaContainer = assistantRow.querySelector(".message-meta");

    let streamedContent = "";
    const startTime = Date.now();

    try {
      await api.chatStream(conversationHistory, {
        onToken(token) {
          if (!token) return;
          if (streamedContent === "") {
            // First token arrived, clear typing indicator
            textContainer.innerHTML = "";
          }
          streamedContent += token;
          textContainer.innerHTML = formatMarkdown(streamedContent) + `<span class="streaming-cursor">▌</span>`;
          scrollToBottom();
        },
        onToolCall(toolCall) {
          // Add tool invocation pill
          const chip = document.createElement("div");
          chip.className = "tool-chip";
          const argsPreview = JSON.stringify(toolCall.arguments || {});
          chip.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"></path></svg>
            <span><strong>${toolCall.name}</strong> <span class="tool-chip-args">${argsPreview}</span></span>
          `;
          toolContainer.appendChild(chip);
          scrollToBottom();
        },
        onDone(doneData) {
          // Finalize text: prioritize streamedContent, fallback to doneData.reply
          const finalReply = (streamedContent && streamedContent.trim())
            ? streamedContent
            : (doneData && doneData.reply ? doneData.reply : streamedContent);

          textContainer.innerHTML = formatMarkdown(finalReply || "I have completed processing your request.");
          const latency = (doneData && doneData.latency_seconds) 
            ? `${doneData.latency_seconds.toFixed(2)}s` 
            : `${((Date.now() - startTime) / 1000).toFixed(2)}s`;

          metaContainer.style.display = "flex";
          metaContainer.innerHTML = `
            <span>Latency: ${latency}</span>
            <span>•</span>
            <span>Model: ${store.get("health")?.active_model || "local"}</span>
          `;

          // Add to conversation history
          conversationHistory.push({
            role: "assistant",
            content: finalReply,
          });

          isStreaming = false;
          sendBtn.disabled = !textarea.value.trim();
          scrollToBottom();
        },
        onError(error) {
          textContainer.innerHTML = `
            <div style="color: var(--color-danger);">
              ⚠ Error generating response: ${error.message}
            </div>
          `;
          isStreaming = false;
          sendBtn.disabled = !textarea.value.trim();
          toast.error(error.message, "Chat Error");
          scrollToBottom();
        },
      });
    } catch (err) {
      isStreaming = false;
      sendBtn.disabled = !textarea.value.trim();
      textContainer.innerHTML = `<span style="color: var(--color-danger);">${err.message}</span>`;
      scrollToBottom();
    }
  }

  // Subscribe to health for warmup banner & model badge
  store.subscribe("health", (health) => {
    if (health.active_model) {
      modelBadgeName.textContent = health.active_model;
    }
    if (health.llm_ready) {
      warmupBanner.style.display = "none";
    } else {
      warmupBanner.style.display = "flex";
    }
  });

  return () => {
    // Cleanup if needed
  };
}
