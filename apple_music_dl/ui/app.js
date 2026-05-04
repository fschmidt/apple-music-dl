const $ = (id) => document.getElementById(id);
const log = (msg, cls = "") => {
  const line = document.createElement("div");
  if (cls) line.className = cls;
  line.textContent = msg;
  $("log").appendChild(line);
  $("log").scrollTop = $("log").scrollHeight;
};

async function refreshAuth() {
  const has = await window.pywebview.api.has_token();
  $("authState").textContent = has ? "Signed in" : "Not signed in";
  $("loginBtn").hidden = has;
  $("logoutBtn").hidden = !has;
  $("dlBtn").disabled = !has;
}

window.onLoggedIn = () => {
  log("Signed in.", "ok");
  refreshAuth();
};

window.onEvent = (evt) => {
  if (evt.type === "track") {
    if (evt.error) log(`✗ ${evt.title} — ${evt.error}`, "err");
    else if (evt.skipped) log(`• ${evt.title} (skipped — already exists or no file)`, "muted");
    else log(`✓ ${evt.title} → ${evt.path}`, "ok");
  } else if (evt.type === "done") {
    log("Finished.", "ok");
    $("dlBtn").disabled = false;
  } else if (evt.type === "error") {
    log(`Error: ${evt.message}`, "err");
    $("dlBtn").disabled = false;
  }
};

window.addEventListener("pywebviewready", () => {
  refreshAuth();

  $("loginBtn").addEventListener("click", () => {
    window.pywebview.api.login();
  });
  $("logoutBtn").addEventListener("click", async () => {
    await window.pywebview.api.logout();
    refreshAuth();
  });
  $("copyBtn").addEventListener("click", async () => {
    const text = $("log").innerText;
    try {
      await navigator.clipboard.writeText(text);
      $("copyBtn").textContent = "Copied!";
      setTimeout(() => ($("copyBtn").textContent = "Copy logs"), 1200);
    } catch (e) {
      const r = document.createRange();
      r.selectNodeContents($("log"));
      const sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(r);
    }
  });
  $("clearBtn").addEventListener("click", () => { $("log").innerHTML = ""; });

  $("dlBtn").addEventListener("click", () => {
    const url = $("url").value.trim();
    if (!url) return;
    $("dlBtn").disabled = true;
    log(`→ ${url}`);
    window.pywebview.api.download(url, $("mp3").checked);
  });
});
