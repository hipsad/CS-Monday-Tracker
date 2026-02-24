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
    const wl = (p.wins !== undefined)
      ? `<span style="color:var(--green)">${p.wins}W</span>-<span style="color:var(--red)">${p.losses}L</span>`
      : `—`;
    const wr = (p.wins !== undefined && (p.wins + p.losses) > 0)
      ? `${p.win_rate.toFixed(1)}%`
      : `—`;
    const extraCells = extraCols.map(c => `<td>${c.render(p)}</td>`).join("");
    return `
      <tr>
        <td class="rank">#${i + 1}</td>
        <td><div class="player-cell">${avatar}<span class="username player-link" data-steamid="${p.steam_id}" style="cursor:pointer;text-decoration:underline dotted">${p.username}</span></div></td>
        <td>${p.games}</td>
        <td>${wl}</td>
        <td>${wr}</td>
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
            <th>W-L</th>
            <th>Win%</th>
            <th>Rating</th>
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
  if (name === "home")         loadHome();
  if (name === "session")      loadCurrentSession();
  if (name === "alltime")      loadAllTime();
  if (name === "records")      loadRecords();
  if (name === "win-stats")    loadWinStats();
  if (name === "player-stats") loadPlayerStats();
  if (name === "players")      loadPlayers();
  if (name === "problem")      loadProblemPlayers();
  if (name === "ai")           loadAnalyses();
}

// ------------------------------------------------------------------ //
// Home Tab – Last 15 Games                                             //
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
      ? (active.reduce((s, p) => s + p.avg_leetify_rating, 0) / active.length).toFixed(2)
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
        <div class="summary-label">Total Kills (15 games)</div>
        <div class="summary-value">${totalKills}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Avg Leetify Rating</div>
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
// Player Stats Tab (filterable per-player view)                       //
// ------------------------------------------------------------------ //

let _psCurrentSteamId = null;
let _psGames = [];

async function loadPlayerStats() {
  try {
    const players = await api("GET", "/api/players");
    const sel = document.getElementById("ps-player-select");
    sel.innerHTML = `<option value="">— Select a player —</option>` +
      players.map(p => `<option value="${p.steam_id}">${p.username}</option>`).join("");

    // Restore last selection
    if (_psCurrentSteamId) {
      sel.value = _psCurrentSteamId;
      renderPlayerStats(_psCurrentSteamId);
    }
  } catch (e) {
    toast(e.message, "error");
  }
}

document.getElementById("ps-player-select").addEventListener("change", async function () {
  _psCurrentSteamId = this.value || null;
  if (_psCurrentSteamId) await renderPlayerStats(_psCurrentSteamId);
  else {
    document.getElementById("ps-summary").innerHTML = "";
    document.getElementById("ps-table-wrap").innerHTML = `<p class="empty-msg">Select a player to view their stats.</p>`;
  }
});

document.querySelectorAll(".ps-stat-toggle").forEach(cb => {
  cb.addEventListener("change", () => { if (_psCurrentSteamId) renderPlayerStats(_psCurrentSteamId); });
});

async function renderPlayerStats(steamId) {
  const wrap = document.getElementById("ps-table-wrap");
  const summaryEl = document.getElementById("ps-summary");
  wrap.innerHTML = `<p class="muted" style="text-align:center;padding:20px">Loading…</p>`;
  try {
    const data = await api("GET", `/api/stats/${steamId}`);
    const p = data.player;
    const s = data.stats;
    _psGames = data.games || [];

    summaryEl.innerHTML = `
      <div class="summary-card"><div class="summary-label">Games</div><div class="summary-value">${s.games}</div></div>
      <div class="summary-card"><div class="summary-label">Rating</div><div class="summary-value">${(s.avg_leetify_rating||0).toFixed(2)}</div></div>
      <div class="summary-card"><div class="summary-label">K/D</div><div class="summary-value">${(s.avg_kd||0).toFixed(2)}</div></div>
      <div class="summary-card"><div class="summary-label">ADR</div><div class="summary-value">${(s.avg_adr||0).toFixed(1)}</div></div>
      <div class="summary-card"><div class="summary-label">HS%</div><div class="summary-value">${(s.avg_hs_pct||0).toFixed(1)}%</div></div>
      <div class="summary-card"><div class="summary-label">Kills</div><div class="summary-value">${s.total_kills}</div></div>
      <div class="summary-card"><div class="summary-label">Deaths</div><div class="summary-value">${s.total_deaths}</div></div>
      <div class="summary-card"><div class="summary-label">Assists</div><div class="summary-value">${s.total_assists}</div></div>`;

    const cols = getActiveStatCols();
    if (!_psGames.length) {
      wrap.innerHTML = `<p class="empty-msg">No game history yet.</p>`;
      return;
    }

    const headerCells = cols.map(c => `<th>${c.label}</th>`).join("");
    const rows = _psGames.map(g => {
      const d = g.game.played_at ? new Date(g.game.played_at).toLocaleDateString() : "—";
      const result = g.won === true
        ? `<span class="badge-ok" style="padding:2px 6px">W</span>`
        : g.won === false
          ? `<span class="badge-danger" style="padding:2px 6px">L</span>`
          : `<span style="color:var(--muted)">—</span>`;
      const cells = cols.map(c => `<td>${c.render(g)}</td>`).join("");
      return `<tr><td>${d}</td><td>${g.game.map_name || "—"}</td><td>${result}</td>${cells}</tr>`;
    }).join("");

    wrap.innerHTML = `
      <div style="overflow-x:auto">
        <table class="stats-table">
          <thead><tr><th>Date</th><th>Map</th><th>Result</th>${headerCells}</tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  } catch (e) {
    wrap.innerHTML = `<p class="empty-msg">Could not load stats.</p>`;
    toast(e.message, "error");
  }
}

