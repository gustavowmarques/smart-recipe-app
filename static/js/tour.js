(function () {

  // Prevent double-initialization if tour.js is accidentally included twice
  if (window.__SRTourLoaded) { 
    console.debug('tour.js already loaded; skipping second init');
    return; 
  }
  window.__SRTourLoaded = true;

  // Global z-order for the tour UI (overlay < spotlight < tip)
var Z = {
  overlay:  2147483600,
  spot:     2147483601,
  tip:      2147483602,
  elevated: 2147483599 // target sits just under the spotlight/tip
};


  // -------------------------
  // Utilities
  // -------------------------
  const $  = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));
  const on = (el, evt, fn) => el && el.addEventListener(evt, fn, false);

  const LS = {
    get(k, d = null) { try { return JSON.parse(localStorage.getItem(k)); } catch { return d; } },
    set(k, v)        { try { localStorage.setItem(k, JSON.stringify(v)); } catch {} },
    del(k)           { try { localStorage.removeItem(k); } catch {} }
  };

  const clamp = (n, min, max) => Math.max(min, Math.min(max, n));
  const inViewport = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0 &&
           r.top >= 0 && r.left >= 0 &&
           r.bottom <= (window.innerHeight || document.documentElement.clientHeight) &&
           r.right  <= (window.innerWidth  || document.documentElement.clientWidth);
  };

  function reveal(el) {
    if (!el) return;
    try { el.scrollIntoView({ behavior: "smooth", block: "center", inline: "center" }); }
    catch { el.scrollIntoView(); }
  }

  // -------------------------
  // DOM (overlay + tooltip)
  // -------------------------
  function createEl(tag, cls, html) {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (html != null) el.innerHTML = html;
    return el;
  }

  function buildUI() {
    const overlay = createEl("div", "sr-tour-overlay", "");
    overlay.setAttribute("aria-hidden", "true");

    const spot = createEl("div", "sr-tour-spotlight", "");
    spot.setAttribute("aria-hidden", "true");

    const tip = createEl("div", "sr-tour-tip", "");
    tip.setAttribute("role", "dialog");
    tip.setAttribute("aria-modal", "true");
    tip.setAttribute("aria-live", "polite");

    tip.innerHTML = `
      <div class="sr-tour-header">
        <div class="sr-tour-title"></div>
        <button type="button" class="sr-tour-close" aria-label="Close">×</button>
      </div>
      <div class="sr-tour-body"></div>
      <div class="sr-tour-footer">
        <div class="sr-tour-steps"></div>
        <div class="sr-tour-actions">
          <button type="button" class="sr-tour-prev" aria-label="Previous">Back</button>
          <button type="button" class="sr-tour-next" aria-label="Next">Next</button>
          <button type="button" class="sr-tour-done" aria-label="Done">Done</button>
        </div>
      </div>
    `;

    // Make sure these layers sit above everything
    overlay.style.zIndex = Z.overlay;
    spot.style.zIndex    = Z.spot;
    tip.style.zIndex     = Z.tip;

    document.body.appendChild(overlay);
    document.body.appendChild(spot);
    document.body.appendChild(tip);

    return {
      overlay,
      spot,
      tip,
      title: $(".sr-tour-title", tip),
      body:  $(".sr-tour-body",  tip),
      steps: $(".sr-tour-steps", tip),
      prev:  $(".sr-tour-prev",  tip),
      next:  $(".sr-tour-next",  tip),
      done:  $(".sr-tour-done",  tip),
      close: $(".sr-tour-close", tip),
    };
  }


