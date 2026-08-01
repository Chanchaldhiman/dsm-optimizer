/* DSM Optimizer — workspace, matrix editor, edge-list import, projects,
   diff + change propagation, what-if scoring, and report generation.
   Loaded before app.js; exposes window.DSMTools. No dependencies. */
(() => {
  "use strict";

  // ── Workspace: the editable source-of-truth matrix ──────────────────────
  const Workspace = {
    matrix: null,        // array of arrays (numbers)
    labels: null,
    sourceName: null,
    loaded: false,
    _undo: [],
    _redo: [],
    onChange: null,      // set by app.js — called after every mutation

    set(matrix, labels, sourceName) {
      this.matrix = matrix.map((r) => r.slice());
      this.labels = labels.slice();
      this.sourceName = sourceName || "matrix";
      this.loaded = true;
      this._undo = [];
      this._redo = [];
      this._emit(false);
    },

    _snapshot() {
      this._undo.push({ m: this.matrix.map((r) => r.slice()), l: this.labels.slice() });
      if (this._undo.length > 50) this._undo.shift();
      this._redo = [];
    },

    _emit(dirty = true) { if (this.onChange) this.onChange(dirty); },

    canUndo() { return this._undo.length > 0; },
    canRedo() { return this._redo.length > 0; },

    undo() {
      if (!this.canUndo()) return;
      this._redo.push({ m: this.matrix, l: this.labels });
      const s = this._undo.pop();
      this.matrix = s.m; this.labels = s.l;
      this._emit();
    },
    redo() {
      if (!this.canRedo()) return;
      this._undo.push({ m: this.matrix, l: this.labels });
      const s = this._redo.pop();
      this.matrix = s.m; this.labels = s.l;
      this._emit();
    },

    setCell(i, j, v) {
      if (i === j) return;
      this._snapshot();
      this.matrix[i][j] = v;
      this._emit();
    },
    toggleCell(i, j) { this.setCell(i, j, this.matrix[i][j] > 0 ? 0 : 1); },

    rename(i, name) {
      if (!name) return;
      this._snapshot();
      this.labels[i] = name;
      this._emit();
    },

    addElement(name) {
      this._snapshot();
      const n = this.labels.length;
      this.labels.push(name || `Element ${n + 1}`);
      this.matrix.forEach((row) => row.push(0));
      this.matrix.push(new Array(n + 1).fill(0));
      this._emit();
    },

    removeElement(i) {
      this._snapshot();
      this.labels.splice(i, 1);
      this.matrix.splice(i, 1);
      this.matrix.forEach((row) => row.splice(i, 1));
      this._emit();
    },
  };

  // ── Matrix editor (HTML table) ──────────────────────────────────────────
  const Editor = {
    render(container) {
      const { matrix, labels } = Workspace;
      if (!matrix) { container.innerHTML = ""; return; }
      const n = labels.length;
      const tbl = document.createElement("table");
      tbl.className = "dsm-edit";

      const thead = document.createElement("thead");
      const hr = document.createElement("tr");
      const corner = document.createElement("th");
      corner.className = "corner";
      hr.appendChild(corner);
      labels.forEach((lbl, j) => {
        const th = document.createElement("th");
        th.textContent = lbl.length > 10 ? lbl.slice(0, 9) + "\u2026" : lbl;
        th.title = `${lbl} — click to rename`;
        th.onclick = () => {
          const name = prompt("Rename element:", lbl);
          if (name && name.trim()) Workspace.rename(j, name.trim());
        };
        hr.appendChild(th);
      });
      thead.appendChild(hr);
      tbl.appendChild(thead);

      const tbody = document.createElement("tbody");
      for (let i = 0; i < n; i++) {
        const tr = document.createElement("tr");
        const th = document.createElement("th");
        const span = document.createElement("span");
        span.textContent = labels[i];
        span.title = "Click to rename";
        span.onclick = () => {
          const name = prompt("Rename element:", labels[i]);
          if (name && name.trim()) Workspace.rename(i, name.trim());
        };
        const del = document.createElement("span");
        del.className = "del-el";
        del.textContent = "\u00d7";
        del.title = `Delete ${labels[i]}`;
        del.onclick = (e) => {
          e.stopPropagation();
          if (confirm(`Delete element "${labels[i]}" and all its dependencies?`)) {
            Workspace.removeElement(i);
          }
        };
        th.appendChild(span); th.appendChild(del);
        tr.appendChild(th);

        for (let j = 0; j < n; j++) {
          const td = document.createElement("td");
          td.className = "cell" + (i === j ? " diag" : (matrix[i][j] > 0 ? " marked" : ""));
          if (i !== j) {
            const v = matrix[i][j];
            td.textContent = v > 0 ? (v === 1 ? "\u25cf" : String(v)) : "";
            td.title = `${labels[i]} depends on ${labels[j]}` +
                       (v > 0 ? ` (weight ${v})` : "") +
                       " — click to toggle, double-click for weight";
            td.onclick = () => Workspace.toggleCell(i, j);
            td.ondblclick = (e) => {
              e.preventDefault();
              const w = prompt(`Weight of dependency ${labels[i]} \u2192 ${labels[j]} (0 removes):`,
                               String(matrix[i][j] || 1));
              if (w === null) return;
              const num = parseFloat(w);
              if (!isNaN(num) && num >= 0) Workspace.setCell(i, j, num);
            };
          }
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
      tbl.appendChild(tbody);
      container.innerHTML = "";
      container.appendChild(tbl);
    },
  };

  // ── Edge-list CSV import ────────────────────────────────────────────────
  // Accepts lines of: from,to[,weight]  (header row auto-detected).
  // "from depends on to" — matches the IR convention used internally.
  function parseEdgeList(text) {
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (!lines.length) throw new Error("Edge list is empty.");
    const rows = lines.map((l) => l.split(",").map((c) => c.trim()));
    let start = 0;
    // Header detection: third column non-numeric, or first row matches from/to naming
    const first = rows[0].map((c) => c.toLowerCase());
    if (first[0] === "from" || first[0] === "source" ||
        (rows[0].length >= 3 && isNaN(parseFloat(rows[0][2])))) start = 1;

    const labels = [];
    const idx = {};
    const ensure = (name) => {
      if (!(name in idx)) { idx[name] = labels.length; labels.push(name); }
      return idx[name];
    };
    const edges = [];
    for (let r = start; r < rows.length; r++) {
      const cols = rows[r];
      if (cols.length < 2 || !cols[0] || !cols[1]) continue;
      const w = cols.length >= 3 && cols[2] !== "" ? parseFloat(cols[2]) : 1;
      if (isNaN(w)) throw new Error(`Bad weight on line ${r + 1}: "${rows[r][2]}"`);
      edges.push([ensure(cols[0]), ensure(cols[1]), w]);
    }
    if (labels.length < 2) throw new Error("Edge list needs at least two distinct elements.");
    const n = labels.length;
    const matrix = Array.from({ length: n }, () => new Array(n).fill(0));
    edges.forEach(([a, b, w]) => { if (a !== b) matrix[a][b] = w; });
    return { matrix, labels };
  }

  // Heuristic: is this CSV an edge list rather than a square matrix?
  // A matrix CSV's first data row has ~n+1 columns; an edge list has 2-3.
  function looksLikeEdgeList(text) {
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    if (lines.length < 2) return false;
    const widths = lines.slice(0, Math.min(6, lines.length))
                        .map((l) => l.split(",").length);
    return widths.every((w) => w >= 2 && w <= 3) && lines.length >= 2;
  }

  // ── Project files (.dsmproj — plain JSON) ───────────────────────────────
  const Project = {
    VERSION: 2,   // v2 adds client_state + server_state (full session); v1 files (matrix+settings) still load
    serialize(extra) {
      return JSON.stringify({
        format: "dsm-optimizer-project",
        version: this.VERSION,
        saved_at: new Date().toISOString(),
        matrix: Workspace.matrix,
        labels: Workspace.labels,
        source_name: Workspace.sourceName,
        ...extra,   // params, dsm_type, convention, chosen_algorithm, notes
      }, null, 1);
    },
    download(extra) {
      const blob = new Blob([this.serialize(extra)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      const base = (Workspace.sourceName || "dsm").replace(/\.[^.]+$/, "");
      a.download = `${base}.dsmproj`;
      a.click();
      URL.revokeObjectURL(a.href);
    },
    parse(text) {
      const obj = JSON.parse(text);
      if (obj.format !== "dsm-optimizer-project") throw new Error("Not a DSM Optimizer project file.");
      if (!obj.matrix || !obj.labels) throw new Error("Project file is missing matrix/labels.");
      return obj;
    },
  };

  // ── Scoring in JS (mirrors scoring/thebeau_cost.py) for live what-if ────
  function thebeauCost(matrix, clusters, powCc = 1.0, powBid = 1.0) {
    const n = matrix.length;
    const unique = [...new Set(clusters)];
    let total = 0;
    for (const c of unique) {
      const members = [];
      clusters.forEach((cl, i) => { if (cl === c) members.push(i); });
      const size = members.length;
      if (!size) continue;
      let intra = 0, extra = 0;
      for (const i of members) {
        for (let j = 0; j < n; j++) {
          if (i === j) continue;
          if (clusters[j] === c) { if (members.includes(j)) intra += matrix[i][j]; }
          else if (matrix[i][j] > 0) extra += matrix[i][j];
        }
      }
      if (intra > 0) total += Math.pow(intra, 2) / Math.pow(size, powCc);
      total += extra * Math.pow(n, powBid);
    }
    return total;
  }

  function externalRatio(matrix, clusters) {
    const n = matrix.length;
    let total = 0, ext = 0;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      total += matrix[i][j];
      if (i !== j && clusters[i] !== clusters[j] && matrix[i][j] > 0) ext += matrix[i][j];
    }
    return total > 0 ? ext / total : 0;
  }

  // ── Diff two matrices, aligned by label ─────────────────────────────────
  function diffMatrices(labelsA, matA, labelsB, matB) {
    const all = [...labelsA];
    labelsB.forEach((l) => { if (!all.includes(l)) all.push(l); });
    const ia = {}, ib = {};
    labelsA.forEach((l, i) => ia[l] = i);
    labelsB.forEach((l, i) => ib[l] = i);
    const n = all.length;
    // status[i][j]: 0 same-empty, 1 same-mark, 2 added (only in B),
    //               3 removed (only in A), 4 weight-changed
    const status = Array.from({ length: n }, () => new Array(n).fill(0));
    let added = 0, removed = 0, changed = 0;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      if (i === j) continue;
      const a = (all[i] in ia && all[j] in ia) ? matA[ia[all[i]]][ia[all[j]]] : 0;
      const b = (all[i] in ib && all[j] in ib) ? matB[ib[all[i]]][ib[all[j]]] : 0;
      if (a > 0 && b > 0) status[i][j] = a === b ? 1 : (changed++, 4);
      else if (b > 0) { status[i][j] = 2; added++; }
      else if (a > 0) { status[i][j] = 3; removed++; }
    }
    const newEls = all.filter((l) => !(l in ia));
    const goneEls = labelsA.filter((l) => !(l in ib));
    return { labels: all, status, added, removed, changed, newEls, goneEls };
  }

  // ── Change propagation (attenuated strongest-path) ──────────────────────
  // Earlier versions used probabilistic-OR over all paths; on a connected
  // matrix of ordinary density that saturates to ~100% everywhere within a
  // few hops — mathematically true, informationally useless (an all-red
  // heatmap). This model instead scores each pair by the STRONGEST single
  // propagation path, attenuated per interface hop (Clarkson's CPM data
  // showed strong attenuation across interfaces):
  //   direct:  w/maxW           (a change in a direct dependency)
  //   2 hops:  ≤ α·(w1/maxW)(w2/maxW),  3 hops: ≤ α² ..., etc., α = 0.6
  // Computed as a max-times relaxation: R ← max(A, max_k A[i][k]·α·R[k][j]).
  // Result: distinct bands by path length/strength instead of saturation.
  function propagationRisk(matrix, depth = 4, attenuation = 0.6) {
    const n = matrix.length;
    let maxW = 0;
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) maxW = Math.max(maxW, matrix[i][j]);
    if (maxW === 0) return matrix.map((r) => r.slice());
    const A = matrix.map((row) => row.map((v) => v / maxW));
    let R = A.map((r) => r.slice());
    for (let step = 1; step < depth; step++) {
      const next = A.map((r) => r.slice());          // direct always included
      for (let i = 0; i < n; i++) {
        for (let k = 0; k < n; k++) {
          if (A[i][k] === 0 || i === k) continue;
          const via = A[i][k] * attenuation;
          for (let j = 0; j < n; j++) {
            if (j === i) continue;
            const cand = via * R[k][j];
            if (cand > next[i][j]) next[i][j] = cand;
          }
        }
      }
      R = next;
    }
    for (let i = 0; i < n; i++) R[i][i] = 0;
    return R;
  }

  // ── Print-ready report ──────────────────────────────────────────────────
  // sections: [{h, html}] — returned as a standalone HTML string. The app
  // saves it server-side (Downloads folder) because window.open is blocked
  // in the desktop shell; the user opens the file and prints to PDF.
  function reportHTML(title, meta, sections) {
    const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");
    let out = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>
      body { font-family: 'Segoe UI', sans-serif; color: #14181C; margin: 32px; }
      h1 { font-size: 20px; border-bottom: 2px solid #1F5FA8; padding-bottom: 6px; }
      h2 { font-size: 15px; margin-top: 26px; }
      .meta { font-family: monospace; font-size: 11px; color: #4B5560; margin-bottom: 18px; }
      table { border-collapse: collapse; font-size: 12px; margin-top: 8px; }
      th, td { border: 1px solid #D8DCE0; padding: 4px 9px; text-align: left; }
      th { background: #F5F6F4; font-size: 10.5px; text-transform: uppercase; letter-spacing: 0.05em; }
      img { max-width: 100%; border: 1px solid #D8DCE0; margin-top: 8px; }
      .print-hint { background: #E8F0FA; padding: 8px 12px; font-size: 12px; border-radius: 4px; }
      @media print { .print-hint { display: none; } }
    </style></head><body>`;
    out += `<div class="print-hint">Use your browser's Print (Ctrl/Cmd+P) and choose "Save as PDF".</div>`;
    out += `<h1>${esc(title)}</h1><div class="meta">${esc(meta)}</div>`;
    sections.forEach((s) => { out += `<h2>${esc(s.h)}</h2>${s.html}`; });
    out += "</body></html>";
    return out;
  }

  window.DSMTools = {
    Workspace, Editor, Project,
    parseEdgeList, looksLikeEdgeList,
    thebeauCost, externalRatio,
    diffMatrices, propagationRisk,
    reportHTML,
  };
})();
