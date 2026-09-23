/**
 * =========================================================
 * InboxIQ — Brand Logo Component
 * =========================================================
 * Modern high-contrast mail intelligence emblem with glowing green accent.
 */

export function renderLogo(size = 32, animated = true) {
  return `
    <svg 
      class="app-logo ${animated ? 'pulse' : ''}" 
      width="${size}" 
      height="${size}" 
      viewBox="0 0 40 40" 
      fill="none" 
      xmlns="http://www.w3.org/2000/svg"
      style="display: block; filter: drop-shadow(0 0 ${size > 40 ? '10px' : '4px'} rgba(0, 255, 65, 0.4));"
    >
      <!-- Background badge -->
      <rect x="2" y="2" width="36" height="36" rx="8" fill="#111611" stroke="#00FF41" stroke-width="1.8" stroke-opacity="0.8" />
      
      <!-- Mail envelope shape -->
      <rect x="9" y="12" width="22" height="16" rx="2.5" stroke="#00FF41" stroke-width="1.8" fill="#0A0A0A" />
      <path d="M9 13.5L20 22L31 13.5" stroke="#00FF41" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
      
      <!-- Intelligence pulse node -->
      <circle cx="20" cy="20" r="2" fill="#00FF41" />
      <circle cx="20" cy="20" r="4.5" stroke="#00FF41" stroke-width="1" stroke-opacity="0.4" />
    </svg>
  `;
}

