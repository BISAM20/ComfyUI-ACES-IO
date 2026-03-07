/**
 * ACES IO — Colorspace / Display / View pickers
 *
 * Registers three custom widget types via ComfyUI's getCustomWidgets API:
 *   ACES_COLORSPACE  — Nuke-style family-tabbed colorspace picker
 *   ACES_DISPLAY     — display device picker
 *   ACES_VIEW        — view/output-transform picker
 *
 * Each widget renders as a text box + "⬡ Browse" button that opens a
 * full-screen modal dialog organised exactly like Nuke's color menus
 * (families as top-level tabs, sub-families as sub-tabs, live search).
 */

import { app } from "/scripts/app.js";

// ─────────────────────────────────────────────────────────────────────────────
//  Data cache  (loaded once from the server, then kept in memory)
// ─────────────────────────────────────────────────────────────────────────────

const _cache = { cs: null, disp: {} };

async function _loadCS() {
    if (_cache.cs) return _cache.cs;
    try {
        const r = await fetch("/aces_io/all_colorspaces");
        _cache.cs = await r.json();
    } catch (e) {
        console.warn("[ACES IO] Could not load colorspace data:", e);
        _cache.cs = { config_names: [], by_config: {} };
    }
    return _cache.cs;
}

async function _loadDisp(preset) {
    if (_cache.disp[preset]) return _cache.disp[preset];
    try {
        const r = await fetch("/aces_io/displays_views?preset=" + encodeURIComponent(preset));
        _cache.disp[preset] = await r.json();
    } catch (e) {
        _cache.disp[preset] = { displays: {} };
    }
    return _cache.disp[preset];
}

// ─────────────────────────────────────────────────────────────────────────────
//  CSS — injected once into <head>
// ─────────────────────────────────────────────────────────────────────────────

