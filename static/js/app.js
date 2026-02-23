/* ===== CS Monday Tracker – Dashboard JS ===== */
const API = "";  // same origin

// ------------------------------------------------------------------ //
// Utilities                                                            //
// ------------------------------------------------------------------ //

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(API + path, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || `HTTP ${res.status}`);
  return data;
}

function toast(msg, type = "success") {
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.className = `toast ${type} show`;
  clearTimeout(el._timer);
  el._timer = setTimeout(() => el.classList.remove("show"), 3500);
}

function ratingClass(r) {
  if (r >= 1.1) return "rating-high";
  if (r >= 0.9) return "rating-mid";
  return "rating-low";
}

function fmtRating(r) {
  const n = parseFloat(r) || 0;
  return `<span class="${ratingClass(n)}">${n.toFixed(2)}</span>`;
}

function statsTable(players, extraCols = []) {
  if (!players || players.length === 0) {
    return `<p class="empty-msg">No stats available yet.</p>`;
  }
  const extra = extraCols.map(c => `<th>${c.label}</th>`).join("");
  const rows = players.map((p, i) => {
    const avatar = p.avatar_url
      ? `<img class="avatar" src="${p.avatar_url}" alt="" onerror="this.style.display='none'">`
      : `<span class="avatar" style="background:#30363d;display:inline-block;"></span>`;
    const extraCells = extraCols.map(c => `<td>${c.render(p)}</td>`).join("");
    return `
      <tr>
        <td class="rank">#${i + 1}</td>
        <td><div class="player-cell">${avatar}<span class="username">${p.username}</span></div></td>
        <td>${p.games}</td>
        <td>${fmtRating(p.avg_rating)}</td>
        <td>${fmtRating(p.avg_leetify_rating)}</td>
        <td>${(parseFloat(p.avg_kd) || 0).toFixed(2)}</td>
        <td>${(parseFloat(p.avg_adr) || 0).toFixed(1)}</td>
        <td>${(parseFloat(p.avg_hs_pct) || 0).toFixed(1)}%</td>
        ${extraCells}
      </tr>`;
  }).join("");
  return `
    <div style="overflow-x:auto">
      <table class="stats-table">
        <thead>
          <tr>
            <th></th>
            <th>Player</th>
            <th>Games</th>
            <th>HLTV Rating</th>
            <th>Leetify Rating</th>
            <th>K/D</th>
            <th>ADR</th>
            <th>HS%</th>
            ${extra}
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </div>`;
}

// ------------------------------------------------------------------ //
// Tab navigation                                                       //
// ------------------------------------------------------------------ //

document.querySelectorAll(".nav-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
    document.querySelectorAll(".tab-content").forEach(s => {
      s.classList.add("hidden");
      s.classList.remove("active");
    });
    btn.classList.add("active");
    const tab = document.getElementById(`tab-${btn.dataset.tab}`);
    tab.classList.remove("hidden");
    tab.classList.add("active");
    loadTab(btn.dataset.tab);
  });
});

function loadTab(name) {
  if (name === "home")     loadHome();
  if (name === "session")  loadCurrentSession();
  if (name === "alltime")  loadAllTime();
  if (name === "players")  loadPlayers();
  if (name === "problem")  loadProblemPlayers();
  if (name === "ai")       loadAnalyses();
}

// ------------------------------------------------------------------ //
// Home Tab – Last 30 Days                                             //
// ------------------------------------------------------------------ //

async function loadHome() {
  try {
    const players = await api("GET", "/api/stats/monthly");
    const summaryEl = document.getElementById("home-summary");
    const tableEl   = document.getElementById("home-table-wrap");

    // Build summary cards
    const active = players.filter(p => p.games > 0);
    const topPlayer  = active.length ? active[0] : null;
    const totalKills = active.reduce((s, p) => s + p.total_kills, 0);
    const avgRating  = active.length
      ? (active.reduce((s, p) => s + p.avg_rating, 0) / active.length).toFixed(2)
      : "—";

    summaryEl.innerHTML = `
      <div class="summary-card">
        <div class="summary-label">Active Players</div>
        <div class="summary-value">${active.length}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Top Player (Rating)</div>
        <div class="summary-value">${topPlayer ? topPlayer.username : "—"}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Total Kills (30d)</div>
        <div class="summary-value">${totalKills}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Avg HLTV Rating</div>
        <div class="summary-value">${avgRating}</div>
      </div>`;

    tableEl.innerHTML = statsTable(players);
  } catch (e) {
    toast(e.message, "error");
  }
}

