document.addEventListener("DOMContentLoaded", function () {
  document.querySelectorAll(".toggle-password").forEach(function (btn) {
    btn.addEventListener("click", function () {
      const inputId = this.getAttribute("data-target");
      const input = document.getElementById(inputId);
      if (!input) return;

      if (input.type === "password") {
        input.type = "text";
        this.innerHTML = '<i class="bi bi-eye-slash"></i>';
      } else {
        input.type = "password";
        this.innerHTML = '<i class="bi bi-eye"></i>';
      }
    });
  });
});
