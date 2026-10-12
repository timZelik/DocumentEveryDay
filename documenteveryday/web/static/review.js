"use strict";

// The review page, one clip at a time, Tinder-style:
//   swipe right → approve: caption copied + iOS share sheet ("Save Video")
//   swipe left  → reject
//   swipe up    → needs another look: record a voice note saying why

const SWIPE_THRESHOLD_PIXELS = 90;
const FLY_OFF_MILLISECONDS = 250;
const POLL_INTERVAL_MILLISECONDS = 10000;
const FINISHED_BATCH_STATUSES = ["ready", "failed"];
const VOICE_NOTE_MIME_TYPES = ["audio/mp4", "audio/webm", "audio/ogg"];

const state = { payload: null, passStatus: "pending", queue: [], queueIndex: 0, videoFilesByClipId: new Map() };

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

function clipsWithStatus(reviewStatus) {
  return state.payload.clips.filter((clip) => clip.is_playable && clip.review_status === reviewStatus);
}

function currentClip() {
  return state.queue[state.queueIndex];
}

// A pass walks every clip that had a given status when it started: first "pending", later "needs_review".
function startPass(reviewStatus) {
  state.passStatus = reviewStatus;
  state.queue = clipsWithStatus(reviewStatus);
  state.queueIndex = 0;
  renderCurrentCard();
}

async function loadBatch() {
  const wasShowingCard = Boolean(currentClip());
  try {
    state.payload = await fetchJson(`/api/batches/${batchIdFromPath()}`);
  } catch (error) {
    renderEmptyState("No batches yet", "Upload an evening of footage to get started.", [uploadLink()]);
    return;
  }
  renderHeader();
  if (!wasShowingCard) startPass("pending"); // polling never yanks away the clip being watched
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
  const safeTitle = (clip.title || "").replace(/[^\w\- ]+/g, "").trim() || `clip ${clip.id}`;
  return `${safeTitle}.mp4`;
}

// The share sheet must open inside the swipe gesture, so the file is downloaded before the swipe happens.
function prefetchVideoFile(clip) {
  if (!clip || state.videoFilesByClipId.has(clip.id)) return;
  const entry = { file: null };
  fetch(clip.video_url)
    .then((response) => response.blob())
    .then((blob) => (entry.file = new File([blob], videoFileName(clip), { type: "video/mp4" })))
    .catch(() => state.videoFilesByClipId.delete(clip.id));
  state.videoFilesByClipId.set(clip.id, entry);
}

function shareVideoFile(clip) {
  const file = state.videoFilesByClipId.get(clip.id)?.file;
  if (!file || !navigator.canShare || !navigator.canShare({ files: [file] })) {
    return Promise.reject(new Error("not ready"));
  }
  return navigator.share({ files: [file] });
}

// ---------- the three decisions ----------

function approveCurrentClip() {
  const clip = currentClip();
  if (!clip) return;
  if (navigator.clipboard) navigator.clipboard.writeText(clip.clipboard_text).catch(() => {});
  recordDecision(clip, "approved");
  shareVideoFile(clip) // started first: the share sheet only opens inside the user's gesture
    .then(() => flyOffThenAdvance("right"))
    .catch((error) => {
      if (error.name !== "AbortError") showToast("Caption copied. Tap “Save video” when it's ready.");
      renderCurrentCard();
    });
}

function rejectCurrentClip() {
  const clip = currentClip();
  if (!clip) return;
  recordDecision(clip, "rejected");
  flyOffThenAdvance("left");
}

function sendCurrentClipForFurtherReview() {
  const clip = currentClip();
  if (!clip) return;
  recordDecision(clip, "needs_review");
  openVoiceNoteSheet(clip);
}

function advanceToNextClip() {
  state.queueIndex = Math.min(state.queueIndex + 1, state.queue.length);
  renderCurrentCard();
}

function flyOffThenAdvance(direction) {
  const card = document.querySelector(".card");
  if (!card) return advanceToNextClip();
  const offscreen = { right: "translateX(140vw) rotate(25deg)", left: "translateX(-140vw) rotate(-25deg)", up: "translateY(-140vh)" };
  card.style.transition = `transform ${FLY_OFF_MILLISECONDS}ms ease-in`;
  card.style.transform = offscreen[direction];
  setTimeout(advanceToNextClip, FLY_OFF_MILLISECONDS);
}

// ---------- voice note for "needs review" ----------

function preferredVoiceNoteMimeType() {
  return VOICE_NOTE_MIME_TYPES.find((mimeType) => window.MediaRecorder && MediaRecorder.isTypeSupported(mimeType)) || "";
}