function _injectCSS() {
    if (document.getElementById("aces-io-css")) return;
    const s = document.createElement("style");
    s.id = "aces-io-css";
    s.textContent = `
.aces-overlay{position:fixed;inset:0;background:rgba(0,0,0,.7);z-index:99999;
  display:flex;align-items:center;justify-content:center}
.aces-dialog{background:#1c1c1c;border:1px solid #555;border-radius:8px;
  width:560px;max-height:82vh;display:flex;flex-direction:column;
  box-shadow:0 16px 48px rgba(0,0,0,.95);font:13px/1.4 "Segoe UI",Arial,sans-serif;color:#ddd;overflow:hidden}
.aces-hdr{display:flex;align-items:center;gap:8px;padding:10px 14px;
  background:#252525;border-bottom:1px solid #444}
.aces-hdr-title{font-weight:600;font-size:13px;flex:1;color:#eee}
.aces-cfg-sel{background:#333;border:1px solid #555;border-radius:4px;
  color:#ddd;font-size:12px;padding:3px 6px;cursor:pointer;max-width:230px}
.aces-close{background:none;border:none;color:#888;font-size:18px;cursor:pointer;padding:0 4px;line-height:1}
.aces-close:hover{color:#fff}
.aces-search-wrap{position:relative;padding:8px 12px;background:#1e1e1e}
.aces-search{width:100%;box-sizing:border-box;background:#2a2a2a;border:1px solid #555;
  border-radius:5px;color:#ddd;font-size:13px;padding:6px 10px 6px 30px;outline:none}
.aces-search:focus{border-color:#5588bb}
.aces-search-icon{position:absolute;left:22px;top:50%;transform:translateY(-50%);
  color:#666;font-size:14px;pointer-events:none}
.aces-tabs{display:flex;flex-wrap:wrap;gap:2px;padding:6px 10px 0;
  background:#1e1e1e;border-bottom:1px solid #2e2e2e}
.aces-tab{background:#252525;border:1px solid #3e3e3e;border-bottom:none;
  border-radius:4px 4px 0 0;color:#999;font-size:12px;padding:4px 12px;
  cursor:pointer;user-select:none;transition:background .12s,color .12s}
.aces-tab:hover{background:#333;color:#ddd}
.aces-tab.active{background:#2e2e2e;color:#fff;border-color:#5588bb}
.aces-subtabs{display:flex;flex-wrap:wrap;gap:2px;padding:5px 10px;
  background:#1e1e1e;border-bottom:1px solid #252525}
.aces-stab{background:#252525;border:1px solid #333;border-radius:3px;
  color:#888;font-size:11px;padding:2px 9px;cursor:pointer;user-select:none}
.aces-stab:hover{background:#2e2e2e;color:#bbb}
.aces-stab.active{background:#1e3050;color:#7ec0f5;border-color:#3a6090}
.aces-list{flex:1;overflow-y:auto;padding:4px 0;background:#1a1a1a}
.aces-list::-webkit-scrollbar{width:6px}
.aces-list::-webkit-scrollbar-track{background:#111}
.aces-list::-webkit-scrollbar-thumb{background:#3e3e3e;border-radius:3px}
.aces-item{padding:5px 16px;cursor:pointer;display:flex;align-items:center;
  gap:6px;border-left:3px solid transparent;transition:background .08s}
.aces-item:hover{background:#253040}
.aces-item.cur{background:#1a2e4a;border-left-color:#4e96d8;color:#7ec8ff}
.aces-chk{font-size:11px;width:12px;flex-shrink:0}
.aces-nm{flex:1}
.aces-fam{color:#484848;font-size:11px}
.aces-foot{padding:4px 16px 6px;font-size:11px;color:#444;border-top:1px solid #222}
.aces-empty{padding:28px;text-align:center;color:#444;font-style:italic}
/* ── widget button ── */
.aces-btn{display:inline-flex;align-items:center;justify-content:center;
  background:#2a2a2a;border:1px solid #555;border-radius:4px;color:#ccc;
  font-size:11px;padding:1px 6px;cursor:pointer;height:20px;white-space:nowrap}
.aces-btn:hover{background:#383838;color:#fff}
/* ── path browser ── */
.aces-path-bar{display:flex;flex-wrap:wrap;align-items:center;gap:1px;
  padding:5px 12px;background:#1c1c1c;border-bottom:1px solid #2a2a2a;font-size:12px}
.aces-path-part{color:#7ec0f5;cursor:pointer;padding:1px 3px;border-radius:3px}
.aces-path-part:hover{background:#1e3050;text-decoration:underline}
.aces-path-sep{color:#555;padding:0 1px}
.aces-path-foot{padding:6px 14px;background:#1c1c1c;border-top:1px solid #2a2a2a;
  font-size:11px;color:#666;display:flex;align-items:center;gap:10px;min-height:32px}
.aces-select-btn{background:#1e3050;border:1px solid #3a6090;border-radius:4px;
  color:#7ec0f5;font-size:12px;padding:4px 12px;cursor:pointer;white-space:nowrap}
.aces-select-btn:hover{background:#253a60;color:#aad4ff}
.aces-select-btn:disabled{opacity:.4;cursor:default}
`;
    document.head.appendChild(s);
}

// ─────────────────────────────────────────────────────────────────────────────
//  Colorspace picker dialog
// ─────────────────────────────────────────────────────────────────────────────

function openColorspacePicker(currentVal, onSelect, initialPreset) {
    _injectCSS();
    _loadCS().then(data => _showCSDialog(data, currentVal, onSelect, initialPreset));
}

