(function () {
  function getCsrf() {
    const m = document.cookie.match(/csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }

  const fileInput   = document.getElementById("upload");
  const submitBtn   = document.getElementById("upload-submit");
  const progress    = document.getElementById("upload-progress");
  const progressBar = progress ? progress.querySelector(".progress-bar") : null;
  const statusEl    = document.getElementById("upload-status");
  const startForm   = document.getElementById("start-extract-form");
  const s3KeyInput  = document.getElementById("s3_key");

  // READ FROM TEMPLATE-PROVIDED DATA ATTRIBUTE (fallback keeps dev usable)
  const presignEndpoint =
    document.body.getAttribute("data-presign-url") || "/api/s3/presign-upload/";

  if (!fileInput || !submitBtn || !startForm || !s3KeyInput) return;

  // Optional: “Scan with camera” just triggers the file input
  const scanBtn = document.getElementById("scan-btn");
  if (scanBtn) {
    scanBtn.addEventListener("click", function () {
      fileInput.click();
    });
  }

  function showProgress(pct, text) {
    if (!progress || !progressBar) return;
    progress.classList.remove("d-none");
    progressBar.style.width = pct + "%";
    progressBar.textContent = pct + "%";
    if (statusEl) statusEl.textContent = text || "";
  }

  async function presign(filename, contentType) {
    const resp = await fetch(presignEndpoint, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrf(),
      },
      body: JSON.stringify({
        filename,
        content_type: contentType || "image/jpeg",
      }),
    });
    if (!resp.ok) throw new Error("Failed to presign upload.");
    return resp.json();
  }

  function uploadToS3(url, fields, file, onProgress) {
    return new Promise((resolve, reject) => {
      const form = new FormData();
      Object.entries(fields).forEach(([k, v]) => form.append(k, v));
      form.append("file", file);

      const xhr = new XMLHttpRequest();
      xhr.open("POST", url);

      xhr.upload.addEventListener("progress", (e) => {
        if (e.lengthComputable && onProgress) {
          const pct = Math.max(1, Math.round((e.loaded / e.total) * 100));
          onProgress(pct);
        }
      });

      xhr.onload = () => {
        // S3 success: 204 (or 201 with XML)
        if (xhr.status === 204 || xhr.status === 201) resolve();
        else reject(new Error("S3 upload failed: " + xhr.status));
      };
      xhr.onerror = () => reject(new Error("Network error during S3 upload."));
      xhr.send(form);
    });
  }

  submitBtn.addEventListener("click", async function (e) {
    const file = fileInput.files && fileInput.files[0];

    // If no file, let the normal (legacy) form submit happen
    if (!file) return;

    // Intercept and do direct-to-S3
    e.preventDefault();

    try {
      showProgress(1, "Requesting upload slot…");
      const { url, fields, key } = await presign(file.name, file.type);

      showProgress(5, "Uploading to S3…");
      await uploadToS3(url, fields, file, (pct) => showProgress(pct, "Uploading…"));

      showProgress(100, "Processing…");
      // Handoff to Django with the S3 key so it can run extraction
      s3KeyInput.value = key;
      startForm.submit();
    } catch (err) {
      console.error(err);
      if (statusEl) statusEl.textContent = "Upload failed. Please try again.";
      if (progressBar) progressBar.classList.add("bg-danger");
    }
  });
})();