function getActiveStatCols() {
  const all = [
    { col: "rating",   label: "Rating",      render: g => fmtRating(g.leetify_rating) },
    { col: "kd",       label: "K/D",         render: g => (parseFloat(g.kd_ratio)||0).toFixed(2) },
    { col: "adr",      label: "ADR",         render: g => (parseFloat(g.adr)||0).toFixed(1) },
    { col: "hs",       label: "HS%",         render: g => `${(parseFloat(g.headshot_pct)||0).toFixed(1)}%` },
    { col: "kills",    label: "Kills",       render: g => g.kills },
    { col: "deaths",   label: "Deaths",      render: g => g.deaths },
    { col: "assists",  label: "Assists",     render: g => g.assists },
    { col: "utility",  label: "Utility DMG", render: g => (parseFloat(g.utility_damage)||0).toFixed(0) },
    { col: "opening",  label: "Opening K",   render: g => g.opening_kills },
  ];
  const active = new Set(
    Array.from(document.querySelectorAll(".ps-stat-toggle:checked")).map(cb => cb.dataset.col)
  );
  return all.filter(c => active.has(c.col));
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
// Records Tab                                                         //
// ------------------------------------------------------------------ //

async function loadRecords() {
  try {
    const [records, players] = await Promise.all([
      api("GET", "/api/stats/records"),
      api("GET", "/api/players"),
    ]);

    // ---- Best-performance highlight cards ----
    const grid = document.getElementById("records-grid");
    const entries = Object.values(records);
    if (!entries.length) {
      grid.innerHTML = `<p class="empty-msg">No data yet. Add players and sync.</p>`;
    } else {
      grid.innerHTML = entries.map(r => {
        const avatar = r.avatar_url
          ? `<img src="${r.avatar_url}" alt="" style="width:32px;height:32px;border-radius:50%;vertical-align:middle;margin-right:8px;" onerror="this.style.display='none'">`
          : "";
        const date = r.played_at ? new Date(r.played_at).toLocaleDateString() : "";
        return `
          <div class="summary-card" style="cursor:pointer" onclick="showPlayerDetail('${r.steam_id}')">
            <div class="summary-label">🏆 ${r.label}</div>
            <div class="summary-value">${r.value}</div>
            <div style="margin-top:8px;font-size:12px">${avatar}<span style="font-weight:600">${r.username}</span></div>
            <div style="margin-top:4px;color:var(--muted);font-size:11px">${r.map_name}${date ? " · " + date : ""}</div>
          </div>`;
      }).join("");
    }

    // ---- Player selector for detailed game history ----
    const sel = document.getElementById("records-player-select");
    sel.innerHTML = `<option value="">— Select a player —</option>` +
      players.map(p => `<option value="${p.steam_id}">${p.username}</option>`).join("");

    document.getElementById("records-player-detail").innerHTML = "";

  } catch (e) {
    toast(e.message, "error");
  }
}

document.getElementById("records-player-select").addEventListener("change", async function () {
  const steamId = this.value;
  if (!steamId) {
    document.getElementById("records-player-detail").innerHTML = "";
    return;
  }
  await showPlayerDetail(steamId);
});

async function showPlayerDetail(steamId) {
  const wrap = document.getElementById("records-player-detail");
  wrap.innerHTML = `<p class="muted" style="text-align:center;padding:20px">Loading…</p>`;

  // Update the selector if called from a card click
  const sel = document.getElementById("records-player-select");
  if (sel && sel.value !== steamId) sel.value = steamId;

  try {
    const data = await api("GET", `/api/stats/${steamId}`);
    const p = data.player;
    const s = data.stats;
    const games = data.games;

    const avatar = p.avatar_url
      ? `<img src="${p.avatar_url}" alt="" style="width:48px;height:48px;border-radius:50%;vertical-align:middle;margin-right:12px;" onerror="this.style.display='none'">`
      : "";

    const gameRows = (games || []).map(g => {
      const d = g.game.played_at ? new Date(g.game.played_at).toLocaleDateString() : "—";
      const result = g.won === true
        ? `<span class="badge-ok" style="padding:2px 6px">W</span>`
        : g.won === false
          ? `<span class="badge-danger" style="padding:2px 6px">L</span>`
          : `<span style="color:var(--muted)">—</span>`;
      return `
        <tr>
          <td>${d}</td>
          <td>${g.game.map_name || "—"}</td>
          <td>${result}</td>
          <td>${g.kills}</td>
          <td>${g.deaths}</td>
          <td>${g.assists}</td>
          <td>${fmtRating(g.leetify_rating)}</td>
          <td>${(parseFloat(g.adr) || 0).toFixed(1)}</td>
          <td>${(parseFloat(g.headshot_pct) || 0).toFixed(1)}%</td>
        </tr>`;
    }).join("");

    wrap.innerHTML = `
      <div class="card">
        <div style="display:flex;align-items:center;margin-bottom:16px">
          ${avatar}
          <div>
            <div style="font-size:17px;font-weight:700">${p.username}</div>
            <div class="muted" style="font-size:11px">${p.steam_id}</div>
          </div>
        </div>
        <div class="summary-grid" style="margin-bottom:16px">
          <div class="summary-card"><div class="summary-label">Games</div><div class="summary-value">${s.games}</div></div>
          <div class="summary-card"><div class="summary-label">Avg Rating</div><div class="summary-value">${(s.avg_leetify_rating||0).toFixed(2)}</div></div>
          <div class="summary-card"><div class="summary-label">Avg ADR</div><div class="summary-value">${(s.avg_adr||0).toFixed(1)}</div></div>
          <div class="summary-card"><div class="summary-label">Avg HS%</div><div class="summary-value">${(s.avg_hs_pct||0).toFixed(1)}%</div></div>
          <div class="summary-card"><div class="summary-label">K/D</div><div class="summary-value">${(s.avg_kd||0).toFixed(2)}</div></div>
          <div class="summary-card"><div class="summary-label">Total Kills</div><div class="summary-value">${s.total_kills}</div></div>
        </div>
        ${games && games.length ? `
        <div style="overflow-x:auto">
          <table class="stats-table">
            <thead><tr>
              <th>Date</th><th>Map</th><th>Result</th><th>K</th><th>D</th><th>A</th>
              <th>Rating</th><th>ADR</th><th>HS%</th>
            </tr></thead>
            <tbody>${gameRows}</tbody>
          </table>
        </div>` : `<p class="empty-msg">No game history yet.</p>`}
      </div>`;
  } catch (e) {
    wrap.innerHTML = `<p class="empty-msg">Could not load player data.</p>`;
    toast(e.message, "error");
  }
}

// Event delegation: clicking a player name in any stats table opens their detail
document.addEventListener("click", e => {
  const el = e.target.closest(".player-link");
  if (!el) return;
  const steamId = el.dataset.steamid;
  if (!steamId) return;
  // Switch to Records tab and show detail
  document.querySelectorAll(".nav-btn").forEach(b => b.classList.remove("active"));
  document.querySelectorAll(".tab-content").forEach(s => { s.classList.add("hidden"); s.classList.remove("active"); });
  const recordsBtn = document.querySelector('.nav-btn[data-tab="records"]');
  recordsBtn.classList.add("active");
  const tab = document.getElementById("tab-records");
  tab.classList.remove("hidden");
  tab.classList.add("active");
  loadRecords().then(() => showPlayerDetail(steamId));
});



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
  // Populate player list for selection
  try {
    const players = await api("GET", "/api/players");
    const sel = document.getElementById("analysis-players");
    sel.innerHTML = players.map(p =>
      `<option value="${p.steam_id}">${p.username}</option>`
    ).join("");
  } catch {}

  try {
    const analyses = await api("GET", "/api/analysis");
    const container = document.getElementById("past-analyses");
    if (!analyses.length) {
      container.innerHTML = `<p class="empty-msg">No past analyses yet.</p>`;
      return;
    }
    container.innerHTML = analyses.map(a => {
      const div = document.createElement("div");
      div.className = "card analysis-card";
      const textDiv = document.createElement("div");
      textDiv.textContent = a.analysis || "";
      const meta = document.createElement("p");
      meta.className = "muted";
      meta.style.marginTop = "12px";
      meta.textContent = `${new Date(a.created_at).toLocaleString()} · ${a.scope} · ${a.model_used}`;
      div.appendChild(textDiv);
      div.appendChild(meta);
      return div.outerHTML;
    }).join("");
  } catch (e) {
    toast(e.message, "error");
  }
}

