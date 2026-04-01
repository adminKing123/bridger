/**
 * profile.js — Bridger profile page interactions
 * Loaded on: profile/profile.html
 *
 * Modules:
 *   initProfileEdit — inline edit / discard toggle for profile form
 */
(function () {
  'use strict';

  /* ── Profile edit toggle ──────────────────────────────────── */
  function initProfileEdit() {
    var view       = document.getElementById('profileView');
    var editForm   = document.getElementById('profileEditForm');
    var openBtn    = document.getElementById('editProfileBtn');
    var discardBtn = document.getElementById('discardProfileBtn');
    if (!view || !editForm || !openBtn) return;

    function openEdit() {
      view.style.display     = 'none';
      editForm.style.display = 'block';
      openBtn.style.display  = 'none';
      var firstInput = editForm.querySelector('input:not([type=hidden])');
      if (firstInput) firstInput.focus();
    }

    function closeEdit() {
      editForm.style.display = 'none';
      view.style.display     = 'block';
      openBtn.style.display  = '';
    }

    /* Auto-open if the server returned validation errors */
    if (editForm.querySelector('.is-invalid')) openEdit();

    openBtn.addEventListener('click', openEdit);
    if (discardBtn) discardBtn.addEventListener('click', closeEdit);
  }

  /* ── Boot ─────────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    initProfileEdit();
  });
})();