// ------------------------------------------------------------------ //
// Current Session Tab                                                  //
// ------------------------------------------------------------------ //

async function loadCurrentSession() {
  try {
    const data = await api("GET", "/api/sessions/current");
    const wrap = document.getElementById("session-table-wrap");
    const info = document.getElementById("session-info");

    if (!data.session) {
      wrap.innerHTML = `<p class="empty-msg">No session yet. Create a session and sync data.</p>`;
      info.classList.add("hidden");
      return;
    }

    info.classList.remove("hidden");
    document.getElementById("session-name").textContent = data.session.name;
    document.getElementById("session-date").textContent =
      new Date(data.session.date).toLocaleString();
    document.getElementById("session-notes").textContent = data.session.notes || "";

    wrap.innerHTML = statsTable(data.players);
  } catch (e) {
    toast(e.message, "error");
  }
}

// ------------------------------------------------------------------ //
// All-Time Stats Tab                                                   //
// ------------------------------------------------------------------ //

async function loadAllTime() {
  try {
    const players = await api("GET", "/api/stats");
    document.getElementById("alltime-table-wrap").innerHTML = statsTable(players);
  } catch (e) {
    toast(e.message, "error");
  }
}

// ------------------------------------------------------------------ //
// Players Tab                                                          //
// ------------------------------------------------------------------ //

async function loadPlayers() {
  try {
    const players = await api("GET", "/api/players");
    const grid = document.getElementById("players-list");
    if (!players.length) {
      grid.innerHTML = `<p class="empty-msg">No players tracked yet.</p>`;
      return;
    }
    grid.innerHTML = players.map(p => `
      <div class="player-card">
        ${p.avatar_url ? `<img src="${p.avatar_url}" alt="" onerror="this.style.display='none'">` : ""}
        <span class="name">${p.username}</span>
        <span class="steam-id">${p.steam_id}</span>
        <button class="btn btn-danger" onclick="removePlayer('${p.steam_id}')">Remove</button>
      </div>`).join("");
  } catch (e) {
    toast(e.message, "error");
  }
}

document.getElementById("btn-add-player").addEventListener("click", async () => {
  const steamId = document.getElementById("input-steam-id").value.trim();
  if (!steamId) { toast("Enter a Steam64 ID", "error"); return; }
  try {
    await api("POST", "/api/players", { steam_id: steamId });
    document.getElementById("input-steam-id").value = "";
    toast("Player added!");
    loadPlayers();
  } catch (e) {
    toast(e.message, "error");
  }
});

async function removePlayer(steamId) {
  if (!confirm("Remove this player?")) return;
  try {
    await api("DELETE", `/api/players/${steamId}`);
    toast("Player removed");
    loadPlayers();
  } catch (e) {
    toast(e.message, "error");
  }
}

// ------------------------------------------------------------------ //
// Steam Friends Browser                                                //
// ------------------------------------------------------------------ //

document.getElementById("btn-load-friends").addEventListener("click", async () => {
  const steamId = document.getElementById("input-friends-steam-id").value.trim();
  if (!steamId) { toast("Enter a Steam64 ID", "error"); return; }
  const btn = document.getElementById("btn-load-friends");
  btn.disabled = true;
  btn.textContent = "Loading…";
  try {
    const friends = await api("GET", `/api/steam/friends/${steamId}`);
    const grid = document.getElementById("friends-grid");
    if (!friends.length) {
      grid.innerHTML = `<p class="empty-msg">No friends found or friends list is private.</p>`;
      return;
    }
    grid.innerHTML = friends.map(f => `
      <div class="player-card">
        ${f.avatar_url ? `<img src="${f.avatar_url}" alt="" onerror="this.style.display='none'">` : ""}
        <span class="name">${f.username}</span>
        <span class="steam-id">${f.steam_id}</span>
        ${f.tracked
          ? `<span class="badge-ok" style="padding:4px 10px">✓ Tracked</span>`
          : `<button class="btn btn-primary" onclick="addFriend('${f.steam_id}', this)">+ Add</button>`
        }
      </div>`).join("");
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Load Friends";
  }
});

async function addFriend(steamId, btnEl) {
  try {
    await api("POST", "/api/players", { steam_id: steamId });
    btnEl.outerHTML = `<span class="badge-ok" style="padding:4px 10px">✓ Tracked</span>`;
    toast("Player added!");
    loadPlayers();
  } catch (e) {
    toast(e.message, "error");
  }
}

// ------------------------------------------------------------------ //
// Problem Players Tab                                                  //
// ------------------------------------------------------------------ //

