"use strict";

// The review page: one clip at a time. Swipe right approves (share sheet + caption copied), left rejects.

const SWIPE_THRESHOLD_PIXELS = 90;
const POLL_INTERVAL_MILLISECONDS = 10000;
const FINISHED_BATCH_STATUSES = ["ready", "failed"];

const state = { payload: null, clipIndex: 0, videoFilesByClipId: new Map() };

// ---------- data ----------

function batchIdFromPath() {
  const match = location.pathname.match(/^\/review\/(\d+)/);
  return match ? match[1] : "latest";
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, options);
  if (response.status === 401) {
    location.href = `/login?next=${encodeURIComponent(location.pathname)}`;
    throw new Error("signed out");
  }
  if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
  return response.json();
}

function playableClips() {
  return state.payload ? state.payload.clips.filter((clip) => clip.is_playable) : [];
}

function currentClip() {
  return playableClips()[state.clipIndex];
}

function firstPendingClipIndex() {
  const index = playableClips().findIndex((clip) => clip.review_status === "pending");
  return index === -1 ? playableClips().length : index;
}

async function loadBatch() {
  const wasShowingCard = Boolean(currentClip());
  try {
    state.payload = await fetchJson(`/api/batches/${batchIdFromPath()}`);
  } catch (error) {
    renderEmptyState("No batches yet", "Upload an evening of footage to get started.", true);
    return;
  }
  renderHeader();
  // Polling must never yank away the clip being watched; it only fills an empty screen.
  if (!wasShowingCard) {
    state.clipIndex = firstPendingClipIndex();
    renderCurrentCard();
  }
  if (!FINISHED_BATCH_STATUSES.includes(state.payload.batch.status)) {
    setTimeout(loadBatch, POLL_INTERVAL_MILLISECONDS);
  }
}

