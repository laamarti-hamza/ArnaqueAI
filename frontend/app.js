const chatList = document.getElementById("chat-list");
const stageName = document.getElementById("stage-name");
const objective = document.getElementById("objective");
const audienceConstraint = document.getElementById("audience-constraint");
const directorReason = document.getElementById("director-reason");
const llmProvider = document.getElementById("llm-provider");
const llmModel = document.getElementById("llm-model");
const pendingList = document.getElementById("pending-list");
const choicesList = document.getElementById("choices-list");
const winnerLabel = document.getElementById("winner-label");

const scammerForm = document.getElementById("scammer-form");
const scammerInput = document.getElementById("scammer-input");
const proposalForm = document.getElementById("proposal-form");
const proposalInput = document.getElementById("proposal-input");
const resetBtn = document.getElementById("reset-btn");
const selectChoicesBtn = document.getElementById("select-choices-btn");
const simulateVoteBtn = document.getElementById("simulate-vote-btn");

let currentState = null;
let pendingScammerMessage = "";
let pendingVictimMessage = "";
let pendingVictimCharQueue = "";
let victimTypingIntervalId = null;
let victimTypingDrainResolvers = [];
let victimVoiceEnabled = false;
let activeVictimAudio = null;
let activeVictimAudioUrl = "";
let lastSpokenVictimKey = "";

async function withButtonLoading(button, action) {
  if (!button) {
    return action();
  }
  if (button.dataset.loading === "true") {
    return;
  }

  button.dataset.loading = "true";
  button.disabled = true;
  button.classList.add("is-loading");
  button.setAttribute("aria-busy", "true");

  try {
    return await action();
  } finally {
    button.dataset.loading = "false";
    button.disabled = false;
    button.classList.remove("is-loading");
    button.removeAttribute("aria-busy");
  }
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    const contentType = response.headers.get("content-type") || "";
    if (contentType.includes("application/json")) {
      const payload = await response.json().catch(() => null);
      const detail = payload && typeof payload.detail === "string" ? payload.detail : "";
      throw new Error(detail || `Erreur HTTP ${response.status}`);
    }
    const body = await response.text();
    throw new Error(body || `Erreur HTTP ${response.status}`);
  }
  return response.json();
}

async function parseHttpError(response) {
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    const payload = await response.json().catch(() => null);
    const detail = payload && typeof payload.detail === "string" ? payload.detail : "";
    return detail || `Erreur HTTP ${response.status}`;
  }
  const body = await response.text().catch(() => "");
  return body || `Erreur HTTP ${response.status}`;
}

function victimMessageKey(msg) {
  if (!msg) return "";
  return `${msg.timestamp || ""}|${msg.content || ""}`;
}

function getLatestVictimMessage(state) {
  const messages = state?.messages || [];
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const msg = messages[i];
    if (msg?.role === "victim" && typeof msg.content === "string" && msg.content.trim()) {
      return msg;
    }
  }
  return null;
}

function stopVictimAudioPlayback() {
  if (activeVictimAudio) {
    activeVictimAudio.pause();
    activeVictimAudio.onended = null;
    activeVictimAudio.onerror = null;
    activeVictimAudio.src = "";
    activeVictimAudio = null;
  }
  if (activeVictimAudioUrl) {
    URL.revokeObjectURL(activeVictimAudioUrl);
    activeVictimAudioUrl = "";
  }
}

async function speakLatestVictimMessage(state) {
  if (!victimVoiceEnabled) {
    return false;
  }
  const latestVictim = getLatestVictimMessage(state);
  if (!latestVictim) {
    return false;
  }

  const key = victimMessageKey(latestVictim);
  if (!key || key === lastSpokenVictimKey) {
    return false;
  }

  let response;
  try {
    response = await fetch("/api/voice/victim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: latestVictim.content }),
    });
  } catch (err) {
    console.warn("Voix victime indisponible:", err);
    return false;
  }

  if (!response.ok) {
    const detail = await parseHttpError(response).catch(() => `Erreur HTTP ${response.status}`);
    console.warn("Synthese vocale victime impossible:", detail);
    return false;
  }

  const blob = await response.blob().catch(() => null);
  if (!blob || blob.size === 0) {
    return false;
  }

  stopVictimAudioPlayback();
  activeVictimAudioUrl = URL.createObjectURL(blob);
  activeVictimAudio = new Audio(activeVictimAudioUrl);
  activeVictimAudio.preload = "auto";
  activeVictimAudio.onended = () => stopVictimAudioPlayback();
  activeVictimAudio.onerror = () => stopVictimAudioPlayback();

  try {
    await activeVictimAudio.play();
    lastSpokenVictimKey = key;
    return true;
  } catch (err) {
    console.warn("Lecture automatique de la voix bloquee:", err);
    stopVictimAudioPlayback();
    return false;
  }
}