document.getElementById("btn-analyse").addEventListener("click", async () => {
  const scope = document.getElementById("analysis-scope").value;
  const sel = document.getElementById("analysis-players");
  const selected = Array.from(sel.selectedOptions).map(o => o.value).slice(0, 5);
  const btn = document.getElementById("btn-analyse");
  btn.disabled = true;
  btn.textContent = "Generating…";
  try {
    const body = { scope };
    if (selected.length > 0) body.player_ids = selected;
    const result = await api("POST", "/api/analysis", body);
    const resDiv = document.getElementById("analysis-result");
    resDiv.classList.remove("hidden");
    document.getElementById("analysis-text").textContent = result.analysis || "";
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
// Win Stats Tab                                                        //
// ------------------------------------------------------------------ //

async function loadWinStats() {
  try {
    const players = await api("GET", "/api/stats/monthly");
    const summaryEl = document.getElementById("win-stats-summary");
    const tableWrap = document.getElementById("win-stats-table-wrap");

    const active = players.filter(p => p.games > 0);
    const totalWins  = active.reduce((s, p) => s + (p.wins  || 0), 0);
    const totalLoss  = active.reduce((s, p) => s + (p.losses || 0), 0);
    const totalGames = totalWins + totalLoss;
    const topWinner  = active.slice().sort((a, b) => (b.wins || 0) - (a.wins || 0))[0];
    const topWinRate = active.filter(p => (p.wins || 0) + (p.losses || 0) > 0)
                             .sort((a, b) => b.win_rate - a.win_rate)[0];

    summaryEl.innerHTML = `
      <div class="summary-card">
        <div class="summary-label">Total Wins (group)</div>
        <div class="summary-value" style="color:var(--green)">${totalWins}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Total Losses (group)</div>
        <div class="summary-value" style="color:var(--red)">${totalLoss}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Group Win Rate</div>
        <div class="summary-value">${totalGames > 0 ? ((totalWins / totalGames) * 100).toFixed(1) + "%" : "—"}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Most Wins</div>
        <div class="summary-value">${topWinner ? topWinner.username : "—"}</div>
      </div>
      <div class="summary-card">
        <div class="summary-label">Best Win Rate</div>
        <div class="summary-value">${topWinRate ? topWinRate.username + " (" + topWinRate.win_rate.toFixed(1) + "%)" : "—"}</div>
      </div>`;

    // Sort by win rate descending, then by wins
    const sorted = active.slice().sort((a, b) => {
      const aGames = (a.wins || 0) + (a.losses || 0);
      const bGames = (b.wins || 0) + (b.losses || 0);
      if (bGames === 0 && aGames === 0) return 0;
      if (bGames === 0) return -1;
      if (aGames === 0) return 1;
      return b.win_rate - a.win_rate;
    });

    if (!sorted.length) {
      tableWrap.innerHTML = `<p class="empty-msg">No data yet. Add players and sync.</p>`;
    } else {
      const rows = sorted.map((p, i) => {
        const avatar = p.avatar_url
          ? `<img class="avatar" src="${p.avatar_url}" alt="" onerror="this.style.display='none'">`
          : `<span class="avatar" style="background:#30363d;display:inline-block;"></span>`;
        const gwr = (p.wins || 0) + (p.losses || 0);
        const wrBar = gwr > 0
          ? `<div style="display:inline-block;width:80px;height:8px;background:var(--border);border-radius:4px;vertical-align:middle;margin-left:8px"><div style="width:${p.win_rate}%;height:100%;background:var(--green);border-radius:4px"></div></div>`
          : "";
        return `
          <tr>
            <td class="rank">#${i + 1}</td>
            <td><div class="player-cell">${avatar}<span class="username player-link" data-steamid="${p.steam_id}" style="cursor:pointer;text-decoration:underline dotted">${p.username}</span></div></td>
            <td>${p.games}</td>
            <td style="color:var(--green);font-weight:600">${p.wins || 0}</td>
            <td style="color:var(--red);font-weight:600">${p.losses || 0}</td>
            <td>${gwr > 0 ? p.win_rate.toFixed(1) + "%" + wrBar : "—"}</td>
            <td>${fmtRating(p.avg_leetify_rating)}</td>
            <td>${(parseFloat(p.avg_kd) || 0).toFixed(2)}</td>
          </tr>`;
      }).join("");
      tableWrap.innerHTML = `
        <div style="overflow-x:auto">
          <table class="stats-table">
            <thead><tr>
              <th></th><th>Player</th><th>Games</th>
              <th>Wins</th><th>Losses</th><th>Win Rate</th>
              <th>Rating</th><th>K/D</th>
            </tr></thead>
            <tbody>${rows}</tbody>
          </table>
        </div>`;
    }

    // Populate player selector for match history
    const sel = document.getElementById("win-stats-player-select");
    sel.innerHTML = `<option value="">— Select a player —</option>` +
      players.map(p => `<option value="${p.steam_id}">${p.username}</option>`).join("");
  } catch (e) {
    toast(e.message, "error");
  }
}

document.getElementById("win-stats-player-select").addEventListener("change", async function () {
  const steamId = this.value;
  const wrap = document.getElementById("win-stats-match-wrap");
  if (!steamId) {
    wrap.innerHTML = `<p class="empty-msg">Select a player to view their match history.</p>`;
    return;
  }
  wrap.innerHTML = `<p class="muted" style="text-align:center;padding:20px">Loading…</p>`;
  try {
    const data = await api("GET", `/api/stats/${steamId}`);
    const games = data.games || [];
    if (!games.length) {
      wrap.innerHTML = `<p class="empty-msg">No game history yet.</p>`;
      return;
    }
    const rows = games.map(g => {
      const d = g.game.played_at ? new Date(g.game.played_at).toLocaleDateString() : "—";
      const result = g.won === true
        ? `<span class="badge-ok" style="padding:2px 8px">WIN</span>`
        : g.won === false
          ? `<span class="badge-danger" style="padding:2px 8px">LOSS</span>`
          : `<span style="color:var(--muted)">—</span>`;
      const score = g.game.score_ct !== undefined
        ? `${g.game.score_ct} – ${g.game.score_t}`
        : "—";
      return `
        <tr>
          <td>${d}</td>
          <td>${g.game.map_name || "—"}</td>
          <td>${result}</td>
          <td>${score}</td>
          <td>${g.kills}</td>
          <td>${g.deaths}</td>
          <td>${g.assists}</td>
          <td>${fmtRating(g.leetify_rating)}</td>
          <td>${(parseFloat(g.adr) || 0).toFixed(1)}</td>
          <td>${(parseFloat(g.headshot_pct) || 0).toFixed(1)}%</td>
        </tr>`;
    }).join("");
    wrap.innerHTML = `
      <div style="overflow-x:auto">
        <table class="stats-table">
          <thead><tr>
            <th>Date</th><th>Map</th><th>Result</th><th>Score</th>
            <th>K</th><th>D</th><th>A</th><th>Rating</th><th>ADR</th><th>HS%</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>`;
  } catch (e) {
    wrap.innerHTML = `<p class="empty-msg">Could not load match history.</p>`;
    toast(e.message, "error");
  }
});

// ------------------------------------------------------------------ //
// Initial load                                                         //
// ------------------------------------------------------------------ //

loadHome();
