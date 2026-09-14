const API = "/api";

const el = (id) => document.getElementById(id);

const state = {
  datasets: [],
  currentConversationId: null,
  currentTurnId: null,
  eventSource: null,
  map: null,
  resultLayer: null,
  contextLayer: null,
};

// --------------------------------------------------------------- utils

function node(tag, props = {}, children = []) {
  const elmt = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "class") elmt.className = value;
    else if (key === "text") elmt.textContent = value;
    else elmt.setAttribute(key, value);
  }
  for (const child of children) {
    if (child) elmt.appendChild(child);
  }
  return elmt;
}

function fmtTime(ts) {
  const d = new Date(ts);
  if (isNaN(d.getTime())) return "";
  return d.toLocaleString([], { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

async function safely(label, fn) {
  try {
    await fn();
  } catch (e) {
    console.error(`${label} failed:`, e);
    appendNote(`${label} failed to initialize: ${e.message}`);
  }
}

// -------------------------------------------------------------- health

async function checkHealth() {
  const dot = el("status-dot");
  const text = el("status-text");
  try {
    const res = await fetch(`${API}/health`);
    const body = await res.json();
    if (body.agent_ready) {
      dot.className = "status-dot ok";
      text.textContent = "agent ready";
      text.title = "";
    } else {
      dot.className = "status-dot error";
      text.textContent = "agent not ready";
      text.title = body.agent_error || "Unknown error";
    }
  } catch {
    dot.className = "status-dot error";
    text.textContent = "API unreachable";
  }
}

// ------------------------------------------------------------ datasets

function datasetOptionValue(datasetName, filename) {
  return JSON.stringify({ dataset: datasetName, file: filename });
}

async function loadDatasets() {
  const select = el("dataset-select");
  select.innerHTML = "";

  try {
    const res = await fetch(`${API}/datasets`);
    const body = await res.json();
    state.datasets = body.datasets || [];
  } catch {
    select.appendChild(node("option", { text: "Could not reach API" }));
    return;
  }

  const usable = [];
  for (const ds of state.datasets) {
    for (const f of ds.files) usable.push({ dataset: ds.name, file: f.filename });
  }

  if (usable.length === 0) {
    select.appendChild(node("option", { value: "", text: "No datasets yet — upload one below" }));
    if (!state.currentConversationId) el("dataset-hint").textContent = "No dataset selected.";
    return;
  }

  for (const item of usable) {
    const opt = node("option", {
      value: datasetOptionValue(item.dataset, item.file),
      text: `${item.dataset} / ${item.file}`,
    });
    select.appendChild(opt);
  }

  if (!state.currentConversationId) updateDatasetHint();
}

function updateDatasetHint() {
  const select = el("dataset-select");
  if (!select.value) {
    el("dataset-hint").textContent = "No dataset selected.";
    return;
  }
  const { dataset, file } = JSON.parse(select.value);
  el("dataset-hint").textContent = `Ready: data/raw/${dataset}/${file}`;
  loadContextLayerOptions(dataset, file);
}

async function uploadDataset(file) {
  const hint = el("dataset-hint");
  hint.textContent = `Uploading ${file.name}...`;
  hint.classList.remove("error");

  const form = new FormData();
  form.append("file", file);

  try {
    const res = await fetch(`${API}/datasets`, { method: "POST", body: form });
    const body = await res.json();

    if (!res.ok) {
      hint.textContent = body.detail || "Upload failed.";
      hint.classList.add("error");
      return;
    }

    await loadDatasets();
    const select = el("dataset-select");
    if (body.files && body.files.length) {
      select.value = datasetOptionValue(body.name, body.files[0].filename);
    }
    updateDatasetHint();
    hint.textContent = `Uploaded: ${body.name} (${body.files.length} file(s)).`;
  } catch (e) {
    hint.textContent = "Upload failed: " + e.message;
    hint.classList.add("error");
  }
}

// --------------------------------------------------------- conversations

async function loadConversations() {
  const list = el("conversation-list");
  list.innerHTML = "";

  let conversations = [];
  try {
    const res = await fetch(`${API}/conversations`);
    const body = await res.json();
    conversations = body.conversations || [];
  } catch {
    list.appendChild(node("li", { class: "conversation-empty", text: "Could not reach API" }));
    return;
  }

  if (conversations.length === 0) {
    list.appendChild(node("li", { class: "conversation-empty", text: "No conversations yet." }));
    return;
  }

  for (const c of conversations) {
    const item = node("li", {
      class: "conversation-item" + (c.id === state.currentConversationId ? " active" : ""),
    });
    item.appendChild(node("div", { class: "conversation-item__title", text: c.title }));
    const meta = node("div", { class: "conversation-item__meta" });
    const stepWord = c.turn_count === 1 ? "step" : "steps";
    meta.appendChild(node("span", { text: `${c.turn_count} ${stepWord}` }));
    meta.appendChild(node("span", { text: fmtTime(c.updated_at) }));
    item.appendChild(meta);

    const del = node("button", {
      class: "conversation-item__delete",
      text: "\u00d7",
      title: "Delete this conversation",
    });
    del.addEventListener("click", (event) => {
      event.stopPropagation();
      deleteConversation(c.id);
    });
    item.appendChild(del);

    item.addEventListener("click", () => openConversation(c.id));
    list.appendChild(item);
  }
}

async function deleteConversation(id) {
  await fetch(`${API}/conversations/${id}`, { method: "DELETE" });
  if (state.currentConversationId === id) startNewChat();
  loadConversations();
}

function syncRunButtonLabel() {
  el("run-btn").textContent = state.currentConversationId ? "Send" : "Run";
}

function enterConversationMode(conversation) {
  const select = el("dataset-select");
  select.disabled = true;
  el("dataset-hint").textContent = `Chat dataset: ${conversation.dataset_host_path}`;
  el("dataset-hint").classList.remove("error");

  el("task-label").textContent = "Continue this chat";
  el("task-input").placeholder = "Ask a follow-up, e.g. now compute the total area of each building";
  el("new-chat-btn").hidden = false;
  syncRunButtonLabel();
}

function startNewChat() {
  closeStream();
  state.currentConversationId = null;
  state.currentTurnId = null;
  clearTimeline();
  clearResultLayer();

  el("dataset-select").disabled = false;
  el("task-label").textContent = "Task";
  el("task-input").placeholder =
    "e.g. Find every building within 500m of the rivers and save it as a new layer.";
  el("task-input").value = "";
  el("new-chat-btn").hidden = true;
  syncRunButtonLabel();
  updateDatasetHint();
  loadConversations();
}

async function openConversation(id) {
  closeStream();
  state.currentConversationId = id;
  state.currentTurnId = null;
  clearTimeline();
  clearResultLayer();

  let conversation;
  try {
    const res = await fetch(`${API}/conversations/${id}`);
    if (!res.ok) throw new Error("not found");
    conversation = await res.json();
  } catch {
    appendNote("This conversation is no longer available on the server.");
    return;
  }

  enterConversationMode(conversation);

  for (const turn of conversation.turns) {
    renderTurnHeader(turn);
    for (const evt of turn.events) renderEvent(evt);
  }

  loadConversations();
}

// ------------------------------------------------------------- timeline

function clearTimeline() {
  const timeline = el("timeline");
  timeline.innerHTML = "";
}

function appendNote(text) {
  const timeline = el("timeline");
  const li = node("li", { class: "timeline__empty", text });
  timeline.appendChild(li);
}

function renderTurnHeader(turn) {
  const timeline = el("timeline");
  if (timeline.querySelector(".timeline__empty")) timeline.innerHTML = "";

  const header = node("li", { class: "turn-header" });
  header.appendChild(
    node("span", { class: "turn-header__label", text: `Step ${turn.turn_index + 1}` })
  );
  header.appendChild(node("span", { class: "turn-header__task", text: turn.task }));
  timeline.appendChild(header);
}

function stepEl(className, headText, badgeText) {
  const li = node("li", { class: `step ${className}` });
  const head = node("div", { class: "step__head" });
  head.appendChild(node("span", { text: headText }));
  if (badgeText) head.appendChild(node("span", { class: "step__badge", text: badgeText }));
  li.appendChild(head);
  const body = node("div", { class: "step__body" });
  li.appendChild(body);
  return { li, body };
}

function kv(pairs) {
  const dl = node("dl", { class: "kv" });
  for (const [k, v] of pairs) {
    if (v === undefined || v === null || v === "") continue;
    dl.appendChild(node("dt", { text: k }));
    dl.appendChild(node("dd", { text: v }));
  }
  return dl;
}

function renderEvent(evt) {
  const timeline = el("timeline");
  if (timeline.querySelector(".timeline__empty")) timeline.innerHTML = "";

  const { type, data } = evt;
  let entry;

  if (type === "decision") {
    entry = stepEl("step--decision", `Decided: ${data.action}`, `iteration ${data.iteration}`);
    entry.body.appendChild(node("p", { text: data.reason || "" }));
    entry.body.appendChild(
      kv([
        ["query", data.query],
        ["path", data.path],
        ["layer", data.layer],
      ])
    );
  } else if (type === "docs_retrieved") {
    entry = stepEl("step--info", "Searched documentation", `${data.total_docs} total`);
    if (data.new_docs.length === 0) {
      entry.body.appendChild(node("p", { text: "No new documents (already retrieved)." }));
    } else {
      const chips = node("div", { class: "chips" });
      for (const d of data.new_docs) {
        const label = d.library ? `[${d.library}] ${d.title || d.source}` : d.title || d.source || "doc";
        chips.appendChild(
          node("span", { class: "chip", text: `${label} (${Number(d.score).toFixed(2)})` })
        );
      }
      entry.body.appendChild(chips);
    }
  } else if (type === "layers_listed") {
    entry = stepEl("step--info", "Listed dataset layers");
    const chips = node("div", { class: "chips" });
    for (const layer of data.layers || []) chips.appendChild(node("span", { class: "chip", text: layer }));
    entry.body.appendChild(chips);
  } else if (type === "layer_inspected") {
    entry = stepEl("step--info", `Inspected layer`, data.layer);
    const r = data.result || {};
    entry.body.appendChild(
      kv([
        ["rows", r.rows],
        ["crs", r.crs],
        ["columns", (r.columns || []).join(", ")],
        ["geometry", JSON.stringify(r.geometry_type || {})],
        ["bounds", (r.bounds || []).map((v) => Number(v).toFixed(4)).join(", ")],
      ])
    );
  } else if (type === "code_generated") {
    entry = stepEl("step--code", "Generated code");
    entry.body.appendChild(node("pre", { class: "code-block", text: data.code }));
  } else if (type === "validation_result") {
    const ok = data.valid;
    entry = stepEl(ok ? "step--code" : "step--danger", "Validated code");
    entry.body.appendChild(
      node("span", { class: `badge ${ok ? "badge--ok" : "badge--bad"}`, text: ok ? "valid" : "invalid" })
    );
    if (!ok) {
      entry.body.appendChild(
        kv([
          ["syntax error", data.syntax_error],
          ["disallowed imports", (data.import_violations || []).join(", ")],
          ["dangerous operations", (data.dangerous_operations || []).join(", ")],
        ])
      );
    }
  } else if (type === "execution_result") {
    if (data.skipped) {
      entry = stepEl("step--danger", "Execution skipped");
      entry.body.appendChild(node("p", { text: data.reason }));
    } else {
      const ok = data.status === "success";
      entry = stepEl(ok ? "step--code" : "step--danger", "Executed in sandbox");
      entry.body.appendChild(
        node("span", { class: `badge ${ok ? "badge--ok" : "badge--bad"}`, text: data.status })
      );
      if (data.stdout) entry.body.appendChild(node("pre", { class: "code-block", text: data.stdout }));
      if (data.stderr) entry.body.appendChild(node("pre", { class: "code-block", text: data.stderr }));
      if (data.error_message) entry.body.appendChild(node("p", { text: data.error_message }));
      if (data.artifacts && data.artifacts.length) {
        const chips = node("div", { class: "chips" });
        for (const a of data.artifacts) chips.appendChild(node("span", { class: "chip", text: a }));
        entry.body.appendChild(chips);
        showArtifactsOnMap(data.artifacts);
      }
    }
  } else if (type === "finished") {
    entry = stepEl("step--decision", "Run finished");
  } else if (type === "error") {
    entry = stepEl("step--danger", "Error", "");
    entry.body.appendChild(node("p", { text: data.message }));
  } else {
    return;
  }

  timeline.appendChild(entry.li);
  timeline.parentElement.scrollTop = timeline.parentElement.scrollHeight;
}

// ---------------------------------------------------------------- tasks

function closeStream() {
  if (state.eventSource) {
    state.eventSource.close();
    state.eventSource = null;
  }
}

function streamTurn(conversationId, turnId) {
  const runBtn = el("run-btn");

  closeStream();
  const source = new EventSource(`${API}/conversations/${conversationId}/turns/${turnId}/stream`);
  state.eventSource = source;

  source.onmessage = (message) => {
    const evt = JSON.parse(message.data);

    if (evt.node === "server" && evt.type === "done") {
      if (evt.data.status === "failed" && evt.data.error) {
        appendNote(`Run failed: ${evt.data.error}`);
      }
      closeStream();
      runBtn.disabled = false;
      syncRunButtonLabel();
      loadConversations();
      return;
    }

    renderEvent(evt);
  };

  source.onerror = () => {
    appendNote("Lost connection to the run stream.");
    closeStream();
    runBtn.disabled = false;
    syncRunButtonLabel();
  };
}

async function submitTask() {
  const taskText = el("task-input").value.trim();

  if (!taskText) {
    el("dataset-hint").textContent = "Write a task first.";
    return;
  }

  const runBtn = el("run-btn");
  const isNewConversation = state.currentConversationId === null;

  if (isNewConversation) {
    const select = el("dataset-select");
    if (!select.value) {
      el("dataset-hint").textContent = "Choose or upload a dataset first.";
      el("dataset-hint").classList.add("error");
      return;
    }

    const { dataset, file } = JSON.parse(select.value);

    runBtn.disabled = true;
    runBtn.textContent = "Running…";
    clearTimeline();
    clearResultLayer();

    let body;
    try {
      const res = await fetch(`${API}/conversations`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task: taskText, dataset, file }),
      });
      body = await res.json();
      if (!res.ok) {
        appendNote(body.detail || "Could not start the conversation.");
        runBtn.disabled = false;
        syncRunButtonLabel();
        return;
      }
    } catch (e) {
      appendNote("Could not reach the API: " + e.message);
      runBtn.disabled = false;
      syncRunButtonLabel();
      return;
    }

    state.currentConversationId = body.conversation_id;
    state.currentTurnId = body.turn_id;

    const conversation = await fetch(`${API}/conversations/${body.conversation_id}`).then((r) => r.json());
    enterConversationMode(conversation);
    renderTurnHeader({ turn_index: 0, task: taskText });

    el("task-input").value = "";
    runBtn.disabled = true;
    runBtn.textContent = "Working…";
    streamTurn(body.conversation_id, body.turn_id);
  } else {
    runBtn.disabled = true;
    runBtn.textContent = "Sending…";

    let body;
    try {
      const res = await fetch(`${API}/conversations/${state.currentConversationId}/turns`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ task: taskText }),
      });
      body = await res.json();
      if (!res.ok) {
        appendNote(body.detail || "Could not send the follow-up.");
        runBtn.disabled = false;
        syncRunButtonLabel();
        return;
      }
    } catch (e) {
      appendNote("Could not reach the API: " + e.message);
      runBtn.disabled = false;
      syncRunButtonLabel();
      return;
    }

    state.currentTurnId = body.turn_id;

    const conversation = await fetch(`${API}/conversations/${state.currentConversationId}`).then((r) =>
      r.json()
    );
    const newTurn = conversation.turns[conversation.turns.length - 1];
    renderTurnHeader(newTurn);

    el("task-input").value = "";
    runBtn.disabled = true;
    runBtn.textContent = "Working…";
    streamTurn(state.currentConversationId, body.turn_id);
  }
}

