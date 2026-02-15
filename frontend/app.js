const chatList = document.getElementById("chat-list");
const audienceConstraint = document.getElementById("audience-constraint");
const llmProvider = document.getElementById("llm-provider");
const pendingList = document.getElementById("pending-list");
const choicesList = document.getElementById("choices-list");
const winnerLabel = document.getElementById("winner-label");
const toggleStateBtn = document.getElementById("toggle-state-btn");
const simulationStatePanel = document.getElementById("simulation-state");
const proposalModal = document.getElementById("proposal-modal");
const voteModal = document.getElementById("vote-modal");

const scammerForm = document.getElementById("scammer-form");
const scammerInput = document.getElementById("scammer-input");
const proposalForm = document.getElementById("proposal-form");
const proposalInput = document.getElementById("proposal-input");
const resetBtn = document.getElementById("reset-btn");
const selectChoicesBtn = document.getElementById("select-choices-btn");
const simulateVoteBtn = document.getElementById("simulate-vote-btn");
const SOUND_EFFECT_TAG_RE = /\[SOUND_EFFECT:\s*([A-Z_]+)\s*\]/gi;
const SOUND_EFFECT_AUDIO_MAP = {
  DOG_BARKING: "/sounds/dog-barking.mp3",
  DOORBELL: "/sounds/doorbell.mp3",
  COUGHING_FIT: "/sounds/coughing.mp3",
  TV_BACKGROUND_BFMTV: "/sounds/tvbackground.mp3",
};
const SOUND_EFFECT_LABEL_MAP = {
  DOG_BARKING: "Son : Chien aboie",
  DOORBELL: "Son : Sonnette",
  COUGHING_FIT: "Son : Quinte de toux",
  TV_BACKGROUND_BFMTV: "Son : TV en fond",
};

let currentState = null;
let pendingScammerMessage = "";
let pendingVictimMessage = "";
let pendingVictimCharQueue = "";
let victimTypingIntervalId = null;
let victimTypingDrainResolvers = [];
let victimVoiceEnabled = false;
let activeVictimAudio = null;
let activeVictimAudioUrl = "";
let activeEffectAudios = [];
let activeEffectCueTimeoutIds = [];
let lastSpokenVictimKey = "";
let simulationStateVisible = false;
let nextAudienceTrigger = 3;
let audienceFlowInProgress = false;

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

function normalizeSoundEffect(effect) {
  return String(effect || "").trim().toUpperCase();
}

function getSoundEffectLabel(effect) {
  const normalized = normalizeSoundEffect(effect);
  return SOUND_EFFECT_LABEL_MAP[normalized] || `Son : ${normalized}`;
}

function extractSoundEffectsFromText(text) {
  if (!text) return [];
  const effects = [];
  SOUND_EFFECT_TAG_RE.lastIndex = 0;
  let match = SOUND_EFFECT_TAG_RE.exec(text);
  while (match) {
    effects.push(normalizeSoundEffect(match[1]));
    match = SOUND_EFFECT_TAG_RE.exec(text);
  }
  SOUND_EFFECT_TAG_RE.lastIndex = 0;
  return effects;
}

function getMessageSoundEffects(message) {
  const fromArray = Array.isArray(message?.sound_effects) ? message.sound_effects : [];
  const fromText = extractSoundEffectsFromText(message?.content || "");
  const merged = [...fromArray, ...fromText].map(normalizeSoundEffect).filter(Boolean);
  return [...new Set(merged)];
}

function stripSoundTagsForSpeech(text) {
  if (!text) return "";
  const withoutTags = String(text).replace(SOUND_EFFECT_TAG_RE, " ");
  SOUND_EFFECT_TAG_RE.lastIndex = 0;
  return withoutTags.replace(/\s+/g, " ").trim();
}

function clearSoundEffectCueTimers() {
  for (const timeoutId of activeEffectCueTimeoutIds) {
    window.clearTimeout(timeoutId);
  }
  activeEffectCueTimeoutIds = [];
}

