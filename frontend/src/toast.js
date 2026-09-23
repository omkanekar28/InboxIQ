/**
 * =========================================================
 * InboxIQ — Toast Notification System
 * =========================================================
 */

class ToastManager {
  constructor() {
    this.container = null;
  }

  init() {
    if (!this.container) {
      this.container = document.getElementById("toast-container");
      if (!this.container) {
        this.container = document.createElement("div");
        this.container.id = "toast-container";
        document.body.appendChild(this.container);
      }
    }
  }

  show({ type = "info", title, message, duration = 4000 }) {
    this.init();

    const toast = document.createElement("div");
    toast.className = `toast ${type}`;

    let iconSvg = "";
    if (type === "success") {
      iconSvg = `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>`;
    } else if (type === "error") {
      iconSvg = `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="8" x2="12" y2="12"></line><line x1="12" y1="16" x2="12.01" y2="16"></line></svg>`;
    } else {
      iconSvg = `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`;
    }

    toast.innerHTML = `
      ${iconSvg}
      <div class="toast-content">
        ${title ? `<div class="toast-title">${title}</div>` : ""}
        <div class="toast-message">${message || ""}</div>
      </div>
      <button class="toast-close-btn" aria-label="Dismiss">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>
      </button>
    `;

    const closeBtn = toast.querySelector(".toast-close-btn");
    const dismiss = () => {
      toast.classList.add("toast-out");
      setTimeout(() => {
        if (toast.parentElement) toast.parentElement.removeChild(toast);
      }, 200);
    };

    closeBtn.addEventListener("click", dismiss);
    if (duration > 0) {
      setTimeout(dismiss, duration);
    }

    this.container.appendChild(toast);
  }

  success(message, title = "Success") {
    this.show({ type: "success", title, message });
  }

  error(message, title = "Error") {
    this.show({ type: "error", title, message });
  }

  warning(message, title = "Warning") {
    this.show({ type: "warning", title, message });
  }
}

export const toast = new ToastManager();
