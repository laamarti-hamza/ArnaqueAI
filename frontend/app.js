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
  if (typeof chunk !== "string" || !chunk) {
    return;
  }
  pendingVictimCharQueue += chunk.replace(/\r?\n/g, " ");
  ensureVictimTypingLoop();
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
        await waitForVictimTypingDrain();
        currentState = packet.data?.state || currentState;
        pendingScammerMessage = "";
        pendingVictimMessage = "";
        resetVictimTyping();
        render();
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
      await waitForVictimTypingDrain();
      currentState = packet.data?.state || currentState;
      pendingScammerMessage = "";
      pendingVictimMessage = "";
      resetVictimTyping();
      render();
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
  currentState = await api("/api/simulation/state");
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
