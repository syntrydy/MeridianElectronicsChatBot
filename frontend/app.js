import { Client } from "https://cdn.jsdelivr.net/npm/@gradio/client/dist/index.min.js";

const BACKEND_URL =
  new URLSearchParams(location.search).get("backend") ||
  window.MERIDIAN_BACKEND ||
  "http://127.0.0.1:7860";

const $messages = document.getElementById("messages");
const $form = document.getElementById("form");
const $input = document.getElementById("input");
const $send = document.getElementById("send");
const $status = document.getElementById("status");
const $suggestions = document.getElementById("suggestions");

const history = [];
let client = null;

function setStatus(text, kind = "") {
  $status.textContent = text;
  $status.className = `status ${kind}`.trim();
}

function addMessage(role, text) {
  const wrap = document.createElement("div");
  wrap.className = `msg ${role}`;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  wrap.appendChild(bubble);
  $messages.appendChild(wrap);
  $messages.scrollTop = $messages.scrollHeight;
  return bubble;
}

async function connect() {
  setStatus("connecting…");
  try {
    client = await Client.connect(BACKEND_URL);
    setStatus("ready", "ready");
  } catch (err) {
    console.error(err);
    setStatus("offline", "error");
    addMessage(
      "bot",
      `Cannot reach backend at ${BACKEND_URL}. Append ?backend=https://your-space.hf.space to the URL or set window.MERIDIAN_BACKEND.`,
    );
  }
}

async function send(message) {
  if (!client) {
    await connect();
    if (!client) return;
  }

  addMessage("user", message);
  const pending = addMessage("bot", "");
  pending.classList.add("typing");
  $send.disabled = true;

  try {
    const result = await client.predict("/chat", {
      message,
      history,
    });
    const reply = extractReply(result?.data);
    pending.classList.remove("typing");
    pending.textContent = reply;
    history.push({ role: "user", content: message });
    history.push({ role: "assistant", content: reply });
  } catch (err) {
    console.error(err);
    pending.classList.remove("typing");
    pending.textContent = `Error: ${err?.message ?? "request failed"}`;
  } finally {
    $send.disabled = false;
    $input.focus();
  }
}

function extractReply(data) {
  if (!data) return "(empty response)";
  const first = Array.isArray(data) ? data[0] : data;
  if (typeof first === "string") return first;
  if (first?.content) return first.content;
  return JSON.stringify(first);
}

$form.addEventListener("submit", (e) => {
  e.preventDefault();
  const text = $input.value.trim();
  if (!text) return;
  $input.value = "";
  send(text);
});

$suggestions.addEventListener("click", (e) => {
  const btn = e.target.closest(".chip");
  if (!btn) return;
  $input.value = btn.textContent;
  $form.requestSubmit();
});

connect();