function _showCSDialog(data, currentVal, onSelect, initialPreset) {
    const presets    = data.config_names ?? [];
    let activePreset = initialPreset ?? presets[0] ?? "ACES 2.0 CG  [Recommended]";
    let activeTab    = "All";
    let activeSub    = "All";
    let searchQ      = "";

    const overlay = _el("div", "aces-overlay");
    const dlg     = _el("div", "aces-dialog");
    overlay.appendChild(dlg);
    document.body.appendChild(overlay);

    // header
    const hdr  = _el("div", "aces-hdr");
    const ttl  = _el("span", "aces-hdr-title", "ACES IO — Colorspace Picker");
    const sel  = document.createElement("select");
    sel.className = "aces-cfg-sel";
    presets.forEach(p => { const o = _el("option"); o.value = o.textContent = p; if (p === activePreset) o.selected = true; sel.appendChild(o); });
    const cls  = _el("button", "aces-close", "✕");
    hdr.append(ttl, sel, cls);

    // search
    const sw   = _el("div", "aces-search-wrap");
    const si   = _el("span", "aces-search-icon", "🔍");
    const inp  = document.createElement("input");
    inp.className = "aces-search"; inp.placeholder = "Search colorspaces…";
    sw.append(si, inp);

    // tab bars
    const tabs = _el("div", "aces-tabs");
    const subs = _el("div", "aces-subtabs");
    subs.style.display = "none";

    // list
    const lst  = _el("div", "aces-list");
    const foot = _el("div", "aces-foot");

    dlg.append(hdr, sw, tabs, subs, lst, foot);

    // ── helpers ──────────────────────────────────────────────────────────────

    function fams() { return data.by_config?.[activePreset]?.families ?? {}; }

    function topFams() {
        const tops = new Set(["All"]);
        Object.keys(fams()).forEach(k => tops.add(k.split("/")[0]));
        return Array.from(tops);
    }

    function subFams(top) {
        if (top === "All") return [];
        const sset = new Set();
        Object.keys(fams()).forEach(k => {
            if (k === top) sset.add("—");
            else if (k.startsWith(top + "/")) sset.add(k.slice(top.length + 1));
        });
        return sset.size > 1 ? ["All", ...Array.from(sset).sort()] : [];
    }

    function items() {
        const f = fams(); let out = [];
        for (const [fam, names] of Object.entries(f)) {
            const top = fam.split("/")[0];
            if (activeTab !== "All" && top !== activeTab) continue;
            if (activeTab !== "All" && activeSub !== "All") {
                const sub = fam.includes("/") ? fam.slice(fam.indexOf("/") + 1) : "—";
                if (sub !== activeSub) continue;
            }
            names.forEach(n => out.push({ name: n, fam }));
        }
        if (searchQ) { const q = searchQ.toLowerCase(); out = out.filter(i => i.name.toLowerCase().includes(q)); }
        return out;
    }

    // ── render ────────────────────────────────────────────────────────────────

    function renderTabs() {
        tabs.innerHTML = "";
        topFams().forEach(t => {
            const b = _el("div", "aces-tab" + (t === activeTab ? " active" : ""), t);
            b.onclick = () => { activeTab = t; activeSub = "All"; render(); };
            tabs.appendChild(b);
        });
    }

    function renderSubs() {
        const sf = subFams(activeTab);
        subs.style.display = sf.length ? "flex" : "none";
        subs.innerHTML = "";
        sf.forEach(s => {
            const b = _el("div", "aces-stab" + (s === activeSub ? " active" : ""), s === "—" ? "(direct)" : s);
            b.onclick = () => { activeSub = s; render(); };
            subs.appendChild(b);
        });
    }

    function renderList() {
        lst.innerHTML = "";
        const its = items();
        if (!its.length) { lst.appendChild(_el("div", "aces-empty", searchQ ? `No results for "${searchQ}"` : "No colorspaces")); foot.textContent = ""; return; }
        its.forEach(({ name, fam }) => {
            const row  = _el("div", "aces-item" + (name === currentVal ? " cur" : ""));
            const chk  = _el("span", "aces-chk", name === currentVal ? "✓" : "");
            const nm   = _el("span", "aces-nm");
            const fmsp = _el("span", "aces-fam", activeTab === "All" ? fam : "");
            if (searchQ) {
                const q = searchQ.toLowerCase(), idx = name.toLowerCase().indexOf(q);
                nm.innerHTML = idx >= 0
                    ? _esc(name.slice(0, idx)) + `<mark style="background:#3a6090;color:#fff;border-radius:2px">${_esc(name.slice(idx, idx + searchQ.length))}</mark>` + _esc(name.slice(idx + searchQ.length))
                    : _esc(name);
            } else { nm.textContent = name; }
            row.append(chk, nm, fmsp);
            row.onclick = () => { onSelect(name); document.body.removeChild(overlay); };
            lst.appendChild(row);
        });
        foot.textContent = `${its.length} colorspace${its.length !== 1 ? "s" : ""}`;
    }

    function render() { renderTabs(); renderSubs(); renderList(); }

    // ── events ───────────────────────────────────────────────────────────────

    sel.onchange = () => { activePreset = sel.value; activeTab = "All"; activeSub = "All"; inp.value = ""; searchQ = ""; render(); };
    inp.oninput  = () => { searchQ = inp.value.trim(); if (searchQ) { activeTab = "All"; subs.style.display = "none"; } render(); };
    cls.onclick  = () => document.body.removeChild(overlay);
    overlay.onclick = e => { if (e.target === overlay) document.body.removeChild(overlay); };
    document.addEventListener("keydown", function onEsc(e) {
        if (e.key === "Escape") { document.body.removeChild(overlay); document.removeEventListener("keydown", onEsc); }
    });

    render();
    requestAnimationFrame(() => inp.focus());
}