// ----------------------------------------------------------------- map

function initMap() {
  const map = L.map("map", { zoomControl: false, attributionControl: false }).setView([18.6, 73.8], 11);

  L.control.zoom({ position: "topleft" }).addTo(map);

  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    subdomains: "abcd",
    maxZoom: 19,
  }).addTo(map);

  map.on("mousemove", (e) => {
    el("map-readout").textContent = `${e.latlng.lat.toFixed(5)}, ${e.latlng.lng.toFixed(5)}`;
  });

  state.map = map;
}

function clearResultLayer() {
  if (state.resultLayer && state.map) {
    state.map.removeLayer(state.resultLayer);
    state.resultLayer = null;
  }
}

function styleForResult() {
  return { color: "#e8672a", weight: 2, fillColor: "#e8672a", fillOpacity: 0.28, radius: 5 };
}

function styleForContext() {
  return { color: "#4a7a94", weight: 1, fillOpacity: 0.08, radius: 3 };
}

async function fetchGeojson(path, layer) {
  const params = new URLSearchParams({ path });
  if (layer) params.set("layer", layer);
  const res = await fetch(`${API}/geo?${params.toString()}`);
  if (!res.ok) throw new Error(`Could not load '${path}'`);
  return res.json();
}

async function showArtifactsOnMap(artifactPaths) {
  if (!state.map) return;

  const vectorPaths = artifactPaths.filter((p) => /\.(gpkg|geojson|json|fgb|gml|kml)$/i.test(p));
  if (vectorPaths.length === 0) return;

  clearResultLayer();

  const group = L.layerGroup();

  for (const path of vectorPaths) {
    try {
      const geojson = await fetchGeojson(path);
      const layer = L.geoJSON(geojson, {
        style: styleForResult(),
        pointToLayer: (feature, latlng) => L.circleMarker(latlng, styleForResult()),
      });
      group.addLayer(layer);
    } catch (e) {
      appendNote(`Could not render '${path}' on the map: ${e.message}`);
    }
  }

  group.addTo(state.map);
  state.resultLayer = group;

  if (el("toggle-output-layer").checked === false) state.map.removeLayer(group);

  fitToResults();
}

