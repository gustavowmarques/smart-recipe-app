document.addEventListener('DOMContentLoaded', function () {
  if (!window.bootstrap || !bootstrap.Tooltip) return;
  var triggers = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
  triggers.forEach(function (el) { new bootstrap.Tooltip(el); });
});