// ─────────────────────────────────────────────────────────────────────────────
//  Display / View pickers (simpler single-column dialogs)
// ─────────────────────────────────────────────────────────────────────────────

function openDisplayPicker(currentVal, onSelect, preset) {
    _injectCSS();
    _loadDisp(preset || "ACES 2.0 CG  [Recommended]").then(data => {
        _showSimplePicker("ACES IO — Display Picker", Object.keys(data.displays ?? {}), currentVal, onSelect);
    });
}

function openViewPicker(currentVal, onSelect, preset, displayVal) {
    _injectCSS();
    _loadDisp(preset || "ACES 2.0 CG  [Recommended]").then(data => {
        let views;
        if (displayVal && data.displays?.[displayVal]) {
            views = data.displays[displayVal];
        } else {
            const seen = new Set(), all = [];
            Object.values(data.displays ?? {}).forEach(vs => vs.forEach(v => { if (!seen.has(v)) { seen.add(v); all.push(v); } }));
            views = all;
        }
        _showSimplePicker("ACES IO — View Picker", views, currentVal, onSelect);
    });
}

function _showSimplePicker(title, items, currentVal, onSelect) {
    const overlay = _el("div", "aces-overlay");
    const dlg     = _el("div", "aces-dialog"); dlg.style.width = "420px";
    overlay.appendChild(dlg);
    document.body.appendChild(overlay);

    const hdr = _el("div", "aces-hdr");
    const ttl = _el("span", "aces-hdr-title", title);
    const cls = _el("button", "aces-close", "✕");
    hdr.append(ttl, cls);

    const sw  = _el("div", "aces-search-wrap");
    const si  = _el("span", "aces-search-icon", "🔍");
    const inp = document.createElement("input");
    inp.className = "aces-search"; inp.placeholder = "Search…";
    sw.append(si, inp);

    const lst = _el("div", "aces-list");
    dlg.append(hdr, sw, lst);

    function render(q) {
        lst.innerHTML = "";
        const filtered = q ? items.filter(i => i.toLowerCase().includes(q.toLowerCase())) : items;
        filtered.forEach(name => {
            const row = _el("div", "aces-item" + (name === currentVal ? " cur" : ""));
            const chk = _el("span", "aces-chk", name === currentVal ? "✓" : "");
            const nm  = _el("span", "aces-nm", name);
            row.append(chk, nm);
            row.onclick = () => { onSelect(name); document.body.removeChild(overlay); };
            lst.appendChild(row);
        });
        if (!filtered.length) lst.appendChild(_el("div", "aces-empty", "No results"));
    }

    inp.oninput = () => render(inp.value.trim());
    cls.onclick = () => document.body.removeChild(overlay);
    overlay.onclick = e => { if (e.target === overlay) document.body.removeChild(overlay); };
    document.addEventListener("keydown", function onEsc(e) {
        if (e.key === "Escape") { document.body.removeChild(overlay); document.removeEventListener("keydown", onEsc); }
    });
    render(""); requestAnimationFrame(() => inp.focus());
}

// ─────────────────────────────────────────────────────────────────────────────
//  File / Directory browser dialog  (ACES_PATH widget)
// ─────────────────────────────────────────────────────────────────────────────

function openPathPicker(currentVal, onSelect, mode, filter) {
    _injectCSS();
    const startPath = currentVal
        ? (mode === "dir" ? currentVal : currentVal.split("/").slice(0, -1).join("/"))
        : "";
    _showPathDialog(startPath || "~", currentVal, onSelect, mode, filter);
}