function fitToResults() {
  if (state.resultLayer && state.map) {
    let hasBounds = false;
    state.resultLayer.eachLayer((l) => {
      if (l.getBounds && l.getBounds().isValid()) hasBounds = true;
    });
    if (hasBounds) {
      const all = L.featureGroup();
      state.resultLayer.eachLayer((l) => all.addLayer(l));
      state.map.fitBounds(all.getBounds(), { padding: [20, 20] });
    }
  }
}

async function loadContextLayerOptions(datasetName, filename) {
  const select = el("context-layer-select");
  select.innerHTML = "";
  select.appendChild(node("option", { value: "", text: "none" }));

  try {
    const res = await fetch(
      `${API}/datasets/${encodeURIComponent(datasetName)}/layers?file=${encodeURIComponent(filename)}`
    );
    if (!res.ok) return;
    const body = await res.json();
    for (const layer of body.layers) {
      select.appendChild(node("option", { value: layer, text: layer }));
    }
  } catch {
    // Dataset may have no readable layers yet - leave the dropdown at "none".
  }
}

async function loadContextLayer() {
  if (!state.map) return;

  const datasetSelect = el("dataset-select");
  const layerSelect = el("context-layer-select");
  if (state.contextLayer) {
    state.map.removeLayer(state.contextLayer);
    state.contextLayer = null;
  }
  if (!datasetSelect.value || !layerSelect.value) return;

  const { dataset, file } = JSON.parse(datasetSelect.value);
  const path = `data/raw/${dataset}/${file}`;

  try {
    const geojson = await fetchGeojson(path, layerSelect.value);
    const layer = L.geoJSON(geojson, {
      style: styleForContext(),
      pointToLayer: (feature, latlng) => L.circleMarker(latlng, styleForContext()),
    });
    layer.addTo(state.map);
    state.contextLayer = layer;
    if (el("toggle-input-layer").checked === false) state.map.removeLayer(layer);
  } catch (e) {
    appendNote(`Could not load context layer: ${e.message}`);
  }
}

