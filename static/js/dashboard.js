// static/js/dashboard.js
document.addEventListener('DOMContentLoaded', function () {
  // Select-all helper (matches #select-all and .ing-check in your template)
  var selectAll = document.getElementById('select-all');
  if (selectAll) {
    selectAll.addEventListener('change', function () {
      document.querySelectorAll('.ing-check').forEach(function (cb) {
        cb.checked = selectAll.checked;
      });
    });
  }

  // “Scan with camera” button → opens camera on mobile / picker on desktop
  var scanBtn = document.getElementById('scan-btn');
  var upload = document.getElementById('upload');
  if (scanBtn && upload) {
    scanBtn.addEventListener('click', function () {
      upload.click();
    });
  }
});