function recordDecision(clip, decision) {
  clip.review_status = decision;
  renderHeader();
  return fetchJson(`/api/clips/${clip.id}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision }),
  }).catch(() => showToast("Could not save that decision. Check the connection."));
}

// ---------- video files for the share sheet ----------

function videoFileName(clip) {
  const safeTitle = (clip.title || `clip ${clip.id}`).replace(/[^\w\- ]+/g, "").trim() || `clip ${clip.id}`;
  return `${safeTitle}.mp4`;
}

// The share sheet must open inside the swipe gesture, so the file is downloaded before the swipe happens.
function prefetchVideoFile(clip) {
  if (!clip || state.videoFilesByClipId.has(clip.id)) return;
  const entry = { file: null };
  entry.ready = fetch(clip.video_url)
    .then((response) => response.blob())
    .then((blob) => (entry.file = new File([blob], videoFileName(clip), { type: "video/mp4" })));
  state.videoFilesByClipId.set(clip.id, entry);
}

function shareVideoFile(clip) {
  const file = state.videoFilesByClipId.get(clip.id)?.file;
  if (!file || !navigator.canShare || !navigator.canShare({ files: [file] })) {
    return Promise.reject(new Error("not ready"));
  }
  return navigator.share({ files: [file] });
}

// ---------- actions ----------

function approveCurrentClip() {
  const clip = currentClip();
  if (!clip) return;
  if (navigator.clipboard) navigator.clipboard.writeText(clip.clipboard_text).catch(() => {});
  recordDecision(clip, "approved");
  shareVideoFile(clip)
    .then(() => advanceToNextClip())
    .catch((error) => {
      if (error.name === "AbortError") return renderCurrentCard();
      showToast("Caption copied. Tap “Save video” when it's ready.");
      renderCurrentCard();
    });
}

function rejectCurrentClip() {
  const clip = currentClip();
  if (!clip) return;
  recordDecision(clip, "rejected");
  advanceToNextClip();
}

function advanceToNextClip() {
  state.clipIndex = Math.min(state.clipIndex + 1, playableClips().length);
  renderCurrentCard();
}

// ---------- rendering ----------

function element(tagName, className, text) {
  const created = document.createElement(tagName);
  if (className) created.className = className;
  if (text !== undefined) created.textContent = text;
  return created;
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.style.display = "block";
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => (toast.style.display = "none"), 2500);
}

function renderHeader() {
  const { batch, clips, total_cost_dollars: totalCost } = state.payload;
  const pendingCount = clips.filter((clip) => clip.is_playable && clip.review_status === "pending").length;
  const detail = batch.status === "ready" ? `${pendingCount} to review` : batch.status_detail || batch.status;
  document.getElementById("batch-status").textContent = `Batch #${batch.id} · ${detail}`;
  document.getElementById("batch-cost").textContent = `AI cost $${totalCost.toFixed(4)}`;
}

function renderEmptyState(title, message, showUploadLink) {
  const container = document.getElementById("card-container");
  const emptyState = element("div", "empty-state");
  emptyState.append(element("h2", "", title), element("p", "muted", message));
  if (showUploadLink) {
    const link = element("a", "", "Upload footage");
    link.href = "/upload";
    emptyState.append(link);
  }
  container.replaceChildren(emptyState);
}

function renderFinishedState() {
  const { batch, clips } = state.payload;
  if (!FINISHED_BATCH_STATUSES.includes(batch.status)) {
    return renderEmptyState("Processing…", batch.status_detail || "Your phone buzzes when clips are ready.");
  }
  if (batch.status === "failed") return renderEmptyState("This batch failed", batch.status_detail, true);
  const approvedCount = clips.filter((clip) => clip.review_status === "approved").length;
  renderEmptyState("All reviewed", `${approvedCount} approved of ${playableClips().length} clips.`, true);
}

function chipsFor(clip) {
  const chips = element("div", "chips");
  chips.append(
    element("span", "chip", clip.tag.replace("_", " ")),
    element("span", "chip", `score ${clip.score}/10`),
    ...clip.criteria.map((criterion) => element("span", "chip", criterion)),
    element("span", `chip ${clip.qa_status}`, `QA ${clip.qa_status}`),
    element("span", "chip", `$${clip.ai_cost_dollars.toFixed(4)}`),
  );
  if (clip.review_status !== "pending") chips.append(element("span", `chip ${clip.review_status}`, clip.review_status));
  return chips;
}

function qaLineFor(clip) {
  const fixes = clip.qa_fixes.length ? ` Fixes: ${clip.qa_fixes.join("; ")}` : "";
  return element("p", `clip-qa ${clip.qa_status}`, `QA: ${clip.qa_summary}${fixes}`);
}

function decisionLogFor(clip) {
  const log = element("div", "decision-log");
  log.hidden = true;
  const decisions = [...state.payload.batch_decisions, ...clip.ai_decisions];
  if (!decisions.length) log.append(element("p", "muted", "No AI calls were made for this clip."));
  for (const decision of decisions) {
    const scope = decision.clip_id ? "this clip" : "whole batch";
    const heading = `${decision.purpose} · ${scope} · ${decision.input_tokens}+${decision.output_tokens} tokens · $${decision.cost_dollars.toFixed(5)}`;
    log.append(element("strong", "", heading), element("pre", "", JSON.stringify(decision.decision, null, 2)));
  }
  return log;
}

function actionButtonsFor(clip, decisionLog) {
  const actions = element("div", "card-actions");
  const rejectButton = element("button", "reject-button", "✕ Reject");
  const detailsButton = element("button", "", "AI log");
  const approveButton = element("button", "approve-button", clip.review_status === "approved" ? "Save video" : "✓ Approve");
  rejectButton.addEventListener("click", rejectCurrentClip);
  approveButton.addEventListener("click", approveCurrentClip);
  detailsButton.addEventListener("click", () => (decisionLog.hidden = !decisionLog.hidden));
  actions.append(rejectButton, detailsButton, approveButton);
  return actions;
}

function videoFor(clip) {
  const video = element("video");
  Object.assign(video, { src: clip.video_url, autoplay: true, loop: true, muted: true, playsInline: true });
  video.addEventListener("click", () => {
    video.muted = !video.muted;
    showToast(video.muted ? "Muted" : "Sound on");
  });
  return video;
}

function overlayFor(clip) {
  const overlay = element("div", "card-overlay");
  const decisionLog = decisionLogFor(clip);
  overlay.append(
    chipsFor(clip),
    element("h2", "clip-title", clip.title || clip.hook_line || `Clip ${clip.id}`),
    element("p", "clip-reason", `Why: ${clip.pick_reason}`),
    qaLineFor(clip),
    actionButtonsFor(clip, decisionLog),
    decisionLog,
  );
  return overlay;
}

function renderCurrentCard() {
  const clip = currentClip();
  if (!clip) return renderFinishedState();
  prefetchVideoFile(clip);
  prefetchVideoFile(playableClips()[state.clipIndex + 1]);
  const card = element("section", "card");
  card.append(
    videoFor(clip),
    element("div", "swipe-hint approve", "SAVE"),
    element("div", "swipe-hint reject", "NOPE"),
    overlayFor(clip),
  );
  attachSwipeGestures(card);
  document.getElementById("card-container").replaceChildren(card);
}

// ---------- gestures ----------

function attachSwipeGestures(card) {
  let startX = null;
  const hints = { approve: card.querySelector(".swipe-hint.approve"), reject: card.querySelector(".swipe-hint.reject") };
  const isInsideLog = (event) => event.target.closest(".decision-log");

  card.addEventListener("touchstart", (event) => {
    startX = isInsideLog(event) ? null : event.touches[0].clientX;
    card.style.transition = "none";
  });
  card.addEventListener("touchmove", (event) => {
    if (startX === null) return;
    const deltaX = event.touches[0].clientX - startX;
    card.style.transform = `translateX(${deltaX}px) rotate(${deltaX / 40}deg)`;
    hints.approve.style.opacity = Math.max(0, deltaX / SWIPE_THRESHOLD_PIXELS);
    hints.reject.style.opacity = Math.max(0, -deltaX / SWIPE_THRESHOLD_PIXELS);
  });
  card.addEventListener("touchend", (event) => {
    if (startX === null) return;
    const deltaX = event.changedTouches[0].clientX - startX;
    startX = null;
    card.style.transition = "";
    card.style.transform = "";
    if (deltaX > SWIPE_THRESHOLD_PIXELS) approveCurrentClip();
    else if (deltaX < -SWIPE_THRESHOLD_PIXELS) rejectCurrentClip();
  });
}

document.addEventListener("keydown", (event) => {
  if (event.key === "ArrowRight") approveCurrentClip();
  if (event.key === "ArrowLeft") rejectCurrentClip();
});

loadBatch();