function uploadVoiceNote(clip, blob) {
  return fetchJson(`/api/clips/${clip.id}/voice-note`, {
    method: "PUT",
    headers: { "Content-Type": blob.type.split(";")[0] || "audio/mp4" },
    body: blob,
  }).then((response) => (clip.voice_note_url = response.voice_note_url));
}

function closeSheetAndAdvance(sheet) {
  sheet.remove();
  flyOffThenAdvance("up");
}

function openVoiceNoteSheet(clip) {
  const sheet = element("div", "voice-note-sheet");
  const status = element("p", "muted", "Why does this clip need another look? Tap to record.");
  const recordButton = element("button", "record-button", "● Record");
  const skipButton = element("button", "", "Skip note");
  const actions = element("div", "card-actions");
  actions.append(skipButton, recordButton);
  sheet.append(element("h3", "", "Needs further review"), status, actions);
  document.body.append(sheet);

  let recorder = null;
  let startedAt = 0;
  let timer = null;
  skipButton.addEventListener("click", () => {
    if (recorder && recorder.state === "recording") recorder.stop();
    closeSheetAndAdvance(sheet);
  });
  recordButton.addEventListener("click", async () => {
    if (recorder && recorder.state === "recording") return recorder.stop();
    if (!preferredVoiceNoteMimeType()) return (status.textContent = "This browser can't record audio.");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const chunks = [];
      recorder = new MediaRecorder(stream, { mimeType: preferredVoiceNoteMimeType() });
      recorder.addEventListener("dataavailable", (event) => event.data.size && chunks.push(event.data));
      recorder.addEventListener("stop", () => {
        clearInterval(timer);
        stream.getTracks().forEach((track) => track.stop());
        status.textContent = "Saving your note…";
        uploadVoiceNote(clip, new Blob(chunks, { type: recorder.mimeType }))
          .then(() => showToast("Sent for further review with your note."))
          .catch(() => showToast("Marked for review, but the note didn't upload."))
          .finally(() => closeSheetAndAdvance(sheet));
      });
      recorder.start();
      startedAt = Date.now();
      recordButton.textContent = "■ Stop & send";
      timer = setInterval(() => (status.textContent = `Recording… ${Math.round((Date.now() - startedAt) / 1000)}s`), 250);
    } catch (error) {
      status.textContent = "Microphone permission was denied. You can skip the note.";
    }
  });
}

// ---------- rendering ----------

function element(tagName, className, text) {
  const created = document.createElement(tagName);
  if (className) created.className = className;
  if (text !== undefined) created.textContent = text;
  return created;
}

function uploadLink() {
  const link = element("a", "", "Upload footage");
  link.href = "/upload";
  return link;
}

function showToast(message) {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.style.display = "block";
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => (toast.style.display = "none"), 2500);
}

function renderHeader() {
  const { batch, total_cost_dollars: totalCost } = state.payload;
  const pendingCount = clipsWithStatus("pending").length;
  const detail = batch.status === "ready" ? `${pendingCount} to review` : batch.status_detail || batch.status;
  document.getElementById("batch-status").textContent = `Batch #${batch.id} · ${detail}`;
  document.getElementById("batch-cost").textContent = `AI cost $${totalCost.toFixed(4)}`;
}

function renderEmptyState(title, message, extraElements = []) {
  const emptyState = element("div", "empty-state");
  emptyState.append(element("h2", "", title), element("p", "muted", message), ...extraElements);
  document.getElementById("card-container").replaceChildren(emptyState);
}

function renderFinishedState() {
  const { batch } = state.payload;
  if (!FINISHED_BATCH_STATUSES.includes(batch.status)) {
    return renderEmptyState("Processing…", batch.status_detail || "Your phone buzzes when clips are ready.");
  }
  if (batch.status === "failed") return renderEmptyState("This batch failed", batch.status_detail, [uploadLink()]);
  const counts = ["approved", "rejected", "needs_review"].map((status) => clipsWithStatus(status).length);
  const extras = [];
  if (counts[2]) {
    const reviewAgainButton = element("button", "primary-button", `Review ${counts[2]} flagged for another look`);
    reviewAgainButton.addEventListener("click", () => startPass("needs_review"));
    extras.push(reviewAgainButton);
  }
  extras.push(uploadLink());
  renderEmptyState("All reviewed", `${counts[0]} approved · ${counts[1]} rejected · ${counts[2]} need another look`, extras);
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
  if (clip.review_status !== "pending") {
    chips.append(element("span", `chip ${clip.review_status}`, clip.review_status.replace("_", " ")));
  }
  return chips;
}

