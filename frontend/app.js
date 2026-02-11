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

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
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
  for (const msg of messages || []) {
    const li = document.createElement("li");
    li.className = `message ${msg.role}`;

    const header = document.createElement("div");
    header.className = "message-header";

    const role = document.createElement("span");
    role.className = `role ${msg.role}`;
    role.textContent = msg.role === "victim" ? "Jean Dubois" : "Arnaqueur";

    const timestamp = document.createElement("span");
    timestamp.className = "timestamp";
    timestamp.textContent = formatTime(msg.timestamp);

    header.append(role, timestamp);

    const body = document.createElement("div");
    body.textContent = msg.content;

    li.append(header, body);

    if (Array.isArray(msg.sound_effects) && msg.sound_effects.length > 0) {
      const badgeRow = document.createElement("div");
      badgeRow.className = "sound-badges";
      for (const effect of msg.sound_effects) {
        const badge = document.createElement("span");
        badge.className = "sound-badge";
        badge.textContent = effect;
        badgeRow.appendChild(badge);
      }
      li.appendChild(badgeRow);
    }
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

function vote(index) {
  api("/api/audience/vote", {
    method: "POST",
    body: JSON.stringify({ winner_index: index }),
  })
    .then((state) => {
      currentState = state;
      render();
    })
    .catch((err) => window.alert(`Vote impossible: ${err.message}`));
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
    button.addEventListener("click", () => vote(index));

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

  try {
    currentState = await api("/api/simulation/step", {
      method: "POST",
      body: JSON.stringify({ scammer_input: message }),
    });
    scammerInput.value = "";
    render();
  } catch (err) {
    window.alert(`Envoi impossible: ${err.message}`);
  }
});

proposalForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const proposal = proposalInput.value.trim();
  if (!proposal) return;

  try {
    currentState = await api("/api/audience/submit", {
      method: "POST",
      body: JSON.stringify({ proposal }),
    });
    proposalInput.value = "";
    render();
  } catch (err) {
    window.alert(`Proposition impossible: ${err.message}`);
  }
});

selectChoicesBtn.addEventListener("click", async () => {
  try {
    currentState = await api("/api/audience/select", {
      method: "POST",
      body: JSON.stringify({}),
    });
    render();
  } catch (err) {
    window.alert(`Selection impossible: ${err.message}`);
  }
});

simulateVoteBtn.addEventListener("click", async () => {
  try {
    currentState = await api("/api/audience/vote/simulate", {
      method: "POST",
      body: JSON.stringify({}),
    });
    render();
  } catch (err) {
    window.alert(`Vote simule impossible: ${err.message}`);
  }
});

resetBtn.addEventListener("click", async () => {
  try {
    currentState = await api("/api/simulation/reset", {
      method: "POST",
      body: JSON.stringify({}),
    });
    render();
  } catch (err) {
    window.alert(`Reset impossible: ${err.message}`);
  }
});

refreshState().catch((err) => {
  window.alert(`Erreur de chargement initial: ${err.message}`);
});