async function _showPathDialog(startPath, currentVal, onSelect, mode, filter) {
    const overlay = _el("div", "aces-overlay");
    const dlg     = _el("div", "aces-dialog"); dlg.style.width = "520px";
    overlay.appendChild(dlg);
    document.body.appendChild(overlay);

    const hdr  = _el("div", "aces-hdr");
    const ttl  = _el("span", "aces-hdr-title",
        mode === "dir" ? "ACES IO — Select Directory" : "ACES IO — Select File");
    const cls  = _el("button", "aces-close", "✕");
    hdr.append(ttl, cls);

    // Path breadcrumb bar
    const pathBar = _el("div", "aces-path-bar");

    // Search
    const sw  = _el("div", "aces-search-wrap");
    const si  = _el("span", "aces-search-icon", "🔍");
    const inp = document.createElement("input");
    inp.className = "aces-search"; inp.placeholder = "Filter…";
    sw.append(si, inp);

    const lst    = _el("div", "aces-list");
    lst.style.minHeight = "240px";

    // Footer with confirm button (dir mode) or status
    const foot = _el("div", "aces-path-foot");

    dlg.append(hdr, pathBar, sw, lst, foot);

    let curPath = startPath;
    let allEntries = [];

    async function loadPath(p) {
        inp.value = "";
        lst.innerHTML = `<div class="aces-empty">Loading…</div>`;
        try {
            const url = "/aces_io/browse?path=" + encodeURIComponent(p)
                + "&mode=" + encodeURIComponent(mode)
                + (filter ? "&filter=" + encodeURIComponent(filter) : "");
            const r = await fetch(url);
            const data = await r.json();
            curPath = data.path;
            allEntries = [{ name: "..", type: "up", parent: data.parent }, ...data.entries];
            renderPath(curPath, data.parent);
            renderList("");
        } catch (e) {
            lst.innerHTML = `<div class="aces-empty">Error: ${e.message}</div>`;
        }
    }

    function renderPath(p, parent) {
        pathBar.innerHTML = "";
        const parts = p.split("/").filter(Boolean);
        // Home shortcut
        const homeBtn = _el("span", "aces-path-part", "~");
        homeBtn.onclick = () => loadPath("~");
        pathBar.appendChild(homeBtn);

        let built = "";
        parts.forEach((part, i) => {
            built += "/" + part;
            const sep = _el("span", "aces-path-sep", "/");
            const btn = _el("span", "aces-path-part", part);
            const snap = built;
            btn.onclick = () => loadPath(snap);
            pathBar.append(sep, btn);
        });

        // For dir mode, show "Select this folder" button
        foot.innerHTML = "";
        if (mode === "dir") {
            const selBtn = _el("button", "aces-select-btn", `Select: ${p.split("/").pop() || "/"}`);
            selBtn.onclick = () => { onSelect(p); document.body.removeChild(overlay); };
            foot.appendChild(selBtn);
        } else {
            foot.textContent = p;
        }
    }

    function renderList(q) {
        lst.innerHTML = "";
        const filtered = q
            ? allEntries.filter(e => e.name.toLowerCase().includes(q.toLowerCase()))
            : allEntries;

        if (!filtered.length) { lst.appendChild(_el("div", "aces-empty", "Empty directory")); return; }

        filtered.forEach(entry => {
            const row = _el("div", "aces-item" + (
                (mode === "file" && entry.type === "file" && curPath + "/" + entry.name === currentVal) ||
                (mode === "dir"  && entry.type === "dir"  && curPath + "/" + entry.name === currentVal) ? " cur" : ""
            ));
            const icon = _el("span", "aces-chk",
                entry.type === "up"   ? "↑" :
                entry.type === "dir"  ? "📁" : "📄");
            const nm   = _el("span", "aces-nm", entry.name === ".." ? ".. (up)" : entry.name);
            row.append(icon, nm);

            if (entry.type === "up") {
                row.onclick = () => loadPath(entry.parent);
            } else if (entry.type === "dir") {
                row.onclick = () => loadPath(curPath + "/" + entry.name);
                if (mode === "dir") {
                    // Double-click selects, single click navigates is not ideal
                    // So add a "Select" indicator on hover via a small button
                    const selSpan = _el("span", "aces-fam", "[click to open, dbl-click to select]");
                    row.appendChild(selSpan);
                    row.ondblclick = e => {
                        e.stopPropagation();
                        onSelect(curPath + "/" + entry.name);
                        document.body.removeChild(overlay);
                    };
                }
            } else {
                // file
                row.onclick = () => { onSelect(curPath + "/" + entry.name); document.body.removeChild(overlay); };
            }
            lst.appendChild(row);
        });
    }

    inp.oninput  = () => renderList(inp.value.trim());
    cls.onclick  = () => document.body.removeChild(overlay);
    overlay.onclick = e => { if (e.target === overlay) document.body.removeChild(overlay); };
    document.addEventListener("keydown", function onEsc(e) {
        if (e.key === "Escape") { document.body.removeChild(overlay); document.removeEventListener("keydown", onEsc); }
    });

    await loadPath(startPath);
}

