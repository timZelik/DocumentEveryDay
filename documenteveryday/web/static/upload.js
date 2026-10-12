"use strict";

// Upload flow: create a batch → stream each video (with progress) → start processing → go to review.

const videoInput = document.getElementById("video-input");
const uploadButton = document.getElementById("upload-button");
const progressArea = document.getElementById("upload-progress");

function element(tagName, className, text) {
  const created = document.createElement(tagName);
  if (className) created.className = className;
  if (text !== undefined) created.textContent = text;
  return created;
}

async function postJson(url) {
  const response = await fetch(url, { method: "POST" });
  if (response.status === 401) location.href = "/login?next=/upload";
  if (!response.ok) throw new Error((await response.json()).detail || response.statusText);
  return response.json();
}

function progressRow(file) {
  const row = element("div");
  const label = element("p", "muted", `${file.name} · ${(file.size / 1e9).toFixed(2)} GB`);
  const bar = element("progress");
  bar.max = 1;
  bar.value = 0;
  row.append(label, bar);
  progressArea.append(row);
  return { label, bar };
}

// XMLHttpRequest, not fetch, because only XHR reports upload progress on iOS Safari.
function uploadVideo(batchId, file, row) {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("PUT", `/api/batches/${batchId}/videos?filename=${encodeURIComponent(file.name)}`);
    request.setRequestHeader("Content-Type", "application/octet-stream");
    request.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) row.bar.value = event.loaded / event.total;
    });
    request.addEventListener("load", () =>
      request.status === 200 ? resolve() : reject(new Error(`${file.name}: ${request.responseText}`)),
    );
    request.addEventListener("error", () => reject(new Error(`${file.name}: the connection dropped`)));
    request.send(file);
  });
}

async function uploadEvening() {
  const files = [...videoInput.files];
  uploadButton.disabled = true;
  progressArea.replaceChildren();
  try {
    const { batch_id: batchId } = await postJson("/api/batches");
    for (const file of files) {
      const row = progressRow(file);
      await uploadVideo(batchId, file, row);
      row.label.textContent = `${file.name} · uploaded`;
    }
    const { review_url: reviewUrl } = await postJson(`/api/batches/${batchId}/start`);
    progressArea.append(element("p", "", "Uploaded. Processing has started; you'll get a push when it's done."));
    const reviewLink = element("a", "", "Watch progress →");
    reviewLink.href = reviewUrl;
    progressArea.append(reviewLink);
  } catch (error) {
    progressArea.append(element("p", "", `Upload failed: ${error.message}`));
    uploadButton.disabled = false;
  }
}

videoInput.addEventListener("change", () => (uploadButton.disabled = videoInput.files.length === 0));
uploadButton.addEventListener("click", uploadEvening);
