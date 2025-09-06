// static/js/pantry-selection.js
(function () {
  function byId(id) { return document.getElementById(id); }
  function qsa(sel, root) { return Array.from((root || document).querySelectorAll(sel)); }

  function getSelectedIds() {
    return qsa('.pantry-check')
      .filter(c => c.checked)
      .map(c => c.value)
      .join(',');
  }

  // Keep the "selected_ids" hidden input in sync on submit
  function wireForms() {
    const forms = qsa('form[data-selected-target]');
    forms.forEach(form => {
      const hiddenId = form.getAttribute('data-selected-target');
      const hidden = byId(hiddenId);
      if (!hidden) return;

      form.addEventListener('submit', function () {
        hidden.value = getSelectedIds();
      });
    });
  }

  // Select-all toggle
  function wireSelectAll() {
    const selectAll = byId('selectAllPantry');
    if (!selectAll) return;

    const checks = qsa('.pantry-check');
    selectAll.addEventListener('change', function () {
      checks.forEach(cb => cb.checked = selectAll.checked);
    });
  }

  function init() {
    wireForms();
    wireSelectAll();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