// ─────────────────────────────────────────────────────────────────────────────
//  ACES 1.2 download dialog
// ─────────────────────────────────────────────────────────────────────────────

async function openAces12DownloadDialog() {
    _injectCSS();
    const overlay = _el("div", "aces-overlay");
    const dlg     = _el("div", "aces-dialog"); dlg.style.width = "420px";
    overlay.appendChild(dlg);
    document.body.appendChild(overlay);

    const hdr  = _el("div", "aces-hdr");
    const ttl  = _el("span", "aces-hdr-title", "Download ACES 1.2 Config");
    const cls  = _el("button", "aces-close", "✕");
    hdr.append(ttl, cls);

    const body = _el("div", "");
    body.style.cssText = "padding:16px 18px;display:flex;flex-direction:column;gap:12px";

    const info = _el("p", "");
    info.style.cssText = "color:#aaa;font-size:12px;margin:0;line-height:1.5";
    info.textContent = "This will download the ACES 1.2 OpenColorIO config (~130 MB) from the colour-science GitHub releases. The file will be saved into the ComfyUI-ACES-IO/configs/aces_1.2/ directory and is only needed once.";

    const barWrap = _el("div", "");
    barWrap.style.cssText = "background:#222;border-radius:4px;height:16px;overflow:hidden;display:none";
    const bar = _el("div", "");
    bar.style.cssText = "background:#4e96d8;height:100%;width:0%;transition:width .3s";
    barWrap.appendChild(bar);

    const status = _el("div", "");
    status.style.cssText = "font-size:12px;color:#888;text-align:center";

    const startBtn = _el("button", "aces-select-btn", "Download  (~130 MB)");
    startBtn.style.cssText = "align-self:center;padding:6px 20px;font-size:13px";

    body.append(info, barWrap, status, startBtn);
    dlg.append(hdr, body);

    cls.onclick     = () => document.body.removeChild(overlay);
    overlay.onclick = e => { if (e.target === overlay) document.body.removeChild(overlay); };

    let polling = null;

    function stopPolling() { if (polling) { clearInterval(polling); polling = null; } }

    async function pollStatus() {
        try {
            const r = await fetch("/aces_io/download_aces12_status");
            const d = await r.json();
            if (d.status === "done") {
                stopPolling();
                bar.style.width = "100%";
                status.textContent = "Download complete! Restart ComfyUI to activate ACES 1.2.";
                status.style.color = "#5a5";
                startBtn.disabled = true;
                startBtn.textContent = "Done";
            } else if (d.status === "error") {
                stopPolling();
                status.textContent = "Error: " + d.error;
                status.style.color = "#d55";
                startBtn.disabled = false;
                startBtn.textContent = "Retry";
            } else if (d.status === "downloading") {
                bar.style.width = Math.round((d.progress ?? 0) * 100) + "%";
                status.textContent = Math.round((d.progress ?? 0) * 100) + "% downloaded…";
            }
        } catch (e) {
            status.textContent = "Could not reach server.";
        }
    }

    startBtn.onclick = async () => {
        startBtn.disabled = true;
        startBtn.textContent = "Starting…";
        barWrap.style.display = "block";
        status.textContent = "Connecting…";
        try {
            const r = await fetch("/aces_io/download_aces12");
            const d = await r.json();
            if (d.status === "already_downloaded") {
                status.textContent = "ACES 1.2 is already downloaded!";
                status.style.color = "#5a5";
                bar.style.width = "100%";
            } else {
                polling = setInterval(pollStatus, 1000);
            }
        } catch (e) {
            status.textContent = "Failed to start: " + e.message;
            status.style.color = "#d55";
            startBtn.disabled = false;
            startBtn.textContent = "Retry";
        }
    };
}

