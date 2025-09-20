// Enable Bootstrap tooltips site-wide
document.addEventListener("DOMContentLoaded", () => {
  const triggers = document.querySelectorAll('[data-bs-toggle="tooltip"]');
  [...triggers].forEach(el => new bootstrap.Tooltip(el));
});