function resetVictimTyping() {
  pendingVictimCharQueue = "";
  if (victimTypingIntervalId !== null) {
    window.clearInterval(victimTypingIntervalId);
    victimTypingIntervalId = null;
  }
  const resolvers = victimTypingDrainResolvers;
  victimTypingDrainResolvers = [];
  for (const resolve of resolvers) {
    resolve();
  }
}

function waitForVictimTypingDrain() {
  if (!pendingVictimCharQueue && victimTypingIntervalId === null) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    victimTypingDrainResolvers.push(resolve);
  });
}

function ensureVictimTypingLoop() {
  if (victimTypingIntervalId !== null) {
    return;
  }

  victimTypingIntervalId = window.setInterval(() => {
    if (!pendingVictimCharQueue) {
      window.clearInterval(victimTypingIntervalId);
      victimTypingIntervalId = null;
      const resolvers = victimTypingDrainResolvers;
      victimTypingDrainResolvers = [];
      for (const resolve of resolvers) {
        resolve();
      }
      return;
    }

    pendingVictimMessage += pendingVictimCharQueue[0];
    pendingVictimCharQueue = pendingVictimCharQueue.slice(1);
    renderMessages(currentState?.messages || []);
  }, 14);
}

function consumeVictimStreamChunk(chunk) {
  void chunk;
}

function parseSseBlock(block) {
  const lines = block.split("\n");
  let event = "message";
  const dataLines = [];

  for (const line of lines) {
    if (!line) continue;
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
      continue;
    }
    if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }

  if (dataLines.length === 0) {
    return null;
  }

  const rawData = dataLines.join("\n");
  try {
    return { event, data: JSON.parse(rawData) };
  } catch {
    return { event, data: { raw: rawData } };
  }
}

async function streamSimulationStep(message) {
  const response = await fetch("/api/simulation/step/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify({ scammer_input: message }),
  });

  if (!response.ok) {
    throw new Error(await parseHttpError(response));
  }

  if (!response.body) {
    throw new Error("Le streaming n'est pas disponible sur ce navigateur.");
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let doneEventReceived = false;
  let streamError = "";

  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }

    buffer += decoder.decode(value, { stream: true }).replace(/\r/g, "");
    let separatorIndex = buffer.indexOf("\n\n");
    while (separatorIndex !== -1) {
      const rawBlock = buffer.slice(0, separatorIndex).trim();
      buffer = buffer.slice(separatorIndex + 2);
      separatorIndex = buffer.indexOf("\n\n");

      if (!rawBlock) continue;
      const packet = parseSseBlock(rawBlock);
      if (!packet) continue;

      if (packet.event === "chunk") {
        consumeVictimStreamChunk(packet.data?.text || "");
        continue;
      }

      if (packet.event === "done") {
        const finalState = packet.data?.state || currentState;
        await finalizeVictimTurn(finalState);
        doneEventReceived = true;
        continue;
      }

      if (packet.event === "error") {
        streamError = packet.data?.detail || "Erreur pendant le streaming.";
      }
    }
  }

  buffer += decoder.decode().replace(/\r/g, "");
  if (buffer.trim()) {
    const packet = parseSseBlock(buffer.trim());
    if (packet?.event === "chunk") {
      consumeVictimStreamChunk(packet.data?.text || "");
    } else if (packet?.event === "done") {
      const finalState = packet.data?.state || currentState;
      await finalizeVictimTurn(finalState);
      doneEventReceived = true;
    } else if (packet?.event === "error") {
      streamError = packet.data?.detail || "Erreur pendant le streaming.";
    }
  }

  if (streamError) {
    throw new Error(streamError);
  }
  if (!doneEventReceived) {
    throw new Error("Flux interrompu avant la fin de la reponse.");
  }
}

