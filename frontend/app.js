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
    timestamp.textContent = msg.pending ? "Envoi..." : formatTime(msg.timestamp);

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
    renderMessages(currentState?.messages || []);
    await withButtonLoading(submitBtn, async () => {
      currentState = await api("/api/simulation/step", {
        method: "POST",
        body: JSON.stringify({ scammer_input: message }),
      });
      pendingScammerMessage = "";
      scammerInput.value = "";
      render();
    });
  } catch (err) {
    pendingScammerMessage = "";
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
      render();
    });
  } catch (err) {
    window.alert(`Reset impossible: ${err.message}`);
  }
});

refreshState().catch((err) => {
  window.alert(`Erreur de chargement initial: ${err.message}`);
});