function qaLineFor(clip) {
  const fixes = clip.qa_fixes.length ? ` Fixes: ${clip.qa_fixes.join("; ")}` : "";
  return element("p", `clip-qa ${clip.qa_status}`, `QA: ${clip.qa_summary}${fixes}`);
}

function voiceNotePlayerFor(clip) {
  if (!clip.voice_note_url) return [];
  const player = element("audio", "voice-note-player");
  Object.assign(player, { src: clip.voice_note_url, controls: true, preload: "none" });
  return [element("p", "clip-reason", "Your note:"), player];
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
  const buttons = [
    ["reject-button", "✕", rejectCurrentClip],
    ["review-button", "↑ Review", sendCurrentClipForFurtherReview],
    ["", "AI log", () => (decisionLog.hidden = !decisionLog.hidden)],
    ["approve-button", clip.review_status === "approved" ? "Save video" : "✓ Save", approveCurrentClip],
  ];
  for (const [className, label, onClick] of buttons) {
    const button = element("button", className, label);
    button.addEventListener("click", onClick);
    actions.append(button);
  }
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
    ...voiceNotePlayerFor(clip),
    actionButtonsFor(clip, decisionLog),
    decisionLog,
  );
  return overlay;
}

function renderCurrentCard() {
  const clip = currentClip();
  if (!clip) return renderFinishedState();
  prefetchVideoFile(clip);
  prefetchVideoFile(state.queue[state.queueIndex + 1]);
  const card = element("section", "card");
  card.append(
    videoFor(clip),
    element("div", "swipe-hint approve", "SAVE"),
    element("div", "swipe-hint reject", "NOPE"),
    element("div", "swipe-hint review", "REVIEW"),
    overlayFor(clip),
  );
  attachSwipeGestures(card);
  document.getElementById("card-container").replaceChildren(card);
}

// ---------- gestures ----------

function swipeDirection(deltaX, deltaY) {
  if (-deltaY > SWIPE_THRESHOLD_PIXELS && -deltaY > Math.abs(deltaX)) return "up";
  if (deltaX > SWIPE_THRESHOLD_PIXELS) return "right";
  if (deltaX < -SWIPE_THRESHOLD_PIXELS) return "left";
  return null;
}

function attachSwipeGestures(card) {
  let start = null;
  const hint = (name) => card.querySelector(`.swipe-hint.${name}`);
  const ignoresSwipes = (event) => event.target.closest(".decision-log, audio, button");

  card.addEventListener("touchstart", (event) => {
    start = ignoresSwipes(event) ? null : { x: event.touches[0].clientX, y: event.touches[0].clientY };
    card.style.transition = "none";
  });
  card.addEventListener("touchmove", (event) => {
    if (!start) return;
    event.preventDefault(); // the card follows the finger instead of the page scrolling
    const deltaX = event.touches[0].clientX - start.x;
    const deltaY = event.touches[0].clientY - start.y;
    card.style.transform = `translate(${deltaX}px, ${Math.min(deltaY, 0)}px) rotate(${deltaX / 40}deg)`;
    hint("approve").style.opacity = Math.max(0, deltaX / SWIPE_THRESHOLD_PIXELS);
    hint("reject").style.opacity = Math.max(0, -deltaX / SWIPE_THRESHOLD_PIXELS);
    hint("review").style.opacity = Math.max(0, -deltaY / SWIPE_THRESHOLD_PIXELS);
  }, { passive: false });
  card.addEventListener("touchend", (event) => {
    if (!start) return;
    const direction = swipeDirection(event.changedTouches[0].clientX - start.x, event.changedTouches[0].clientY - start.y);
    start = null;
    card.style.transition = "";
    card.style.transform = "";
    card.querySelectorAll(".swipe-hint").forEach((swipeHint) => (swipeHint.style.opacity = 0));
    if (direction === "right") approveCurrentClip();
    if (direction === "left") rejectCurrentClip();
    if (direction === "up") sendCurrentClipForFurtherReview();
  });
}

document.addEventListener("keydown", (event) => {
  if (document.querySelector(".voice-note-sheet")) return;
  if (event.key === "ArrowRight") approveCurrentClip();
  if (event.key === "ArrowLeft") rejectCurrentClip();
  if (event.key === "ArrowUp") sendCurrentClipForFurtherReview();
});

loadBatch();
