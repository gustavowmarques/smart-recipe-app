document.addEventListener("DOMContentLoaded", function () {
  function toggle(btn) {
    // Prefer explicit target by ID
    const targetId = btn.getAttribute("data-target");
    let input = targetId ? document.querySelector(`#${targetId}`) : null;

    // Fallback: look for an input in the same input-group
    if (!input) {
      const group = btn.closest(".input-group");
      if (group) {
        input = group.querySelector('input[type="password"], input[type="text"]');
      }
    }
    if (!input) return;

    const isHidden = input.type === "password";
    input.type = isHidden ? "text" : "password";

    // swap icon if present (Bootstrap Icons optional)
    const icon = btn.querySelector("i");
    if (icon) {
      icon.classList.toggle("bi-eye", !isHidden);
      icon.classList.toggle("bi-eye-slash", isHidden);
    }

    // accessibility
    btn.setAttribute("aria-label", isHidden ? "Hide password" : "Show password");
  }

  document.addEventListener("click", function (e) {
    const btn = e.target.closest(".toggle-password");
    if (btn) toggle(btn);
  });
});