function positionTip(ui, targetEl) {
  if (!SRTour._running || !ui) return; // guard

  const tip = ui.tip;
  tip.style.opacity = "0";
  tip.style.top = "-9999px";
  tip.style.left = "-9999px";

  requestAnimationFrame(() => {
    if (!SRTour._running) return; // guard in case tour ended

    const pad = 12;
    const vw = window.innerWidth;
    const vh = window.innerHeight;
    const tRect = targetEl ? targetEl.getBoundingClientRect() : null;
    const tipRect = tip.getBoundingClientRect();

    const isFixed = getComputedStyle(tip).position === "fixed";
    const offX = isFixed ? 0 : window.scrollX;
    const offY = isFixed ? 0 : window.scrollY;

    let top, left;

    if (tRect) {
      const belowTop = tRect.bottom + pad;
      const aboveTop = tRect.top - tipRect.height - pad;

      left = tRect.left + (tRect.width / 2) - (tipRect.width / 2);
      left = clamp(left, pad, vw - tipRect.width - pad);

      if (belowTop + tipRect.height <= vh - pad)      top = belowTop;
      else if (aboveTop >= pad)                        top = aboveTop;
      else { top = (vh - tipRect.height) / 2; left = (vw - tipRect.width) / 2; }
    } else {
      top  = (vh - tipRect.height) / 2;
      left = (vw - tipRect.width)  / 2;
    }

    tip.style.top  = `${Math.round(top + offY)}px`;
    tip.style.left = `${Math.round(left + offX)}px`;
    tip.style.opacity = "1";
  });
}



  function escapeHTML(s) {
    const map = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" };
    return String(s).replace(/[&<>"']/g, (m) => map[m]);
  }

  function getTarget(selector) {
    if (!selector) return null;
    try {
      const el = document.querySelector(selector);
      if (el) return el;
    } catch {}
    // allow data-tour="key"
    try {
      const el2 = document.querySelector(`[data-tour="${selector}"]`);
      if (el2) return el2;
    } catch {}
    return null;
  }

  // -------------------------
  // Core: SRTour
  // -------------------------
  const SRTour = {
    VERSION: "1.1.0",
    _ui: null,
    _steps: [],
    _pageKey: "",
    _index: 0,
    _running: false,                     // prevent double starts / overlap
    _resumeKey: "sr.tour.resume",        // resume across pages
    _seenKey(page) { return `sr.tour.seen.${page}`; },

    _currentEl: null, _savedStyle: null, // elevation bookkeeping

    // Public API -------------------------------------------------------
    register(pageKey, steps) {
      // Accept array OR function returning an array (dynamic steps)
      SRTour._registry[pageKey] = steps;
    },

    start(pageKey, startIndex) {
      if (SRTour._running) SRTour.done();  // ensure only one instance runs
      let steps = SRTour._registry[pageKey] || [];
      if (typeof steps === "function") { try { steps = steps() || []; } catch { steps = []; } }
      steps = (Array.isArray(steps) ? steps : []).map(normalizeStep);
      if (!steps.length) return;

      SRTour._pageKey = pageKey;
      SRTour._steps   = steps.filter(Boolean);
      SRTour._index   = clamp(Number(startIndex || 0), 0, SRTour._steps.length - 1);
      SRTour._running = true;

      if (!SRTour._ui) SRTour._ui = buildUI();
      SRTour._bindUI();
      SRTour._showStep(SRTour._index);

      document.documentElement.classList.add("sr-tour-active");
      LS.set(SRTour._seenKey(pageKey), true);
    },

    shouldAutoStart(pageKey) {
      return !LS.get(SRTour._seenKey(pageKey), false);
    },

    next() {
      const step = SRTour._steps[SRTour._index];
      // Cross-page navigation hook
      if (step && (step.goToTour || step.goToUrl || step.clickSelector)) {
        const resume = { tour: step.goToTour || SRTour._pageKey, index: (step.resumeIndex || 0) };
        LS.set(SRTour._resumeKey, resume);
        if (step.clickSelector) {
          const link = getTarget(step.clickSelector);
          if (link) { link.click(); return; }
        }
        if (step.goToUrl) { location.href = step.goToUrl; return; }
      }

      if (SRTour._index < SRTour._steps.length - 1) {
        SRTour._showStep(SRTour._index + 1);
      } else {
        SRTour.done();
      }
    },

    prev() {
      if (SRTour._index > 0) SRTour._showStep(SRTour._index - 1);
    },

    done() {
      SRTour._teardownHighlight();
      SRTour._resetElevation();
      if (SRTour._ui) {
        SRTour._ui.tip.style.display = "none";
        SRTour._ui.overlay.style.display = "none";
        SRTour._ui.spot.style.display = "none";
      }
      document.documentElement.classList.remove("sr-tour-active");
      SRTour._running = false;
      LS.del(SRTour._resumeKey);
    },

    reset(pageKey) {
      if (pageKey) LS.del(SRTour._seenKey(pageKey));
      else Object.keys(SRTour._registry).forEach(k => LS.del(SRTour._seenKey(k)));
    },

    // Internal ---------------------------------------------------------
    _registry: {},

    _bindUI() {
      const { prev, next, done, close, overlay } = SRTour._ui;
      prev.onclick = SRTour.prev;
      next.onclick = SRTour.next;
      done.onclick = SRTour.done;
      close.onclick = SRTour.done;
      overlay.onclick = SRTour.done;

      // Keys
      on(document, "keydown", (e) => {
        if (!SRTour._running) return;
        if (e.key === "Escape") SRTour.done();
        if (e.key === "ArrowRight" || e.key === "Enter") SRTour.next();
        if (e.key === "ArrowLeft") SRTour.prev();
      });

      // Reflow
      let raf;
      const reflow = () => {
        cancelAnimationFrame(raf);
        raf = requestAnimationFrame(() => {
          const step = SRTour._steps[SRTour._index];
          if (!step) return;
          const target = getTarget(step.selector);
          SRTour._positionHighlight(target);
          positionTip(SRTour._ui, target);
        });
      };
      on(window, "resize", reflow);
      on(window, "scroll", reflow);
    },

    _showStep(i) {
      i = clamp(i, 0, SRTour._steps.length - 1);
      SRTour._index = i;

      const step = SRTour._steps[i];
      const ui = SRTour._ui;

      ui.overlay.style.display = "block";
      ui.spot.style.display = "block";
      ui.tip.style.display = "block";

      ui.title.textContent = step.title || "";
      ui.body.innerHTML = step.html || escapeHTML(step.text || ""); // <- ensures description is always shown

      ui.steps.textContent = `${i + 1} / ${SRTour._steps.length}`;
      ui.prev.disabled = i === 0;
      ui.next.style.display = (i === SRTour._steps.length - 1) ? "none" : "inline-block";
      ui.done.style.display = (i === SRTour._steps.length - 1) ? "inline-block" : "none";

      // Before moving, restore previous elevation
      SRTour._resetElevation();

      const target = getTarget(step.selector);
      if (target && !inViewport(target)) reveal(target);
      if (target) SRTour._elevateTarget(target);
      SRTour._positionHighlight(target);
      positionTip(ui, target);

      // Reposition again shortly after smooth scroll completes
      setTimeout(() => positionTip(ui, target), 250);

    },

    _positionHighlight(target) {
      const { spot } = SRTour._ui;
      if (!target) { spot.style.display = "none"; return; }
      spot.style.display = "block";
      const r = target.getBoundingClientRect();
      const pad = 6;
      spot.style.top    = `${Math.max(0, r.top  - pad + window.scrollY)}px`;
      spot.style.left   = `${Math.max(0, r.left - pad + window.scrollX)}px`;
      spot.style.width  = `${r.width  + pad * 2}px`;
      spot.style.height = `${r.height + pad * 2}px`;
    },

    _teardownHighlight() { if (SRTour._ui) SRTour._ui.spot.removeAttribute("style"); },

    _elevateTarget(el) {
      const computed = window.getComputedStyle(el);
      const originalPosition = el.style.position || "";
      const originalZ        = el.style.zIndex || "";

      if (computed.position === "static") el.style.position = "relative";
      el.style.zIndex = "10002";

      SRTour._currentEl = el;
      SRTour._savedStyle = { position: originalPosition, zIndex: originalZ };
    },

    _resetElevation() {
      if (!SRTour._currentEl) return;
      try {
        SRTour._currentEl.style.zIndex  = SRTour._savedStyle.zIndex;
        SRTour._currentEl.style.position = SRTour._savedStyle.position;
      } catch {}
      SRTour._currentEl = null;
      SRTour._savedStyle = null;
    },
  };

  // Expose globally (and legacy aliases)
  window.SRTour = SRTour;
  window.SmartRecipeTour = window.SmartRecipeTour || SRTour;
  window.startTour = window.startTour || function (name) {
    const page = name || (document.body?.dataset?.page || "home");
    SRTour.start(page);
  };

  // -------------------------
  // Step normalization
  // -------------------------
  function normalizeStep(s) {
    if (!s) return null;
    return {
      title:    s.title || "",
      text:     s.text  || "",
      html:     s.html  || "",
      selector: s.selector || "",
      // optional cross-page navigation:
      goToTour: s.goToTour || null,          // name of the tour on next page
      goToUrl:  s.goToUrl  || null,          // explicit URL (fallback)
      clickSelector: s.clickSelector || null,// selector of link to click for nav
      resumeIndex: typeof s.resumeIndex === "number" ? s.resumeIndex : 0
    };
  }

  // -------------------------
  // Default tours
  // -------------------------

  // HOME (logged-out): Tour + Login + Register with brief descriptions
  SRTour.register("home", function () {
    const steps = [];

    // Welcome / hero headline (anchor is the hero container)
    steps.push({
      title: "Welcome to Smart Recipe",
      text:  "From fridge → recipe in seconds. Save ingredients, get smart recipe ideas, build meal plans, and hit your targets.",
      selector: '[data-tour="home.hero"], h1.display-5'
    });

    // Take a tour button
    steps.push({
      title: "Take a quick tour",
      text:  "Explore the app in under a minute. No account needed.",
      selector: '[data-tour-start], #startTourBtn'
    });

    // Login CTA
    steps.push({
      title: "Already have an account?",
      text:  "Log in to access your saved ingredients, favorites, meal plan, and targets.",
      selector: '[data-tour="home.cta.login"], a[href*="login"]'
    });

    // Register CTA
    steps.push({
      title: "New here? Create your account",
      text:  "Register for free to save your pantry, favorite recipes, and meal plans.",
      selector: '[data-tour="home.cta.signup"], a[href*="register"], a[href*="signup"]'
    });

    return steps;
  });

  // Dashboard — top → bottom flow (navbar first, Food/Drink last)
  SRTour.register("dashboard", [
    // NAVBAR (top of page)
    {
      title: "Favorites",
      text:  "Jump back to recipes you’ve saved.",
      selector: '[data-tour="nav.favorites"], a[href$="/favorites/"]'
    },
    {
      title: "Targets",
      text:  "Track daily calories and macros. As you plan meals or log food, progress updates automatically.",
      selector: '[data-tour="nav.targets"], a[href$="/targets/"]'
    },
    {
      title: "Meal plan",
      text:  "Plan your week by placing recipes into each day. You can come here after generating recipes.",
      selector: '[data-tour="nav.mealplan"], a[href$="/meal-plan/"]'
      // NOTE: no goToTour/clickSelector here—Dashboard tour stays on this page.
    },

    // MAIN CONTENT (moving down the page)
    {
      title: "Add ingredients",
      text:  "Type an item, quantity, and unit to add it to your pantry.",
      selector: '[data-tour="dashboard.add"], form[action$="add-ingredient/"], .add-ingredient-form'
    },
    {
      title: "Scan with Camera / Upload",
      text:  "Upload a photo or scan directly. We’ll list detected ingredients for you to confirm.",
      selector: '[data-tour="dashboard.scan"], #pantry-photo-form, button#scan-btn'
    },
    {
      title: "Select ingredients for recipes",
      text:  "Tick items to tell the generator what to use. If nothing is selected, we’ll suggest recipes with a smart pick from your pantry.",
      selector: '[data-tour="dashboard.pantry"], #pantry-table, .pantry-table, .table-responsive table, .table'
    },
    {
      title: "Search / Generate recipes",
      text:  "Click here to generate recipes you can actually make with the checked items.",
      selector: '[data-tour="dashboard.generate"], [data-tour="dashboard.recipes"], button[type="submit"]'
    },

    // BOTTOM (final step at the Food/Drink dropdown)
    {
      title: "Choose recipe type",
      text:  "Pick Food or Drink. This helps tailor the suggestions.",
      selector: '[data-tour="dashboard.type"], select[name="type"], #id_type'
    }
  ]);


  // MEAL PLAN
  SRTour.register("meal-plan", [
    {
      title: "Plan your week",
      text:  "Add recipes to Breakfast, Lunch, Dinner or Snack for each day.",
      selector: '[data-tour="mealplan.table"], .table-responsive, .meal-plan-grid'
    },
    {
      title: "Pick from Favorites",
      text:  "Save a recipe to Favorites, then quickly drop it into a slot.",
      selector: '[data-tour="mealplan.pick"], .favorites-picker'
    },
    {
      title: "Navigate weeks",
      text:  "Use Prev/Next to switch weeks. Today’s items also show on Targets.",
      selector: '[data-tour="mealplan.nav"], .btn-prev, .btn-next'
    },
    {
      title: "Track your targets",
      text:  "Let’s see how your meals impact calories and macros.",
      selector: '[data-tour="nav.targets"], a[href$="/targets/"]',
      goToTour: "targets",
      clickSelector: '[data-tour="nav.targets"], a[href$="/targets/"]',
      resumeIndex: 0
    }
  ]);

  // TARGETS
  SRTour.register("targets", [
    {
      title: "Set your targets",
      text:  "Start by setting your daily calories and macro goals.",
      selector: '[data-tour="targets.form"], form[action*="targets"]'
    },
    {
      title: "Quick log",
      text:  "Log a custom meal here. Use Quantity for multiple servings.",
      selector: '[data-tour="targets.quicklog"], #quick-log-form'
    },
    {
      title: "Progress",
      text:  "As you log meals or add items to today’s Meal Plan, progress updates automatically.",
      selector: '[data-tour="targets.progress"], .targets-progress'
    },
    {
      title: "Suggestions",
      text:  "We suggest protein-weighted ideas to help close your gaps.",
      selector: '[data-tour="targets.suggestions"], .targets-suggestions'
    }
  ]);

  // -------------------------
  // Auto-start + manual start
  // -------------------------
  document.addEventListener("DOMContentLoaded", function () {
    const pageKey = document.body?.dataset?.page || "";

    // Manual starters: [data-tour-start] and (legacy) #startTourBtn
    const starters = [
      ...$$('[data-tour-start]'),
      ...($('#startTourBtn') ? [$('#startTourBtn')] : [])
    ];
    starters.forEach((el) => {
      on(el, "click", (e) => {
        e.preventDefault();
        const name = el.getAttribute("data-tour-name") || pageKey || "home";
        SRTour.start(name);
      });
    });

    // Deep-link start via ?tour=NAME
    const q = new URLSearchParams(location.search);
    const viaUrl = q.get("tour");
    if (viaUrl) {
      SRTour.start(viaUrl);
      return;
    }

    // Resume after cross-page navigation
    const resume = LS.get(SRTour._resumeKey);
    if (resume && resume.tour) {
      LS.del(SRTour._resumeKey);
      // Small delay lets layout settle before positioning
      setTimeout(() => SRTour.start(resume.tour, resume.index || 0), 60);
      return;
    }

    // Autostart only if not seen, and only when there is no explicit starter visible
    if (pageKey && SRTour.shouldAutoStart(pageKey) && starters.length === 0) {
      // Delay a touch so user clicks don’t cause overlap with autostart
      setTimeout(() => SRTour.start(pageKey), 250);
    }
  });
})();
