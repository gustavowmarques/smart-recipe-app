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

// Image preview for "Upload photo of ingredients"
document.addEventListener('DOMContentLoaded', () => {
  const file = document.getElementById('upload');
  const wrap = document.getElementById('upload-preview');
  const img  = document.getElementById('upload-preview-img');

  if (!file || !wrap || !img) return;

  let currentURL = null;

  const hidePreview = () => {
    if (currentURL) URL.revokeObjectURL(currentURL);
    currentURL = null;
    img.removeAttribute('src');
    wrap.classList.add('d-none');
  };

  file.addEventListener('change', () => {
    const f = file.files && file.files[0];
    if (!f || !/^image\//.test(f.type)) {
      hidePreview();
      return;
    }
    if (currentURL) URL.revokeObjectURL(currentURL);
    currentURL = URL.createObjectURL(f);
    img.src = currentURL;
    wrap.classList.remove('d-none');
  });

  const form = document.getElementById('pantry-photo-form');
  if (form) form.addEventListener('reset', hidePreview);
});