// ─────────────────────────────────────────────────────────────────────────────
//  Widget factory helpers
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Returns the value of the `config_preset` widget on the same node,
 * defaulting to the first recommended config.
 */
function _nodePreset(node) {
    for (const w of (node.widgets ?? [])) {
        if (w.name === "config_preset") return w.value;
    }
    return "ACES 2.0 CG  [Recommended]";
}

/** Find the `display` widget on the same node (for view picker). */
function _nodeDisplay(node) {
    for (const w of (node.widgets ?? [])) {
        if (w.name === "display") return w;
    }
    return null;
}

/**
 * Creates a text widget (holds the value) + a button widget (opens picker).
 * The button uses {serialize: false} in addWidget options so ComfyUI's
 * frontend excludes it from widgets_values, preventing positional mismatches.
 */
function _makePickerWidget(node, inputName, defaultVal, pickerFn) {
    const tw = node.addWidget("text", inputName, defaultVal, () => {});
    tw.dynamicPrompts = false;

    // Pass {serialize: false} as the options arg — this is the correct ComfyUI
    // API to exclude the widget from widgets_values serialisation.
    node.addWidget("button", `Browse  ${inputName}`, null, () => {
        pickerFn(tw.value, val => {
            tw.value = val;
            app.graph.setDirtyCanvas(true, true);
        });
    }, { serialize: false });

    return tw;
}

// ─────────────────────────────────────────────────────────────────────────────
//  ComfyUI Extension
// ─────────────────────────────────────────────────────────────────────────────

app.registerExtension({
    name: "AcesIO.Pickers",

    async setup() {
        // Pre-fetch data in the background so the first picker opens instantly
        await _loadCS();
    },

    /**
     * getCustomWidgets is called by ComfyUI when it encounters a widget type
     * it doesn't recognise. Returning handlers here is the correct, official
     * way to define custom widget types in ComfyUI.
     */
    getCustomWidgets() {
        return {
            /** ── Colorspace picker ── */
            ACES_COLORSPACE(node, inputName, inputData /*, app */) {
                const def = inputData[1]?.default ?? "ACEScg";
                const tw  = _makePickerWidget(node, inputName, def, (curVal, onSel) => {
                    openColorspacePicker(curVal, onSel, _nodePreset(node));
                });
                return { widget: tw };
            },

            /** ── Display picker ── */
            ACES_DISPLAY(node, inputName, inputData /*, app */) {
                const def = inputData[1]?.default ?? "sRGB - Display";
                const tw  = _makePickerWidget(node, inputName, def, (curVal, onSel) => {
                    openDisplayPicker(curVal, onSel, _nodePreset(node));
                });
                return { widget: tw };
            },

            /** ── View picker ── */
            ACES_VIEW(node, inputName, inputData /*, app */) {
                const def = inputData[1]?.default ?? "ACES 2.0 - SDR 100 nits (Rec.709)";
                const tw  = _makePickerWidget(node, inputName, def, (curVal, onSel) => {
                    openViewPicker(curVal, onSel, _nodePreset(node), _nodeDisplay(node)?.value);
                });
                return { widget: tw };
            },

            /** ── Path picker (file or directory) ── */
            ACES_PATH(node, inputName, inputData /*, app */) {
                const opts   = inputData[1] ?? {};
                const def    = opts.default ?? "";
                const mode   = opts.mode   ?? "file";   // "file" | "dir"
                const filter = opts.filter ?? "";        // e.g. ".exr"

                const tw = _makePickerWidget(node, inputName, def, (curVal, onSel) => {
                    openPathPicker(curVal, onSel, mode, filter);
                });
                return { widget: tw };
            },
        };
    },
});

// ─────────────────────────────────────────────────────────────────────────────
//  Tiny DOM utilities
// ─────────────────────────────────────────────────────────────────────────────

function _el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls)  e.className   = cls;
    if (text) e.textContent = text;
    return e;
}
function _esc(s) { return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }
