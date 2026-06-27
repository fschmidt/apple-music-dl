const $ = (id) => document.getElementById(id);

const log = (msg, cls = "") => {
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = msg;
  $("log").appendChild(line);
  $("log").scrollTop = $("log").scrollHeight;
};

let signedIn = false;
let queueCounter = 0;
const items = {}; // id -> { el, statusEl, tracksEl }

// --- auth ------------------------------------------------------------------

async function refreshAuth() {
  signedIn = await window.pywebview.api.has_token();
  $("authState").textContent = signedIn ? "Signed in" : "Not signed in";
  $("loginBtn").hidden = signedIn;
  $("logoutBtn").hidden = !signedIn;
  $("searchBtn").disabled = !signedIn;
  $("addUrlBtn").disabled = !signedIn;
}

window.onLoggedIn = () => {
  log("Signed in.", "ok");
  refreshAuth();
};

// --- search ----------------------------------------------------------------

function escapeAttr(s) {
  return (s || "").replace(/"/g, "&quot;");
}

async function runSearch() {
  const term = $("search").value.trim();
  if (!term || !signedIn) return;
  $("searchBtn").disabled = true;
  $("searchBtn").textContent = "…";
  $("results").innerHTML = "";
  try {
    const resp = await window.pywebview.api.search(term);
    if (resp.error) {
      log(`Search error: ${resp.error}`, "err");
      return;
    }
    renderResults(resp.results || []);
    if (!resp.results.length) log(`No results for “${term}”.`, "muted");
  } catch (e) {
    log(`Search error: ${e}`, "err");
  } finally {
    $("searchBtn").disabled = !signedIn;
    $("searchBtn").textContent = "Search";
  }
}

function renderResults(results) {
  const box = $("results");
  box.innerHTML = "";
  for (const r of results) {
    const row = document.createElement("div");
    row.className = "res";
    const art = r.artwork_url
      ? `<img src="${escapeAttr(r.artwork_url)}" alt="">`
      : `<img alt="">`;
    const sub = [r.artist, r.subtitle].filter(Boolean).join(" — ");
    row.innerHTML = `
      ${art}
      <span class="badge ${r.kind}">${r.kind}</span>
      <div class="meta">
        <div class="title">${escapeHtml(r.title)}</div>
        <div class="sub">${escapeHtml(sub)}</div>
      </div>
      <button class="small">Add</button>`;
    const title = r.kind === "album" ? r.title : `${r.title} — ${r.artist}`;
    row.querySelector("button").addEventListener("click", () => {
      addToQueue(r.url, title);
    });
    box.appendChild(row);
  }
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s || "";
  return d.innerHTML;
}

// --- queue -----------------------------------------------------------------

function addToQueue(url, title) {
  if (!url || !signedIn) return;
  const id = `q${++queueCounter}`;
  const mp3 = $("mp3").checked;

  const el = document.createElement("div");
  el.className = "qitem";
  el.innerHTML = `
    <div class="qhead">
      <span class="qtitle"></span>
      <span class="qstatus">Queued</span>
    </div>
    <div class="qtracks"></div>`;
  el.querySelector(".qtitle").textContent = title;
  $("queue").appendChild(el);

  items[id] = {
    el,
    statusEl: el.querySelector(".qstatus"),
    tracksEl: el.querySelector(".qtracks"),
  };

  window.pywebview.api.enqueue({ id, url, title, mp3 });
  log(`Queued: ${title}`);
}

function setStatus(id, text, cls) {
  const it = items[id];
  if (!it) return;
  it.statusEl.textContent = text;
  it.statusEl.className = "qstatus" + (cls ? " " + cls : "");
}

function addTrackLine(id, text, cls) {
  const it = items[id];
  if (!it) return;
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = text;
  it.tracksEl.appendChild(line);
  it.tracksEl.scrollTop = it.tracksEl.scrollHeight;
}

window.onEvent = (evt) => {
  const id = evt.id;
  switch (evt.type) {
    case "queued":
      break;
    case "item-start":
      setStatus(id, "Downloading…", "downloading");
      break;
    case "track":
      if (evt.error) {
        addTrackLine(id, `✗ ${evt.title} — ${evt.error}`, "err");
      } else if (evt.skipped) {
        addTrackLine(id, `• ${evt.title} (skipped)`, "muted");
      } else {
        addTrackLine(id, `✓ ${evt.title}`);
      }
      break;
    case "item-done": {
      const parts = [`${evt.ok} downloaded`];
      if (evt.skipped) parts.push(`${evt.skipped} skipped`);
      if (evt.failed) parts.push(`${evt.failed} failed`);
      setStatus(id, parts.join(", "), evt.failed ? "error" : "done");
      break;
    }
    case "item-error":
      setStatus(id, `Error`, "error");
      addTrackLine(id, evt.message, "err");
      log(`Error: ${evt.message}`, "err");
      break;
  }
};

// --- wiring ----------------------------------------------------------------

window.addEventListener("pywebviewready", () => {
  refreshAuth();

  $("loginBtn").addEventListener("click", () => window.pywebview.api.login());
  $("logoutBtn").addEventListener("click", async () => {
    await window.pywebview.api.logout();
    refreshAuth();
  });

  $("searchBtn").addEventListener("click", runSearch);
  $("search").addEventListener("keydown", (e) => {
    if (e.key === "Enter") runSearch();
  });

  $("addUrlBtn").addEventListener("click", () => {
    const url = $("url").value.trim();
    if (!url) return;
    addToQueue(url, url);
    $("url").value = "";
  });
  $("url").addEventListener("keydown", (e) => {
    if (e.key === "Enter") $("addUrlBtn").click();
  });

  $("copyBtn").addEventListener("click", async () => {
    const text = $("log").innerText;
    try {
      await navigator.clipboard.writeText(text);
      $("copyBtn").textContent = "Copied!";
      setTimeout(() => ($("copyBtn").textContent = "Copy"), 1200);
    } catch (e) {
      const r = document.createRange();
      r.selectNodeContents($("log"));
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
    }
  });
  $("clearBtn").addEventListener("click", () => ($("log").innerHTML = ""));
});
