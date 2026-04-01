/**
 * proxy.js — Bridger proxy page interactions
 * Loaded on: proxy/list.html, proxy/create.html,
 *            proxy/detail.html, proxy/logs.html
 *
 * Modules:
 *   initProxyCopy  — copy-to-clipboard for proxy access URLs
 *   initClearLogs  — clear-logs confirmation modal
 */
(function () {
  'use strict';

  /* ── Copy-to-clipboard for proxy URLs ────────────────────── */
  function initProxyCopy() {
    document.querySelectorAll('[data-copy-target]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var targetId = btn.getAttribute('data-copy-target');
        var el = document.getElementById(targetId);
        if (!el) return;

        var text = el.textContent || el.value || '';

        if (!navigator.clipboard) {
          /* Fallback for older browsers */
          var ta = document.createElement('textarea');
          ta.value = text;
          ta.style.position = 'fixed';
          ta.style.opacity  = '0';
          document.body.appendChild(ta);
          ta.select();
          document.execCommand('copy');
          document.body.removeChild(ta);
          _setCopied(btn);
          return;
        }

        navigator.clipboard.writeText(text).then(function () { _setCopied(btn); });
      });
    });

    function _setCopied(btn) {
      var orig = btn.innerHTML;
      btn.innerHTML = '<i class="bi bi-check-lg"></i>Copied!';
      btn.classList.add('copied');
      setTimeout(function () {
        btn.innerHTML = orig;
        btn.classList.remove('copied');
      }, 2000);
    }
  }

  /* ── Clear-logs confirmation modal ───────────────────────── */
  function initClearLogs() {
    var trigger   = document.getElementById('clearLogsBtn');
    var backdrop  = document.getElementById('clearLogsModal');
    var cancelBtn = document.getElementById('clearLogsCancel');
    if (!trigger || !backdrop) return;

    function openModal() {
      backdrop.classList.add('open');
      backdrop.removeAttribute('aria-hidden');
      if (cancelBtn) cancelBtn.focus();
    }

    function closeModal() {
      backdrop.classList.remove('open');
      backdrop.setAttribute('aria-hidden', 'true');
    }

    trigger.addEventListener('click', openModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeModal);

    backdrop.addEventListener('click', function (e) {
      if (e.target === backdrop) closeModal();
    });

    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && backdrop.classList.contains('open')) closeModal();
    });
  }

  /* ── Boot ─────────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    initProxyCopy();
    initClearLogs();
  });
})();
