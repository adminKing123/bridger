/**
 * base.js — Bridger core interactions (loaded on every page)
 *
 * Modules:
 *   initFormLoading   — spinner + disable on any form[data-loadable] submit
 *   initToastDismiss  — auto-dismiss toast notifications
 *   initLogoutModal   — logout confirmation modal
 */
(function () {
  'use strict';

  /* ── Form loading state ───────────────────────────────────── */
  function initFormLoading() {
    document.querySelectorAll('form[data-loadable]').forEach(function (form) {
      form.addEventListener('submit', function () {
        var btn = form.querySelector('[data-submit-btn]');
        if (!btn) return;
        var loadText = btn.getAttribute('data-loading-text') || 'Please wait…';
        btn.setAttribute('data-original-html', btn.innerHTML);
        btn.innerHTML = '<span class="btn-spinner"></span>' + loadText;
        btn.disabled  = true;
        btn.classList.add('is-loading');

        /* Safety reset after 15 s in case of network failure */
        setTimeout(function () {
          if (!btn.disabled) return;
          var orig = btn.getAttribute('data-original-html');
          if (orig) btn.innerHTML = orig;
          btn.disabled = false;
          btn.classList.remove('is-loading');
        }, 15000);
      });
    });
  }

  /* ── Toast auto-dismiss ───────────────────────────────────── */
  function initToastDismiss() {
    function dismiss(item) {
      item.classList.add('dismissing');
      setTimeout(function () { if (item.parentNode) item.parentNode.removeChild(item); }, 240);
    }

    document.querySelectorAll('.toast-close').forEach(function (btn) {
      btn.addEventListener('click', function () { dismiss(btn.closest('.toast-item')); });
    });

    document.querySelectorAll('.toast-item').forEach(function (item, idx) {
      setTimeout(function () { if (item.isConnected) dismiss(item); }, 5000 + idx * 600);
    });
  }

  /* ── Logout modal ─────────────────────────────────────────── */
  function initLogoutModal() {
    var backdrop  = document.getElementById('logoutModal');
    if (!backdrop) return;
    var cancelBtn = document.getElementById('logoutCancel');

    function openModal() {
      backdrop.classList.add('open');
      backdrop.removeAttribute('aria-hidden');
      if (cancelBtn) cancelBtn.focus();
    }

    function closeModal() {
      backdrop.classList.remove('open');
      backdrop.setAttribute('aria-hidden', 'true');
    }

    document.querySelectorAll('[data-logout-trigger]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        openModal();
      });
    });

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
    initFormLoading();
    initToastDismiss();
    initLogoutModal();
  });
})();
