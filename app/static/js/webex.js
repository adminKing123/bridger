/**
 * app/static/js/webex.js
 * -----------------------
 * Interactive behaviours for Webex configuration pages.
 *
 * initWebexTokenToggle()  — show/hide password field on create/edit forms
 * initWebexTokenReveal()  — show/hide masked token on detail page
 *
 * Called at the bottom of each Webex template's extra_scripts block.
 */

"use strict";

/* ── Token field toggle (create / edit form) ─────────────────── */
function initWebexTokenToggle() {
  const wrap   = document.getElementById("webexTokenWrap");
  const input  = document.getElementById("access_token");
  const btn    = document.getElementById("webexTokenToggleBtn");
  const icon   = btn && btn.querySelector("i");
  if (!wrap || !input || !btn) return;

  btn.addEventListener("click", function () {
    const isPassword = input.type === "password";
    input.type = isPassword ? "text" : "password";
    if (icon) {
      icon.className = isPassword ? "bi bi-eye-slash" : "bi bi-eye";
    }
    btn.setAttribute("aria-label", isPassword ? "Hide token" : "Show token");
  });
}

/* ── Masked token reveal (detail page) ──────────────────────── */
function initWebexTokenReveal() {
  const displayEl = document.getElementById("webexTokenDisplay");
  const revealBtn = document.getElementById("webexTokenRevealBtn");
  const revealIcon = revealBtn && revealBtn.querySelector("i");
  if (!displayEl || !revealBtn) return;

  const maskedValue  = displayEl.dataset.masked;
  const actualValue  = displayEl.dataset.actual;
  let   revealed     = false;

  revealBtn.addEventListener("click", function () {
    revealed = !revealed;
    displayEl.textContent = revealed ? actualValue : maskedValue;
    if (revealIcon) {
      revealIcon.className = revealed ? "bi bi-eye-slash" : "bi bi-eye";
    }
    revealBtn.setAttribute("aria-label", revealed ? "Hide token" : "Show token");
  });
}
