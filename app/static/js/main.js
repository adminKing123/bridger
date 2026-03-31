/**
 * main.js — Bridger client interactions
 *
 * Modules:
 *   initPasswordToggles   — show / hide password on eye-icon click
 *   initPasswordStrength  — live strength bar (signup, reset)
 *   initPasswordMatch     — live confirm-password match hint
 *   initOtpBoxes          — 6-digit individual OTP input boxes
 *   initFormLoading       — spinner + disable on form submit
 *   initToastDismiss      — auto-dismiss toast notifications
 */
(function () {
  'use strict';

  /* ── Password visibility toggles ─────────────────────────── */
  function initPasswordToggles() {
    document.querySelectorAll('[data-toggle-pw]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var id    = btn.getAttribute('data-toggle-pw');
        var input = document.getElementById(id);
        var icon  = btn.querySelector('i');
        if (!input) return;
        var hidden   = input.type === 'password';
        input.type   = hidden ? 'text' : 'password';
        if (icon) icon.className = hidden ? 'bi bi-eye-slash' : 'bi bi-eye';
      });
    });
  }

  /* ── Password strength meter ──────────────────────────────── */
  function scorePassword(pw) {
    if (!pw) return 0;
    var score = 0;
    if (pw.length >= 8)            score++;
    if (pw.length >= 12)           score++;
    if (/[A-Z]/.test(pw))          score++;
    if (/[0-9]/.test(pw))          score++;
    if (/[^A-Za-z0-9]/.test(pw))   score++;
    return score; // 0 – 5
  }

  function initPasswordStrength() {
    document.querySelectorAll('input[data-strength-for]').forEach(function (input) {
      var key     = input.getAttribute('data-strength-for');
      var fillEl  = document.getElementById(key + '-fill');
      var labelEl = document.getElementById(key + '-label');
      if (!fillEl || !labelEl) return;

      var LABELS = ['', 'Too short', 'Weak', 'Fair', 'Good', 'Strong'];
      var COLORS = ['', '#ef4444',   '#f97316', '#eab308', '#22c55e', '#16a34a'];
      var WIDTHS = ['0%', '20%', '40%', '60%', '80%', '100%'];

      input.addEventListener('input', function () {
        var s = scorePassword(input.value);
        fillEl.style.width      = WIDTHS[s];
        fillEl.style.background = COLORS[s];
        labelEl.textContent     = input.value ? LABELS[s] : '';
        labelEl.style.color     = COLORS[s];
      });
    });
  }

  /* ── Confirm-password match hint ──────────────────────────── */
  function initPasswordMatch() {
    document.querySelectorAll('input[data-match-source]').forEach(function (confirmInput) {
      var sourceId = confirmInput.getAttribute('data-match-source');
      var hintId   = confirmInput.getAttribute('data-match-hint');
      var source   = document.getElementById(sourceId);
      var hint     = document.getElementById(hintId);
      if (!source || !hint) return;

      function check() {
        if (!confirmInput.value) { hint.className = 'pw-match-hint'; return; }
        var ok = confirmInput.value === source.value;
        hint.className = 'pw-match-hint show ' + (ok ? 'ok' : 'bad');
        hint.innerHTML = ok
          ? '<i class="bi bi-check-circle-fill"></i>Passwords match'
          : '<i class="bi bi-x-circle-fill"></i>Passwords do not match';
      }

      confirmInput.addEventListener('input', check);
      source.addEventListener('input', check);
    });
  }

  /* ── Individual OTP boxes ─────────────────────────────────── */
  function initOtpBoxes() {
    document.querySelectorAll('.otp-group').forEach(function (group) {
      var boxes      = Array.from(group.querySelectorAll('.otp-box'));
      var hiddenId   = group.getAttribute('data-hidden') || 'otp_code';
      var hidden     = document.getElementById(hiddenId);
      var autoSubmit = group.hasAttribute('data-autosubmit');

      function syncHidden() {
        if (hidden) hidden.value = boxes.map(function (b) { return b.value; }).join('');
      }

      function refreshClasses() {
        boxes.forEach(function (b) { b.classList.toggle('filled', b.value.length > 0); });
        var full = boxes.every(function (b) { return b.value.length > 0; });
        group.classList.toggle('all-done', full);
        if (full && autoSubmit) {
          setTimeout(function () { group.closest('form').submit(); }, 180);
        }
      }

      /* Clear any server-side error styling once user starts typing */
      function clearErrors() {
        boxes.forEach(function (b) { b.classList.remove('has-error'); });
        var errEl = group.parentElement.querySelector('.otp-error');
        if (errEl) errEl.style.display = 'none';
      }

      boxes.forEach(function (box, i) {
        box.addEventListener('focus', function () { box.select(); });

        box.addEventListener('input', function () {
          box.value = box.value.replace(/\D/g, '').slice(-1);
          clearErrors();
          syncHidden();
          refreshClasses();
          if (box.value && i < boxes.length - 1) boxes[i + 1].focus();
        });

        box.addEventListener('keydown', function (e) {
          if (e.key === 'Backspace') {
            if (!box.value && i > 0) {
              boxes[i - 1].value = '';
              boxes[i - 1].focus();
              syncHidden();
              refreshClasses();
            }
          }
          if (e.key === 'ArrowLeft'  && i > 0)                boxes[i - 1].focus();
          if (e.key === 'ArrowRight' && i < boxes.length - 1) boxes[i + 1].focus();
        });

        box.addEventListener('paste', function (e) {
          e.preventDefault();
          var pasted = (e.clipboardData || window.clipboardData)
            .getData('text')
            .replace(/\D/g, '')
            .slice(0, boxes.length);
          pasted.split('').forEach(function (ch, j) { if (boxes[j]) boxes[j].value = ch; });
          var next = Math.min(pasted.length, boxes.length - 1);
          boxes[next].focus();
          clearErrors();
          syncHidden();
          refreshClasses();
        });
      });

      /* Mark error boxes from server-side validation */
      if (hidden && hidden.closest('form')) {
        var hasError = !!hidden.closest('form').querySelector('.otp-error');
        if (hasError) boxes.forEach(function (b) { b.classList.add('has-error'); });
      }

      /* Auto-focus first empty box */
      var firstEmpty = boxes.find(function (b) { return !b.value; });
      if (firstEmpty) firstEmpty.focus();
    });
  }

  /* ── Form loading state ───────────────────────────────────── */
  function initFormLoading() {
    document.querySelectorAll('form[data-loadable]').forEach(function (form) {
      form.addEventListener('submit', function () {
        var btn  = form.querySelector('[data-submit-btn]');
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

  /* ── Multi-step registration form ────────────────────────────────────────── */
  function initStepForm() {
    var form = document.querySelector('[data-step-form]');
    if (!form) return;

    var panels     = Array.from(form.querySelectorAll('.step-panel'));
    var dots       = Array.from(form.querySelectorAll('[data-dot]'));
    var connectors = Array.from(form.querySelectorAll('[data-connector]'));
    var current    = 1;

    /* Client-side rules per step — supplements server-side validation */
    var rules = {
      1: [
        {
          id: 'username',
          test: function (v) { return /^[A-Za-z0-9_]{3,80}$/.test(v.trim()); },
          msg: 'Username must be 3–80 characters (letters, numbers, underscores).'
        },
        {
          id: 'email',
          test: function (v) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v.trim()); },
          msg: 'Please enter a valid email address.'
        }
      ],
      2: [
        {
          id: 'first_name',
          test: function (v) { return v.trim().length >= 1; },
          msg: 'First name is required.'
        }
      ],
      3: [
        {
          id: 'pw1',
          test: function (v) { return v.length >= 8; },
          msg: 'Password must be at least 8 characters.'
        },
        {
          id: 'pw2',
          test: function (v) {
            var pw1 = document.getElementById('pw1');
            return pw1 ? v === pw1.value : false;
          },
          msg: 'Passwords do not match.'
        }
      ]
    };

    /* Add or update a JS-generated error below a field */
    function setErr(el, msg) {
      el.classList.add('is-invalid');
      var wrap  = el.closest('.mb-3') || el.closest('.mb-4') || el.parentElement;
      var grp   = el.closest('.pw-group');
      var anchor = grp || el;
      var errEl = wrap ? wrap.querySelector('.js-err') : null;
      if (!errEl) {
        errEl = document.createElement('div');
        errEl.className = 'invalid-feedback js-err';
        anchor.insertAdjacentElement('afterend', errEl);
      }
      errEl.innerHTML = '<i class="bi bi-exclamation-circle-fill me-1"></i>' + msg;
      errEl.style.display = 'flex';
    }

    function clearErr(el) {
      el.classList.remove('is-invalid');
      var wrap  = el.closest('.mb-3') || el.closest('.mb-4') || el.parentElement;
      var errEl = wrap ? wrap.querySelector('.js-err') : null;
      if (errEl) errEl.style.display = 'none';
    }

    function validateStep(n) {
      var stepRules = rules[n];
      if (!stepRules) return true;
      var ok = true;
      stepRules.forEach(function (rule) {
        var input = document.getElementById(rule.id);
        if (!input) return;
        if (!rule.test(input.value)) { setErr(input, rule.msg); ok = false; }
        else                         { clearErr(input); }
      });
      return ok;
    }

    function showStep(n) {
      if (n < 1 || n > panels.length) return;
      panels.forEach(function (p, i) {
        p.classList.toggle('active', i + 1 === n);
      });
      dots.forEach(function (d) {
        var s = parseInt(d.getAttribute('data-dot'));
        d.classList.toggle('active', s === n);
        d.classList.toggle('done',   s < n);
        d.innerHTML = s < n ? '<i class="bi bi-check-lg"></i>' : String(s);
      });
      connectors.forEach(function (c) {
        c.classList.toggle('done', parseInt(c.getAttribute('data-connector')) < n);
      });
      current = n;
      var first = panels[n - 1].querySelector('input:not([type=hidden])');
      if (first) setTimeout(function () { first.focus(); }, 50);
    }

    /* Clear JS errors as user types */
    panels.forEach(function (panel) {
      panel.querySelectorAll('input').forEach(function (input) {
        input.addEventListener('input', function () { clearErr(input); });
      });
    });

    form.querySelectorAll('[data-next-step]').forEach(function (btn) {
      btn.addEventListener('click', function () {
        if (validateStep(current)) showStep(current + 1);
      });
    });

    form.querySelectorAll('[data-prev-step]').forEach(function (btn) {
      btn.addEventListener('click', function () { showStep(current - 1); });
    });

    /* On page load: jump to the first panel that has a server-side error */
    var errorStep = 1;
    for (var i = 0; i < panels.length; i++) {
      if (panels[i].querySelector('.is-invalid')) { errorStep = i + 1; break; }
    }
    showStep(errorStep);
  }

  /* ── Logout modal ────────────────────────────────────────────────────────── */
  function initLogoutModal() {
    var backdrop = document.getElementById('logoutModal');
    if (!backdrop) return;
    var cancelBtn = document.getElementById('logoutCancel');

    function openModal() {
      backdrop.classList.add('open');
      backdrop.removeAttribute('aria-hidden');
      /* Trap focus on cancel button for accessibility */
      if (cancelBtn) cancelBtn.focus();
    }

    function closeModal() {
      backdrop.classList.remove('open');
      backdrop.setAttribute('aria-hidden', 'true');
    }

    /* Attach to every element with data-logout-trigger */
    document.querySelectorAll('[data-logout-trigger]').forEach(function (el) {
      el.addEventListener('click', function (e) {
        e.preventDefault();
        openModal();
      });
    });

    /* Cancel button closes modal */
    if (cancelBtn) {
      cancelBtn.addEventListener('click', closeModal);
    }

    /* Click on backdrop overlay closes modal */
    backdrop.addEventListener('click', function (e) {
      if (e.target === backdrop) closeModal();
    });

    /* Escape key closes modal */
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && backdrop.classList.contains('open')) {
        closeModal();
      }
    });
  }

  /* ── Boot ────────────────────────────────────────────────────────────────── */
  document.addEventListener('DOMContentLoaded', function () {
    initPasswordToggles();
    initPasswordStrength();
    initPasswordMatch();
    initOtpBoxes();
    initFormLoading();
    initToastDismiss();
    initStepForm();
    initLogoutModal();
  });
})();