function stopSoundEffectsPlayback() {
  clearSoundEffectCueTimers();
  for (const audio of activeEffectAudios) {
    try {
      audio.pause();
      audio.src = "";
    } catch {
      // Ignore cleanup errors.
    }
  }
  activeEffectAudios = [];
}

function buildSoundCuePlan(message) {
  const content = String(message?.content || "");
  const totalSpokenChars = Math.max(stripSoundTagsForSpeech(content).length, 1);
  const cues = [];
  let cursor = 0;
  let spokenCharsBefore = 0;

  SOUND_EFFECT_TAG_RE.lastIndex = 0;
  let match = SOUND_EFFECT_TAG_RE.exec(content);
  while (match) {
    const [fullMatch, effectRaw] = match;
    const start = match.index;
    const plainSegment = stripSoundTagsForSpeech(content.slice(cursor, start));
    spokenCharsBefore += plainSegment.length;
    const effect = normalizeSoundEffect(effectRaw);
    if (effect && SOUND_EFFECT_AUDIO_MAP[effect]) {
      cues.push({
        effect,
        spokenCharsBefore,
        totalSpokenChars,
      });
    }
    cursor = start + fullMatch.length;
    match = SOUND_EFFECT_TAG_RE.exec(content);
  }
  SOUND_EFFECT_TAG_RE.lastIndex = 0;

  if (cues.length > 0) {
    return cues;
  }

  const fallbackEffects = getMessageSoundEffects(message);
  return fallbackEffects
    .filter((effect) => SOUND_EFFECT_AUDIO_MAP[effect])
    .map((effect) => ({ effect, spokenCharsBefore: 0, totalSpokenChars: 1 }));
}

function waitForAudioMetadata(audio, timeoutMs = 1200) {
  if (!audio) {
    return Promise.resolve();
  }
  if (Number.isFinite(audio.duration) && audio.duration > 0) {
    return Promise.resolve();
  }

  return new Promise((resolve) => {
    let settled = false;
    const done = () => {
      if (settled) return;
      settled = true;
      audio.removeEventListener("loadedmetadata", done);
      audio.removeEventListener("durationchange", done);
      resolve();
    };
    audio.addEventListener("loadedmetadata", done, { once: true });
    audio.addEventListener("durationchange", done, { once: true });
    window.setTimeout(done, timeoutMs);
  });
}

async function scheduleSoundEffectsForMessage(voiceAudio, message) {
  const cuePlan = buildSoundCuePlan(message);
  stopSoundEffectsPlayback();
  if (cuePlan.length === 0) {
    return false;
  }

  await waitForAudioMetadata(voiceAudio);
  const durationSec =
    Number.isFinite(voiceAudio?.duration) && voiceAudio.duration > 0 ? voiceAudio.duration : null;

  for (const cue of cuePlan) {
    const src = SOUND_EFFECT_AUDIO_MAP[cue.effect];
    if (!src) continue;

    let delayMs;
    if (durationSec !== null) {
      delayMs = (cue.spokenCharsBefore / cue.totalSpokenChars) * durationSec * 1000;
    } else {
      // Fallback when duration is unavailable: ~18 chars/sec.
      delayMs = cue.spokenCharsBefore * 55;
    }
    const safeDelayMs = Math.max(0, Math.min(delayMs, 30000));

    const timeoutId = window.setTimeout(() => {
      const fxAudio = new Audio(src);
      fxAudio.preload = "auto";
      fxAudio.volume = cue.effect === "TV_BACKGROUND_BFMTV" ? 0.45 : 0.85;
      activeEffectAudios.push(fxAudio);
      fxAudio.play().catch((err) => {
        console.warn("Lecture d'effet sonore impossible:", err);
      });
    }, safeDelayMs);
    activeEffectCueTimeoutIds.push(timeoutId);
  }

  return true;
}