function buildStateWithoutFinalVictim(state) {
  if (!state || !Array.isArray(state.messages) || state.messages.length === 0) {
    return state;
  }
  const last = state.messages[state.messages.length - 1];
  if (!last || last.role !== "victim") {
    return state;
  }
  return {
    ...state,
    messages: state.messages.slice(0, -1),
  };
}

async function finalizeVictimTurn(finalState) {
  const latestVictim = getLatestVictimMessage(finalState);
  const finalVictimText = (latestVictim?.content || "").trim();

  currentState = buildStateWithoutFinalVictim(finalState);
  pendingScammerMessage = "";
  pendingVictimMessage = "";
  resetVictimTyping();
  render();

  if (finalVictimText) {
    const startAudioPromise = speakLatestVictimMessage(finalState);
    await startAudioPromise.catch(() => false);
    pendingVictimCharQueue = finalVictimText;
    ensureVictimTypingLoop();
    renderMessages(currentState?.messages || []);
    await waitForVictimTypingDrain();
  }

  currentState = finalState;
  pendingVictimMessage = "";
  resetVictimTyping();
  render();
}

function formatTime(isoTimestamp) {
  if (!isoTimestamp) return "";
  const d = new Date(isoTimestamp);
  return d.toLocaleTimeString("fr-FR", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function renderMessages(messages) {
  chatList.replaceChildren();
  const items = [...(messages || [])];
  if (pendingScammerMessage) {
    items.push({
      role: "scammer",
      content: pendingScammerMessage,
      timestamp: new Date().toISOString(),
      sound_effects: [],
      pending: true,
      pending_label: "Envoi...",
    });
  }
  if (pendingVictimMessage) {
    items.push({
      role: "victim",
      content: pendingVictimMessage,
      timestamp: new Date().toISOString(),
      sound_effects: [],
      pending: true,
      pending_label: "Reponse en cours...",
    });
  }

  for (const msg of items) {
    const li = document.createElement("li");
    li.className = `message ${msg.role}`;
    if (msg.pending) {
      li.classList.add("pending");
    }

    const bubble = document.createElement("div");
    bubble.className = "message-bubble";

    const body = document.createElement("div");
    body.className = "message-text";
    body.textContent = msg.content;
    bubble.appendChild(body);

    if (Array.isArray(msg.sound_effects) && msg.sound_effects.length > 0 && !msg.pending) {
      const badgeRow = document.createElement("div");
      badgeRow.className = "sound-badges";
      for (const effect of msg.sound_effects) {
        const badge = document.createElement("span");
        badge.className = "sound-badge";
        badge.textContent = effect;
        badgeRow.appendChild(badge);
      }
      bubble.appendChild(badgeRow);
    }

    const meta = document.createElement("div");
    meta.className = "message-meta";

    const role = document.createElement("span");
    role.className = `role ${msg.role}`;
    role.textContent = msg.role === "victim" ? "Jean Dubois" : "Arnaqueur";

    const timestamp = document.createElement("span");
    timestamp.className = "timestamp";
    timestamp.textContent = msg.pending ? msg.pending_label || "Envoi..." : formatTime(msg.timestamp);

    meta.append(role, timestamp);

    li.append(bubble, meta);
    chatList.appendChild(li);
  }
  chatList.scrollTop = chatList.scrollHeight;
}

function renderPending(proposals) {
  pendingList.replaceChildren();
  for (const proposal of proposals || []) {
    const li = document.createElement("li");
    li.textContent = proposal;
    pendingList.appendChild(li);
  }
}

async function vote(index, button) {
  try {
    await withButtonLoading(button, async () => {
      currentState = await api("/api/audience/vote", {
        method: "POST",
        body: JSON.stringify({ winner_index: index }),
      });
      render();
    });
  } catch (err) {
    window.alert(`Vote impossible: ${err.message}`);
  }
}

function renderChoices(choices) {
  choicesList.replaceChildren();

  (choices || []).forEach((choice, index) => {
    const li = document.createElement("li");
    li.className = "choice-row";

    const text = document.createElement("span");
    text.textContent = choice;

    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Voter";
    button.addEventListener("click", () => vote(index, button));

    li.append(text, button);
    choicesList.appendChild(li);
  });
}

function render() {
  if (!currentState) return;
  llmProvider.textContent = currentState.llm_provider || (currentState.llm_enabled ? "configured" : "none");
  llmModel.textContent = currentState.llm_model || "-";
  stageName.textContent = currentState.stage_name || "-";
  objective.textContent = currentState.current_objective || "-";
  audienceConstraint.textContent = currentState.audience_constraint || "Aucune";
  directorReason.textContent = currentState.director_reason || "-";
  winnerLabel.textContent = currentState.last_winner
    ? `Dernier evenement gagnant: ${currentState.last_winner}`
    : "Aucun vote enregistre.";

  renderMessages(currentState.messages);
  renderPending(currentState.pending_proposals);
  renderChoices(currentState.selected_choices);
}

async function refreshState() {
  try {
    const health = await api("/api/health");
    victimVoiceEnabled = Boolean(health?.victim_voice_enabled);
  } catch {
    victimVoiceEnabled = false;
  }

  currentState = await api("/api/simulation/state");
  const latestVictim = getLatestVictimMessage(currentState);
  lastSpokenVictimKey = victimMessageKey(latestVictim);
  render();
}

scammerForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = scammerInput.value.trim();
  if (!message) return;
  const submitBtn = event.submitter || scammerForm.querySelector('button[type="submit"]');

  try {
    pendingScammerMessage = message;
    scammerInput.value = "";
    pendingVictimMessage = "";
    stopVictimAudioPlayback();
    resetVictimTyping();
    renderMessages(currentState?.messages || []);
    await withButtonLoading(submitBtn, async () => {
      await streamSimulationStep(message);
    });
  } catch (err) {
    pendingScammerMessage = "";
    pendingVictimMessage = "";
    resetVictimTyping();
    render();
    window.alert(`Envoi impossible: ${err.message}`);
  }
});

proposalForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const proposal = proposalInput.value.trim();
  if (!proposal) return;
  const submitBtn = event.submitter || proposalForm.querySelector('button[type="submit"]');

  try {
    await withButtonLoading(submitBtn, async () => {
      currentState = await api("/api/audience/submit", {
        method: "POST",
        body: JSON.stringify({ proposal }),
      });
      proposalInput.value = "";
      render();
    });
  } catch (err) {
    window.alert(`Proposition impossible: ${err.message}`);
  }
});

selectChoicesBtn.addEventListener("click", async () => {
  try {
    await withButtonLoading(selectChoicesBtn, async () => {
      currentState = await api("/api/audience/select", {
        method: "POST",
        body: JSON.stringify({}),
      });
      render();
    });
  } catch (err) {
    window.alert(`Selection impossible: ${err.message}`);
  }
});

simulateVoteBtn.addEventListener("click", async () => {
  try {
    await withButtonLoading(simulateVoteBtn, async () => {
      currentState = await api("/api/audience/vote/simulate", {
        method: "POST",
        body: JSON.stringify({}),
      });
      render();
    });
  } catch (err) {
    window.alert(`Vote simule impossible: ${err.message}`);
  }
});

resetBtn.addEventListener("click", async () => {
  try {
    await withButtonLoading(resetBtn, async () => {
      currentState = await api("/api/simulation/reset", {
        method: "POST",
        body: JSON.stringify({}),
      });
      pendingScammerMessage = "";
      pendingVictimMessage = "";
      lastSpokenVictimKey = "";
      stopVictimAudioPlayback();
      resetVictimTyping();
      render();
    });
  } catch (err) {
    window.alert(`Reset impossible: ${err.message}`);
  }
});

refreshState().catch((err) => {
  window.alert(`Erreur de chargement initial: ${err.message}`);
});