async function loadProblemPlayers() {
  try {
    const players = await api("GET", "/api/stats/problem-players");
    const wrap = document.getElementById("problem-table-wrap");
    const cols = [{
      label: "Problem Score",
      render: p => {
        const s = parseFloat(p.problem_score) || 0;
        const cls = s > 3 ? "badge-danger" : s > 1.5 ? "badge-warning" : "badge-ok";
        return `<span class="${cls}">${s.toFixed(2)}</span>`;
      }
    }];
    wrap.innerHTML = statsTable(players, cols);
  } catch (e) {
    toast(e.message, "error");
  }
}

// ------------------------------------------------------------------ //
// Sync Button                                                          //
// ------------------------------------------------------------------ //

async function syncData(sessionId) {
  try {
    toast("Syncing with Leetify...", "success");
    const body = sessionId ? { session_id: sessionId } : {};
    const result = await api("POST", "/api/sync", body);
    toast(`Synced ${result.synced_games} new games.${result.errors.length ? " Some errors." : ""}`);
    loadHome();
    loadCurrentSession();
    loadAllTime();
  } catch (e) {
    toast(e.message, "error");
  }
}

document.getElementById("btn-sync-home").addEventListener("click", () => syncData());
document.getElementById("btn-sync").addEventListener("click", () => syncData());
document.getElementById("btn-sync-alltime").addEventListener("click", () => syncData());

// ------------------------------------------------------------------ //
// New Session Modal                                                    //
// ------------------------------------------------------------------ //

document.getElementById("btn-new-session").addEventListener("click", async () => {
  // Populate player list in modal
  try {
    const players = await api("GET", "/api/players");
    const sel = document.getElementById("ns-players");
    sel.innerHTML = players.map(p =>
      `<option value="${p.steam_id}">${p.username}</option>`
    ).join("");
  } catch {}
  document.getElementById("modal-overlay").classList.remove("hidden");
});

document.getElementById("ns-cancel").addEventListener("click", () => {
  document.getElementById("modal-overlay").classList.add("hidden");
});

document.getElementById("modal-overlay").addEventListener("click", e => {
  if (e.target === document.getElementById("modal-overlay"))
    document.getElementById("modal-overlay").classList.add("hidden");
});

document.getElementById("ns-create").addEventListener("click", async () => {
  const name = document.getElementById("ns-name").value.trim() || "Monday Session";
  const notes = document.getElementById("ns-notes").value.trim();
  const sel = document.getElementById("ns-players");
  const steam_ids = Array.from(sel.selectedOptions).map(o => o.value);

  try {
    await api("POST", "/api/sessions", { name, notes, steam_ids });
    document.getElementById("modal-overlay").classList.add("hidden");
    toast("Session created!");
    loadCurrentSession();
  } catch (e) {
    toast(e.message, "error");
  }
});

// ------------------------------------------------------------------ //
// AI Analysis Tab                                                      //
// ------------------------------------------------------------------ //

async function loadAnalyses() {
  try {
    const analyses = await api("GET", "/api/analysis");
    const container = document.getElementById("past-analyses");
    if (!analyses.length) {
      container.innerHTML = `<p class="empty-msg">No past analyses yet.</p>`;
      return;
    }
    container.innerHTML = analyses.map(a => `
      <div class="card analysis-card">
        <div>${a.analysis || ""}</div>
        <p class="muted" style="margin-top:12px">
          ${new Date(a.created_at).toLocaleString()} · ${a.scope} · ${a.model_used}
        </p>
      </div>`).join("");
  } catch (e) {
    toast(e.message, "error");
  }
}

document.getElementById("btn-analyse").addEventListener("click", async () => {
  const scope = document.getElementById("analysis-scope").value;
  const btn = document.getElementById("btn-analyse");
  btn.disabled = true;
  btn.textContent = "Generating…";
  try {
    const result = await api("POST", "/api/analysis", { scope });
    const resDiv = document.getElementById("analysis-result");
    resDiv.classList.remove("hidden");
    document.getElementById("analysis-text").textContent = result.analysis;
    document.getElementById("analysis-meta").textContent =
      `Generated ${new Date(result.created_at).toLocaleString()} using ${result.model_used}`;
    loadAnalyses();
  } catch (e) {
    toast(e.message, "error");
  } finally {
    btn.disabled = false;
    btn.textContent = "Generate Analysis";
  }
});

// ------------------------------------------------------------------ //
// Initial load                                                         //
// ------------------------------------------------------------------ //

loadHome();