function renderMessageTextWithInlineSoundTags(container, text) {
  container.replaceChildren();
  const content = String(text || "");
  if (!content) return;

  SOUND_EFFECT_TAG_RE.lastIndex = 0;
  let cursor = 0;
  let match = SOUND_EFFECT_TAG_RE.exec(content);
  while (match) {
    const [fullMatch, effectRaw] = match;
    const start = match.index;
    if (start > cursor) {
      container.appendChild(document.createTextNode(content.slice(cursor, start)));
    }

    const chip = document.createElement("span");
    chip.className = "inline-sound-tag";
    chip.textContent = getSoundEffectLabel(effectRaw);
    container.appendChild(chip);

    cursor = start + fullMatch.length;
    match = SOUND_EFFECT_TAG_RE.exec(content);
  }

  if (cursor < content.length) {
    container.appendChild(document.createTextNode(content.slice(cursor)));
  }
  SOUND_EFFECT_TAG_RE.lastIndex = 0;
}

function setSimulationStateVisible(visible) {
  simulationStateVisible = Boolean(visible);
  simulationStatePanel.hidden = !simulationStateVisible;
  toggleStateBtn.setAttribute("aria-expanded", simulationStateVisible ? "true" : "false");
  toggleStateBtn.textContent = simulationStateVisible
    ? "Masquer l'état de la simulation"
    : "Afficher l'état de la simulation";
}

function setModalOpen(modal, open) {
  if (!modal) return;
  const isOpen = Boolean(open);
  const canUseDialogApi = typeof modal.showModal === "function" && typeof modal.close === "function";

  if (isOpen) {
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    if (canUseDialogApi && !modal.open) {
      modal.showModal();
    }
    return;
  }

  if (canUseDialogApi && modal.open) {
    modal.close();
  }
  modal.hidden = true;
  modal.setAttribute("aria-hidden", "true");
}

function openProposalModal() {
  setModalOpen(voteModal, false);
  setModalOpen(proposalModal, true);
}

function openVoteModal() {
  setModalOpen(proposalModal, false);
  setModalOpen(voteModal, true);
}

function closeAudienceFlowModals() {
  setModalOpen(proposalModal, false);
  setModalOpen(voteModal, false);
}

function syncAudienceTrigger(messageCount) {
  const baseCount = Number.isFinite(messageCount) ? messageCount : 0;
  nextAudienceTrigger = (Math.floor(baseCount / 3) + 1) * 3;
}

function countScammerMessages(state) {
  const messages = state?.messages || [];
  let count = 0;
  for (const msg of messages) {
    if (msg?.role === "scammer") {
      count += 1;
    }
  }
  return count;
}

function maybeTriggerAudienceFlow() {
  if (audienceFlowInProgress) return;
  const messageCount = countScammerMessages(currentState);
  if (messageCount < nextAudienceTrigger) return;

  audienceFlowInProgress = true;
  while (nextAudienceTrigger <= messageCount) {
    nextAudienceTrigger += 3;
  }
  openProposalModal();
}

