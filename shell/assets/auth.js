/* auth.js — client-side lane-keeping gate shared by every dashboard entry page.
 *
 * Pages declare their identity with  <body data-page="shell|projection|cash|historical">.
 * The page includes (in <head>, in this order):
 *     <script src=".../access-config.js"></script>
 *     <link rel="stylesheet" href=".../auth.css">
 *     <script src=".../auth.js"></script>
 *
 * Behaviour (see access-config.js for the threat-model caveats):
 *   - No valid session  -> full-screen login overlay (top-level pages only).
 *   - Session present    -> apply the user's `views` filter to this page; show a
 *                           "signed in as … · Log out" chip (top-level pages only).
 *   - Inside an iframe   -> never shows overlay/chip (the shell owns the login UI);
 *                           still applies the view filter.
 *
 * All pages are same-origin, so the session in localStorage is shared across the
 * shell and its iframes.
 */
(function () {
  "use strict";

  var STORAGE_KEY = "toc_dashboard_session";
  var MAX_AGE_MS = 30 * 24 * 60 * 60 * 1000; // 30 days
  var FRAMED = window.top !== window.self;

  var USERS = Array.isArray(window.ACCESS_USERS) ? window.ACCESS_USERS : [];

  // --- credential helpers ---------------------------------------------------

  function findUser(email) {
    var e = String(email || "").toLowerCase().trim();
    for (var i = 0; i < USERS.length; i++) {
      if (String(USERS[i].email || "").toLowerCase().trim() === e) return USERS[i];
    }
    return null;
  }

  async function hashFor(email, password) {
    var msg = String(email || "").toLowerCase().trim() + "\n" + String(password || "");
    var buf = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(msg));
    var bytes = new Uint8Array(buf);
    var hex = "";
    for (var i = 0; i < bytes.length; i++) {
      hex += bytes[i].toString(16).padStart(2, "0");
    }
    return hex;
  }

  // --- session --------------------------------------------------------------

  function readSession() {
    var raw;
    try {
      raw = localStorage.getItem(STORAGE_KEY);
    } catch (e) {
      return null;
    }
    if (!raw) return null;
    var s;
    try {
      s = JSON.parse(raw);
    } catch (e) {
      return null;
    }
    if (!s || !s.email || !s.ts) return null;
    if (Date.now() - Number(s.ts) > MAX_AGE_MS) return null;
    if (!findUser(s.email)) return null; // revoked or renamed
    return s;
  }

  function writeSession(email) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ email: email, ts: Date.now() }));
    } catch (e) {
      /* private mode / storage disabled — login simply won't persist */
    }
  }

  function clearSession() {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (e) {}
  }

  function currentViews() {
    var s = readSession();
    if (!s) return [];
    var u = findUser(s.email);
    return u && Array.isArray(u.views) ? u.views : [];
  }

  // --- view filtering per page ---------------------------------------------

  // Map a shell engine button/iframe to the view key(s) that unlock it.
  function engineAllowed(engine, views) {
    if (engine === "historical") return views.indexOf("historical") !== -1;
    if (engine === "cash") return views.indexOf("cash") !== -1;
    if (engine === "projections") {
      for (var i = 0; i < views.length; i++) {
        if (views[i].indexOf("proj:") === 0) return true;
      }
      return false;
    }
    return false;
  }

  function filterShell(views) {
    var buttons = document.querySelectorAll("#view-nav button[data-view]");
    var firstAllowed = null;
    buttons.forEach(function (btn) {
      var engine = btn.dataset.view;
      var iframe = document.getElementById("view-" + engine);
      if (engineAllowed(engine, views)) {
        if (!firstAllowed) firstAllowed = btn;
      } else {
        btn.remove();
        if (iframe) iframe.remove(); // also stops its data from loading
      }
    });
    if (firstAllowed) firstAllowed.click();
  }

  function filterProjection(views) {
    var buttons = document.querySelectorAll("#view-tabs button[data-view]");
    var firstAllowed = null;
    buttons.forEach(function (btn) {
      var key = "proj:" + btn.dataset.view;
      var section = document.querySelector('main > section[data-view="' + btn.dataset.view + '"]');
      if (views.indexOf(key) !== -1) {
        if (!firstAllowed) firstAllowed = btn;
      } else {
        btn.remove();
        if (section) section.remove();
      }
    });
    if (firstAllowed) firstAllowed.click();
    return !!firstAllowed;
  }

  // --- UI: overlay + chip ---------------------------------------------------

  function buildOverlay() {
    var overlay = document.createElement("div");
    overlay.id = "auth-overlay";
    overlay.innerHTML =
      '<form id="auth-form" autocomplete="on">' +
      '  <div class="auth-brand">TOC <span>Strategic</span> Dashboard</div>' +
      '  <label>Email<input type="email" id="auth-email" autocomplete="username" required></label>' +
      '  <label>Password<input type="password" id="auth-password" autocomplete="current-password" required></label>' +
      '  <button type="submit">Sign in</button>' +
      '  <p id="auth-error" role="alert" hidden>Incorrect email or password.</p>' +
      "</form>";
    document.body.appendChild(overlay);

    var form = overlay.querySelector("#auth-form");
    var errEl = overlay.querySelector("#auth-error");
    form.addEventListener("submit", async function (ev) {
      ev.preventDefault();
      errEl.hidden = true;
      var email = overlay.querySelector("#auth-email").value;
      var password = overlay.querySelector("#auth-password").value;
      var u = findUser(email);
      var ok = false;
      if (u) {
        try {
          ok = (await hashFor(email, password)) === u.passwordHash;
        } catch (e) {
          ok = false;
        }
      }
      if (ok) {
        writeSession(email);
        location.reload();
      } else {
        errEl.hidden = false;
      }
    });
    overlay.querySelector("#auth-email").focus();
  }

  function buildNoAccess(message) {
    var overlay = document.createElement("div");
    overlay.id = "auth-overlay";
    overlay.innerHTML =
      '<div class="auth-noaccess">' +
      '  <div class="auth-brand">TOC <span>Strategic</span> Dashboard</div>' +
      "  <p>" + message + "</p>" +
      '  <button type="button" id="auth-logout-btn">Log out</button>' +
      "</div>";
    document.body.appendChild(overlay);
    overlay.querySelector("#auth-logout-btn").addEventListener("click", logout);
  }

  function buildChip(email) {
    var chip = document.createElement("div");
    chip.id = "auth-chip";
    chip.innerHTML =
      "<span>Signed in as <strong></strong></span>" +
      '<button type="button">Log out</button>';
    chip.querySelector("strong").textContent = email;
    chip.querySelector("button").addEventListener("click", logout);
    document.body.appendChild(chip);
  }

  function logout() {
    clearSession();
    location.reload();
  }

  window.AUTH = {
    session: readSession,
    views: currentViews,
    logout: logout,
  };

  // --- bootstrap ------------------------------------------------------------

  function boot() {
    var page = document.body.getAttribute("data-page") || "";
    var session = readSession();

    // Pages embedded in the shell never show their own login UI — the shell
    // already gated entry. They only apply the view filter (projection tabs).
    if (FRAMED) {
      if (session) {
        if (page === "projection") filterProjection(currentViews());
      }
      return;
    }

    if (!session) {
      buildOverlay();
      return;
    }

    var views = currentViews();

    if (page === "shell") {
      filterShell(views);
    } else if (page === "projection") {
      if (!filterProjection(views)) {
        buildNoAccess("Your account has no projection views assigned.");
        return;
      }
    } else if (page === "cash") {
      if (views.indexOf("cash") === -1) {
        buildNoAccess("You don't have access to the Cash Position view.");
        return;
      }
    } else if (page === "historical") {
      if (views.indexOf("historical") === -1) {
        buildNoAccess("You don't have access to the Historical Performance view.");
        return;
      }
    }

    buildChip(session.email);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