// ---------------------------------------------------------------- init

function wireEvents() {
  el("run-btn").addEventListener("click", submitTask);
  el("new-chat-btn").addEventListener("click", startNewChat);
  el("dataset-select").addEventListener("change", updateDatasetHint);
  el("dataset-upload").addEventListener("change", (e) => {
    if (e.target.files[0]) uploadDataset(e.target.files[0]);
  });
  el("fit-bounds-btn").addEventListener("click", fitToResults);
  el("context-layer-select").addEventListener("change", loadContextLayer);
  el("toggle-input-layer").addEventListener("change", (e) => {
    if (!state.contextLayer) return;
    if (e.target.checked) state.contextLayer.addTo(state.map);
    else state.map.removeLayer(state.contextLayer);
  });
  el("toggle-output-layer").addEventListener("change", (e) => {
    if (!state.resultLayer) return;
    if (e.target.checked) state.resultLayer.addTo(state.map);
    else state.map.removeLayer(state.resultLayer);
  });
}

document.addEventListener("DOMContentLoaded", async () => {
  try {
    initMap();
  } catch (e) {
    console.error("Map failed:", e);
    const mapDiv = el("map");
    if (mapDiv) {
      mapDiv.style.display = "flex";
      mapDiv.style.alignItems = "center";
      mapDiv.style.justifyContent = "center";
      mapDiv.style.padding = "24px";
      mapDiv.style.textAlign = "center";
      mapDiv.style.color = "var(--muted)";
      mapDiv.textContent =
        "Map could not load (the Leaflet library failed to initialize). " +
        "The rest of the console still works.";
    }
  }

  safely("Controls", wireEvents);
  safely("Agent status check", checkHealth);
  safely("Dataset list", loadDatasets);
  safely("Conversation list", loadConversations);
});