function completeAudienceFlow() {
  audienceFlowInProgress = false;
  closeAudienceFlowModals();
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
  const latestVictim = getLatestVictimMessage(state);
  if (!latestVictim) {
    return false;
  }

  const key = victimMessageKey(latestVictim);
  if (!key || key === lastSpokenVictimKey) {
    return false;
  }

  const playEffectsWithoutVoice = async () => {
    try {
      await scheduleSoundEffectsForMessage(null, latestVictim);
      return true;
    } catch (err) {
      console.warn("Planification des effets sonores impossible:", err);
      return false;
    }
  };

  if (!victimVoiceEnabled) {
    const playedEffects = await playEffectsWithoutVoice();
    if (playedEffects) {
      lastSpokenVictimKey = key;
    }
    return false;
  }

  const textForSpeech = stripSoundTagsForSpeech(latestVictim.content);
  const payloadText = textForSpeech || latestVictim.content;

  let response;
  try {
    response = await fetch("/api/voice/victim", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: payloadText }),
    });
  } catch (err) {
    console.warn("Voix victime indisponible:", err);
    const playedEffects = await playEffectsWithoutVoice();
    if (playedEffects) {
      lastSpokenVictimKey = key;
    }
    return false;
  }

  if (!response.ok) {
    const detail = await parseHttpError(response).catch(() => `Erreur HTTP ${response.status}`);
    console.warn("Synthese vocale victime impossible:", detail);
    const playedEffects = await playEffectsWithoutVoice();
    if (playedEffects) {
      lastSpokenVictimKey = key;
    }
    return false;
  }

  const blob = await response.blob().catch(() => null);
  if (!blob || blob.size === 0) {
    const playedEffects = await playEffectsWithoutVoice();
    if (playedEffects) {
      lastSpokenVictimKey = key;
    }
    return false;
  }

  stopVictimAudioPlayback();
  activeVictimAudioUrl = URL.createObjectURL(blob);
  activeVictimAudio = new Audio(activeVictimAudioUrl);
  activeVictimAudio.preload = "auto";
  activeVictimAudio.onended = () => {
    stopVictimAudioPlayback();
    stopSoundEffectsPlayback();
  };
  activeVictimAudio.onerror = () => {
    stopVictimAudioPlayback();
    stopSoundEffectsPlayback();
  };

  try {
    await activeVictimAudio.play();
    lastSpokenVictimKey = key;
    void scheduleSoundEffectsForMessage(activeVictimAudio, latestVictim).catch((err) => {
      console.warn("Planification des effets sonores impossible:", err);
    });
    return true;
  } catch (err) {
    console.warn("Lecture automatique de la voix bloquee:", err);
    stopVictimAudioPlayback();
    const playedEffects = await playEffectsWithoutVoice();
    if (!playedEffects) {
      stopSoundEffectsPlayback();
    } else {
      lastSpokenVictimKey = key;
    }
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
    throw new Error("Flux interrompu avant la fin de la réponse.");
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
    await speakLatestVictimMessage(finalState).catch((err) => {
      console.warn("Lecture voix victime indisponible:", err);
      return false;
    });
    pendingVictimCharQueue = finalVictimText;
    ensureVictimTypingLoop();
    renderMessages(currentState?.messages || []);
    await waitForVictimTypingDrain();
  }

  currentState = finalState;
  pendingVictimMessage = "";
  resetVictimTyping();
  render();
  maybeTriggerAudienceFlow();
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
      pending_label: "Réponse en cours...",
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
    renderMessageTextWithInlineSoundTags(body, msg.content);
    bubble.appendChild(body);

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
      completeAudienceFlow();
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
  llmProvider.textContent = currentState.llm_provider || (currentState.llm_enabled ? "configuré" : "aucun");
  audienceConstraint.textContent = currentState.audience_constraint || "Aucune";
  winnerLabel.textContent = currentState.last_winner
    ? `Dernier événement gagnant: ${currentState.last_winner}`
    : "Aucun vote enregistré.";

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
  stopSoundEffectsPlayback();
  const latestVictim = getLatestVictimMessage(currentState);
  lastSpokenVictimKey = victimMessageKey(latestVictim);
  audienceFlowInProgress = false;
  closeAudienceFlowModals();
  syncAudienceTrigger(countScammerMessages(currentState));
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
    stopSoundEffectsPlayback();
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
      openVoteModal();
    });
  } catch (err) {
    window.alert(`Sélection impossible: ${err.message}`);
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
      completeAudienceFlow();
    });
  } catch (err) {
    window.alert(`Vote simulé impossible: ${err.message}`);
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
      stopSoundEffectsPlayback();
      resetVictimTyping();
      completeAudienceFlow();
      syncAudienceTrigger(countScammerMessages(currentState));
      render();
    });
  } catch (err) {
    window.alert(`Réinitialisation impossible: ${err.message}`);
  }
});

toggleStateBtn.addEventListener("click", () => {
  setSimulationStateVisible(!simulationStateVisible);
});

for (const modal of [proposalModal, voteModal]) {
  if (!modal) continue;
  modal.addEventListener("cancel", (event) => {
    event.preventDefault();
  });
}

setSimulationStateVisible(false);
closeAudienceFlowModals();

refreshState().catch((err) => {
  window.alert(`Erreur de chargement initial: ${err.message}`);
});
