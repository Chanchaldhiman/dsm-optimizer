(() => {
  "use strict";
  const T = window.DSMTools;
  const W = T.Workspace;

  // Mirrors dsm_optimizer/io/writer.py so web view and Excel export agree.
  const CLUSTER_COLORS = [
    "#AED6F1", "#A9DFBF", "#F9E79F", "#F5CBA7", "#D7BDE2",
    "#FAD7A0", "#A3E4D7", "#85C1E9", "#D5DBDB", "#FADBD8",
  ];
  const DIAG_COLOR = "#BFC9CA";
  const EXTERNAL_COLOR = "#F1948A";
  const BUS_COLOR = "#2C3E50";
  const EMPTY_COLOR = "#FFFFFF";
  const GRID_LINE = "#D8DCE0";
  const CLUSTER_BORDER = "#14181C";
  const DIFF_COLORS = { 1: "#B8C4CE", 2: "#7DC98F", 3: "#E58A7B", 4: "#E8B75A" };

  const ALGOS = ["spectral", "mcl", "thebeau", "louvain"];
  const ALGO_NAMES = {
    spectral: "Spectral", mcl: "MCL", thebeau: "Thebeau", louvain: "Louvain",
  };
  const ALGO_DESC = {
    spectral: "Eigenvector partitioning — good at global structure",
    mcl: "Markov flow simulation — deterministic, finds natural granularity",
    thebeau: "Stochastic bidding (the classic DSM literature algorithm)",
    louvain: "Modularity maximization — fast, widely used in network science",
  };
  const SOURCE_LABELS = {
    spectral: "Spectral (raw)", mcl: "MCL (raw)", thebeau: "Thebeau (raw)",
    louvain: "Louvain (raw)", final: "Final (sequenced)", process: "Partitioned",
  };

  // ── DOM refs ─────────────────────────────────────────────────────────────
  const $ = (id) => document.getElementById(id);
  const fileInput = $("fileInput"), uploadZone = $("uploadZone"),
    uploadFilename = $("uploadFilename"), sheetField = $("sheetField"),
    sheetSelect = $("sheetSelect"), sampleBtn = $("sampleBtn"),
    newMatrixBtn = $("newMatrixBtn"), saveProjectBtn = $("saveProjectBtn"),
    openProjectBtn = $("openProjectBtn"), projectFileInput = $("projectFileInput"),
    dsmTypeSel = $("dsmType"), dsmTypeHint = $("dsmTypeHint"),
    conventionSel = $("convention"), constraintSection = $("constraintSection"),
    diffFileInput = $("diffFileInput"), runBtn = $("runBtn"), runHint = $("runHint"),
    errorBanner = $("errorBanner"), staleBanner = $("staleBanner"),
    emptyState = $("emptyState"), editorPanel = $("editorPanel"),
    editorSize = $("editorSize"), undoBtn = $("undoBtn"), redoBtn = $("redoBtn"),
    addElementBtn = $("addElementBtn"), toggleEditorBtn = $("toggleEditorBtn"),
    editorConventionNote = $("editorConventionNote"), editorScroll = $("editorScroll"),
    resultsEl = $("results"), stepCluster = $("stepCluster"),
    stepClusterLabel = $("stepClusterLabel"), stepSep1 = $("stepSep1"),
    stepChoose = $("stepChoose"), stepSep2 = $("stepSep2"), stepFinal = $("stepFinal"),
    statStrip = $("statStrip"), warningBanner = $("warningBanner"),
    guidanceBanner = $("guidanceBanner"), stepsBar = $("stepsBar"), toastEl = $("toast"),
    comparePanel = $("comparePanel"), compareGrid = $("compareGrid"),
    compareNote = $("compareNote"), loopsPanel = $("loopsPanel"),
    loopsContent = $("loopsContent"), finalTabBtn = $("finalTabBtn"),
    whatifTabBtn = $("whatifTabBtn"), stabilityTabBtn = $("stabilityTabBtn"),
    diffTabBtn = $("diffTabBtn"), propTabBtn = $("propTabBtn"),
    panelTitle = $("panelTitle"), panelNote = $("panelNote"),
    finalizeBtn = $("finalizeBtn"), finalizeStatus = $("finalizeStatus"),
    whatifBar = $("whatifBar"), stabilityBar = $("stabilityBar"),
    matrixCanvas = $("matrixCanvas"), chartCanvas = $("chartCanvas"),
    legend = $("legend"), busNote = $("busNote"),
    loadingOverlay = $("loadingOverlay"), loadingText = $("loadingText"),
    tooltip = $("tooltip"), reportBtn = $("reportBtn"), downloadBtn = $("downloadBtn");
  const tabs = document.querySelectorAll(".tab-btn");

  // ── State ────────────────────────────────────────────────────────────────
  let currentFile = null;        // raw File for xlsx sheet re-parse
  let analysis = null;           // /api/cluster payload
  let analysisType = null;       // 'component' | 'process'
  let stage2 = null;             // /api/sequence payload (component)
  let chosenAlgo = null;
  let stabilityCache = {};       // algo -> payload
  let whatif = null;             // {base, clusters, coreN}
  let diffData = null;           // DSMTools.diffMatrices output
  let diffName = null;
  let propMatrix = null;         // propagation risk matrix (workspace order)
  let finalizedSource = null;
  let activeTab = "original";
  let sequencing = false;
  let stale = false;
  let editorCollapsed = true;
  let propStale = false;

  // ── Workspace change hook ────────────────────────────────────────────────
  W.onChange = (dirty) => {
    if (!dirty) {               // fresh load — reset all downstream state
      analysis = null; analysisType = null; stage2 = null; chosenAlgo = null;
      stabilityCache = {}; whatif = null; diffData = null; propMatrix = null;
      finalizedSource = null; stale = false;
      resultsEl.style.display = "none";
      downloadBtn.disabled = true; reportBtn.disabled = true;
      staleBanner.style.display = "none";
      updateFinalizeStatus();
    } else if (analysis) {
      stale = true;
      propStale = true;
      staleBanner.style.display = "flex";
    }
    emptyState.style.display = W.loaded ? "none" : "flex";
    editorPanel.style.display = W.loaded ? "block" : "none";
    editorScroll.style.display = editorCollapsed ? "none" : "block";
    toggleEditorBtn.textContent = editorCollapsed ? "Expand" : "Collapse";
    if (W.loaded && !editorCollapsed) T.Editor.render(editorScroll);
    editorSize.textContent = W.loaded ? `${W.labels.length} × ${W.labels.length}` : "";
    runBtn.disabled = !W.loaded;
    saveProjectBtn.disabled = !W.loaded;
    undoBtn.disabled = !W.canUndo();
    redoBtn.disabled = !W.canRedo();
    uploadFilename.textContent = W.sourceName || "";
  };

  // ── DSM type / convention UI ─────────────────────────────────────────────
  function syncTypeUI() {
    const t = dsmTypeSel.value;
    dsmTypeHint.textContent = t === "process"
      ? "Sequences tasks, finds iteration loops (Tarjan), and suggests which dependencies to tear."
      : "Groups elements into modules that minimize cross-module dependencies.";
    constraintSection.style.display = t === "process" ? "none" : "block";
    runBtn.textContent = t === "process" ? "Run partitioning" : "Run clustering";
    runHint.textContent = t === "process"
      ? "One step — sequencing, loop detection, and tearing analysis run together."
      : "You'll compare four algorithms and pick one to sequence.";
  }
  dsmTypeSel.addEventListener("change", syncTypeUI);
  conventionSel.addEventListener("change", () => {
    editorConventionNote.textContent = conventionSel.value === "IR"
      ? "row depends on column" : "column depends on row (transposed on import)";
  });
  syncTypeUI();

  // ── File routing ─────────────────────────────────────────────────────────
  uploadZone.addEventListener("dragover", (e) => { e.preventDefault(); uploadZone.classList.add("dragover"); });
  uploadZone.addEventListener("dragleave", () => uploadZone.classList.remove("dragover"));
  uploadZone.addEventListener("drop", (e) => {
    e.preventDefault(); uploadZone.classList.remove("dragover");
    if (e.dataTransfer.files.length) routeFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) routeFile(fileInput.files[0]);
  });

  async function routeFile(file) {
    hideError();
    currentFile = null;
    sheetField.style.display = "none";
    sheetSelect.innerHTML = "";
    const name = file.name.toLowerCase();
    try {
      if (name.endsWith(".dsmproj") || name.endsWith(".json")) {
        const proj = T.Project.parse(await file.text());
        await applyProject(proj);
        return;
      }
      if (name.endsWith(".csv")) {
        const text = await file.text();
        if (T.looksLikeEdgeList(text)) {
          const { matrix, labels } = T.parseEdgeList(text);
          W.set(matrix, labels, file.name + " (edge list)");
          return;
        }
        await serverParse({ file });
        return;
      }
      if (/\.(xlsx|xlsm)$/.test(name)) {
        currentFile = file;
        const fd = new FormData(); fd.append("file", file);
        const res = await fetch("/api/sheets", { method: "POST", body: fd });
        const data = await res.json();
        if (res.ok && data.sheets && data.sheets.length > 1) {
          data.sheets.forEach((s) => {
            const o = document.createElement("option");
            o.value = s; o.textContent = s; sheetSelect.appendChild(o);
          });
          sheetField.style.display = "block";
        }
        await serverParse({ file, sheet: sheetSelect.value });
        return;
      }
      throw new Error("Unsupported file type. Use .xlsx, .xlsm, .csv, or .dsmproj.");
    } catch (e) {
      showError(e.message || String(e));
    }
  }

  sheetSelect.addEventListener("change", () => {
    if (currentFile) serverParse({ file: currentFile, sheet: sheetSelect.value })
      .catch((e) => showError(e.message));
  });

  async function serverParse({ file, sheet, useSample }) {
    const fd = new FormData();
    if (useSample) fd.append("use_sample", "1");
    else fd.append("file", file);
    if (sheet) fd.append("sheet", sheet);
    fd.append("convention", conventionSel.value);
    const res = await fetch("/api/parse", { method: "POST", body: fd });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Could not parse file.");
    W.set(data.matrix, data.labels, data.source_name);
  }

  sampleBtn.addEventListener("click", () =>
    serverParse({ useSample: true }).catch((e) => showError(e.message)));

  newMatrixBtn.addEventListener("click", () => {
    const n = 5;
    const m = Array.from({ length: n }, () => new Array(n).fill(0));
    W.set(m, Array.from({ length: n }, (_, i) => `Element ${i + 1}`), "untitled.dsmproj");
    editorCollapsed = false;
    toggleEditorBtn.textContent = "Collapse";
    editorScroll.style.display = "block";
    T.Editor.render(editorScroll);
  });

  openProjectBtn.addEventListener("click", () => projectFileInput.click());
  projectFileInput.addEventListener("change", async () => {
    if (!projectFileInput.files.length) return;
    try {
      const proj = T.Project.parse(await projectFileInput.files[0].text());
      await applyProject(proj);
      toast("Project loaded" + (proj.client_state && proj.client_state.analysis
        ? " — session restored where you left off" : ""));
    } catch (e) {
      showError(e.message || String(e));
    } finally {
      projectFileInput.value = "";
    }
  });

  // ── Project save / load ──────────────────────────────────────────────────
  saveProjectBtn.addEventListener("click", async () => {
    let serverState = null;
    try {
      const res = await fetch("/api/session_dump");
      if (res.ok) {
        const d = await res.json();
        if (d.has_session) serverState = d;
      }
    } catch (e) { /* workspace-only project is still valid */ }
    T.Project.download({
      params: gatherParams(),
      dsm_type: dsmTypeSel.value,
      convention: conventionSel.value,
      chosen_algorithm: chosenAlgo,
      client_state: analysis ? {
        analysis, analysisType, stage2, chosenAlgo,
        whatifClusters: whatif ? whatif.clusters : null,
        stabilityCache, finalizedSource, activeTab,
        diffData, diffName, propMatrix,
      } : null,
      server_state: serverState,
    });
    toast("Project saved — full session included");
  });

  async function applyProject(proj) {
    if (proj.convention) conventionSel.value = proj.convention;
    if (proj.dsm_type) dsmTypeSel.value = proj.dsm_type;
    syncTypeUI();
    const p = proj.params || {};
    const setIf = (id, key) => { if (p[key] !== undefined && p[key] !== null) $(id).value = p[key]; };
    setIf("minK", "min_k"); setIf("maxK", "max_k");
    setIf("minCluster", "min_cluster"); setIf("maxCluster", "max_cluster");
    setIf("busThreshold", "bus_threshold"); setIf("maxExternal", "max_external_ratio");
    setIf("seed", "seed");
    W.set(proj.matrix, proj.labels, proj.source_name || "project");   // wipes state

    // v1 projects stop here (matrix + settings only)
    const cs = proj.client_state;
    if (!cs || !cs.analysis) return;

    // rebuild the server session so re-sequence / stability / save keep
    // working on exactly the saved results (no re-clustering)
    if (proj.server_state) {
      try {
        await fetch("/api/session_restore", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(proj.server_state),
        });
      } catch (e) { /* views still restore; server actions may need a re-run */ }
    }

    analysis = cs.analysis;
    analysisType = cs.analysisType || "component";
    stabilityCache = cs.stabilityCache || {};
    diffData = cs.diffData || null;
    diffName = cs.diffName || null;
    propMatrix = cs.propMatrix || null;
    resultsEl.style.display = "block";

    propTabBtn.style.display = "inline-block";
    if (diffData) { diffTabBtn.style.display = "inline-block"; }

    if (analysisType === "process") {
      renderProcess();
    } else {
      renderComponentStage1();
      if (cs.stage2) {
        stage2 = cs.stage2;
        chosenAlgo = cs.chosenAlgo;
        finalizedSource = cs.finalizedSource || "final";
        finalTabBtn.style.display = "inline-block";
        whatifTabBtn.style.display = "inline-block";
        initWhatif();
        if (cs.whatifClusters && cs.whatifClusters.length === whatif.clusters.length) {
          whatif.clusters = cs.whatifClusters.slice();
        }
        downloadBtn.disabled = false;
        reportBtn.disabled = false;
        updateFinalizeStatus();
        renderStatStrip();
        renderComparePanel();
        updateSteps();
      }
    }
    const valid = [...tabs].some((b) => b.dataset.tab === cs.activeTab &&
                                        b.style.display !== "none");
    setActiveTab(valid ? cs.activeTab : (stage2 || analysisType === "process"
      ? "final" : (analysis.recommended || "original")));
  }

  // ── Editor controls ──────────────────────────────────────────────────────
  undoBtn.addEventListener("click", () => W.undo());
  redoBtn.addEventListener("click", () => W.redo());
  addElementBtn.addEventListener("click", () => {
    const name = prompt("New element name:", `Element ${W.labels.length + 1}`);
    if (name && name.trim()) W.addElement(name.trim());
  });
  toggleEditorBtn.addEventListener("click", () => {
    editorCollapsed = !editorCollapsed;
    editorScroll.style.display = editorCollapsed ? "none" : "block";
    toggleEditorBtn.textContent = editorCollapsed ? "Expand" : "Collapse";
    if (!editorCollapsed) T.Editor.render(editorScroll);
  });
  document.addEventListener("keydown", (e) => {
    if (!W.loaded || !(e.ctrlKey || e.metaKey) || e.key.toLowerCase() !== "z") return;
    if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
    e.preventDefault();
    e.shiftKey ? W.redo() : W.undo();
  });

  // ── Run analysis ─────────────────────────────────────────────────────────
  function gatherParams() {
    return {
      min_k: $("minK").value, max_k: $("maxK").value,
      min_cluster: $("minCluster").value, max_cluster: $("maxCluster").value,
      bus_threshold: $("busThreshold").value,
      max_external_ratio: $("maxExternal").value || "0.30",
      seed: $("seed").value,
    };
  }

  runBtn.addEventListener("click", runAnalysis);

  async function runAnalysis() {
    if (!W.loaded) return;
    hideError();
    resultsEl.style.display = "block";
    showLoading(dsmTypeSel.value === "process" ? "Partitioning..." : "Clustering (4 algorithms)...");
    runBtn.disabled = true;

    try {
      const res = await fetch("/api/cluster", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          matrix: W.matrix, labels: W.labels,
          params: gatherParams(), dsm_type: dsmTypeSel.value,
          convention: conventionSel.value, source_name: W.sourceName,
        }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Analysis failed.");

      analysis = data;
      analysisType = data.dsm_type;
      stage2 = null; chosenAlgo = null; stabilityCache = {}; whatif = null;
      stale = false; staleBanner.style.display = "none";

      editorCollapsed = true;
      editorScroll.style.display = "none";
      toggleEditorBtn.textContent = "Expand";
      if (analysisType === "process") renderProcess();
      else renderComponentStage1();
    } catch (e) {
      showError(e.message || String(e));
      if (!analysis) resultsEl.style.display = "none";
    } finally {
      hideLoading();
      runBtn.disabled = !W.loaded;
    }
  }

  // ── Component: stage 1 ───────────────────────────────────────────────────
  function renderComponentStage1() {
    stepsBar.style.display = "flex";
    guidanceBanner.style.display = "none";
    propTabBtn.style.display = "inline-block";
    document.querySelectorAll(".algo-tab, .diag-tab").forEach((b) => b.style.display = "inline-block");
    comparePanel.style.display = "block";
    loopsPanel.style.display = "none";
    finalTabBtn.style.display = "none";
    whatifTabBtn.style.display = "none";
    stabilityTabBtn.style.display = "inline-block";
    statStrip.style.display = "none";
    warningBanner.style.display = "none";
    stepChoose.style.display = "flex"; stepSep1.style.display = "block"; stepSep2.style.display = "block";
    stepClusterLabel.textContent = "Cluster";
    downloadBtn.disabled = true; reportBtn.disabled = false;
    finalizedSource = null; updateFinalizeStatus();
    updateSteps();
    renderComparePanel();
    setActiveTab(analysis.recommended || "spectral");
  }

  function renderComparePanel() {
    if (!analysis || analysisType !== "component") return;
    compareGrid.innerHTML = "";
    ALGOS.forEach((key) => compareGrid.appendChild(candidateCard(key)));
    compareNote.innerHTML = stage2
      ? `Sequenced with <b>${ALGO_NAMES[chosenAlgo]}</b>. Pick another candidate to re-sequence, or refine cluster membership by hand in the <b>What-if</b> tab. Check <b>Stability</b> to see how robust these assignments are across random seeds.`
      : `Candidates are <b>raw algorithm output</b> — your k range and cluster-size limits are applied in the sequencing step (small clusters merged, oversized ones split). Inspect each candidate in its tab, then pick one to sequence. Sequencing reorders elements <i>within</i> clusters (simulated annealing) to minimize feedback marks. <b>Recommended</b> = lowest Thebeau cost, but cost doesn't capture everything — check <b>Stability</b> before trusting a close call.`;
  }

  function candidateCard(key) {
    const cand = analysis.candidates[key];
    const card = document.createElement("div");
    const isRec = analysis.recommended === key;
    const isChosen = chosenAlgo === key;

    if (!cand) {
      card.className = "compare-card unavailable";
      card.innerHTML = `
        <div class="compare-card-head"><span class="compare-card-title">${ALGO_NAMES[key]}</span></div>
        <div class="compare-empty">No valid result for this matrix.</div>`;
      return card;
    }
    card.className = "compare-card" + (isChosen ? " winner" : "");
    let badge = isChosen ? '<span class="winner-badge">Sequenced</span>'
      : (isRec ? '<span class="rec-badge">Recommended</span>' : "");
    if (cand.k_in_range === false) {
      badge += ' <span class="range-badge" title="This algorithm\'s natural granularity fell outside your k range. Your k range and cluster-size limits are enforced when you sequence — small clusters get merged, oversized ones split.">outside k range</span>';
    }
    card.innerHTML = `
      <div class="compare-card-head">
        <span class="compare-card-title" title="${ALGO_DESC[key]}">${ALGO_NAMES[key]}</span>${badge}
      </div>
      <div class="compare-stats">
        <div><div class="compare-stat-label" title="Number of clusters found">Clusters</div><div class="compare-stat-value">${cand.n_clusters}</div></div>
        <div><div class="compare-stat-label" title="Thebeau coordination cost — lower is better">Cost</div><div class="compare-stat-value">${cand.cost.toFixed(1)}</div></div>
        <div><div class="compare-stat-label" title="Share of marks crossing cluster boundaries">Ext</div><div class="compare-stat-value">${(cand.external_ratio * 100).toFixed(1)}%</div></div>
      </div>
      <button class="btn btn-choose" ${sequencing ? "disabled" : ""}>${
        isChosen ? "Re-sequence" : `Sequence \u2192`}</button>`;
    card.querySelector(".btn-choose").addEventListener("click", () => runSequence(key));
    return card;
  }

  // ── Component: stage 2 ───────────────────────────────────────────────────
  async function runSequence(algorithm) {
    if (!analysis || sequencing) return;
    sequencing = true;
    hideError();
    showLoading(`Sequencing ${ALGO_NAMES[algorithm]} clusters (simulated annealing)...`);
    renderComparePanel();
    try {
      const res = await fetch("/api/sequence", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ algorithm }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Sequencing failed.");
      stage2 = data;
      chosenAlgo = algorithm;
      finalizedSource = "final";
      downloadBtn.disabled = false; reportBtn.disabled = false;
      updateFinalizeStatus();
      finalTabBtn.style.display = "inline-block";
      whatifTabBtn.style.display = "inline-block";
      initWhatif();
      renderStatStrip();
      setActiveTab("final");
    } catch (e) {
      showError(e.message || String(e));
    } finally {
      sequencing = false;
      hideLoading();
      renderComparePanel();
      updateSteps();
    }
  }

  function renderStatStrip() {
    const m = stage2.metrics;
    statStrip.style.display = "grid";
    statStrip.innerHTML = "";
    const stats = [
      ["Elements", analysis.n_elements, "Total elements in the matrix"],
      ["Clusters", m.n_clusters, "Core clusters (bus elements excluded)"],
      ["External coupling", (m.external_ratio * 100).toFixed(1) + "%",
        "Share of marks crossing cluster boundaries — lower is more modular"],
      ["Thebeau cost", m.cost.toFixed(1),
        "Coordination cost: penalizes large clusters and cross-cluster marks"],
      ["Bus elements", analysis.bus_elements.length,
        "Highly-connected elements set aside from clustering"],
    ];
    stats.forEach(([label, value, tip], i) => {
      const cell = document.createElement("div");
      cell.className = "stat-cell" + (i === 2 && m.exceeds_target ? " warn" : "");
      cell.title = tip;
      cell.innerHTML = `<div class="stat-label">${label}</div><div class="stat-value">${value}</div>`;
      statStrip.appendChild(cell);
    });
    if (m.exceeds_target) {
      warningBanner.style.display = "flex";
      warningBanner.innerHTML = `<span class="warn-triangle"></span><span><b>Above target:</b> external coupling (${(m.external_ratio * 100).toFixed(1)}%) exceeds your target (${(($("maxExternal").value || 0.30) * 100).toFixed(0)}%). Try widening min/max k or adjusting size limits.</span>`;
    } else {
      warningBanner.style.display = "none";
    }
  }

  // ── Process mode rendering ───────────────────────────────────────────────
  function renderProcess() {
    stepsBar.style.display = "none";
    propTabBtn.style.display = "inline-block";
    document.querySelectorAll(".algo-tab, .diag-tab").forEach((b) => b.style.display = "none");
    comparePanel.style.display = "none";
    loopsPanel.style.display = "block";
    finalTabBtn.style.display = "inline-block";
    whatifTabBtn.style.display = "none";
    stabilityTabBtn.style.display = "none";
    downloadBtn.disabled = false; reportBtn.disabled = false;
    finalizedSource = "process"; updateFinalizeStatus();

    // Guidance: catch the two situations where partitioning output confuses —
    // symmetric (undirected) matrices and one giant all-encompassing loop.
    const gm = analysis.metrics;
    const symmetric = gm.symmetry_ratio >= 0.6;
    const giantLoop = gm.largest_loop >= 0.8 * gm.n_elements && gm.n_loops >= 1;
    if (symmetric) {
      guidanceBanner.style.display = "flex";
      guidanceBanner.innerHTML = `<span class="warn-triangle"></span><span>
        <b>${(gm.symmetry_ratio * 100).toFixed(0)}% of dependencies here run in both directions</b>,
        which reads as an undirected <b>component/architecture</b> matrix, not a directed task flow.
        On a symmetric matrix every ordering has identical feedback (${gm.feedback_before} → ${gm.feedback_after} here — that's mathematics, not a failed run),
        so partitioning can't produce the block-triangular form you may be expecting.
        Switch <b>DSM type</b> to <i>Component</i> in the sidebar and re-run — clustering is the right analysis for this data.</span>`;
    } else if (giantLoop) {
      guidanceBanner.style.display = "flex";
      guidanceBanner.innerHTML = `<span class="warn-triangle"></span><span>
        <b>One iteration loop spans ${gm.largest_loop} of ${gm.n_elements} tasks</b> — the process is
        almost fully coupled, so reordering alone can't decompose it. The actionable output is the
        <b>tearing table</b> below: tear the top suggestions (treat those inputs as assumptions),
        remove those marks in the matrix editor, and re-run to watch the loop break apart.
        If this is actually a parts/architecture matrix, switch DSM type to <i>Component</i> instead.</span>`;
    } else {
      guidanceBanner.style.display = "none";
    }

    const m = analysis.metrics;
    statStrip.style.display = "grid";
    statStrip.innerHTML = "";
    const stats = [
      ["Elements", m.n_elements, "Total tasks"],
      ["Loops", m.n_loops, "Iteration loops (strongly-connected components) — no reordering can remove these"],
      ["Coupled tasks", m.coupled_elements, "Tasks trapped inside iteration loops"],
      ["Parallel levels", m.n_levels, "Independent stages — tasks on the same level can run concurrently"],
      ["Feedback marks", `${m.feedback_before} \u2192 ${m.feedback_after}`,
        "Dependencies pointing at later tasks, before vs after resequencing"],
    ];
    stats.forEach(([label, value, tip]) => {
      const cell = document.createElement("div");
      cell.className = "stat-cell";
      cell.title = tip;
      cell.innerHTML = `<div class="stat-label">${label}</div><div class="stat-value">${value}</div>`;
      statStrip.appendChild(cell);
    });
    warningBanner.style.display = "none";

    loopsContent.innerHTML = "";
    if (!analysis.loops.length) {
      loopsContent.innerHTML = `<div class="compare-empty">No iteration loops — this process is fully sequential/parallel. The reordered matrix below has every dependency pointing backward.</div>`;
    }
    analysis.loops.forEach((lp, i) => {
      const card = document.createElement("div");
      card.className = "loop-card";
      const tears = lp.tears.map((t) => `
        <tr>
          <td>${esc(t.from_label)} \u2192 ${esc(t.to_label)}</td>
          <td>${t.weight}</td>
          <td>${t.impact} task${t.impact === 1 ? "" : "s"} freed</td>
          <td>${t.fully_resolves ? '<span class="tear-full">breaks the loop entirely</span>'
                : `largest remaining loop: ${t.largest_loop_after}`}</td>
        </tr>`).join("");
      card.innerHTML = `
        <div class="loop-title">Loop ${i + 1} — ${lp.size} coupled tasks (${lp.internal_feedback} residual feedback mark${lp.internal_feedback === 1 ? "" : "s"} after SA ordering)</div>
        <div class="loop-members">${lp.member_labels.map(esc).join(" \u21c4 ")}</div>
        <table class="tear-table">
          <tr><th>Tear this dependency</th><th>Weight</th><th>Impact</th><th>Result</th></tr>
          ${tears}
        </table>
        <div class="hint" style="margin-top:6px;">Tearing = plan to start with an assumption for this input and verify later. Prefer low-weight tears with high impact.</div>`;
      loopsContent.appendChild(card);
    });

    setActiveTab("final");
  }

  // ── What-if mode ─────────────────────────────────────────────────────────
  function initWhatif() {
    const base = stage2.final;
    whatif = {
      base,
      clusters: base.clusters.slice(),
      nBus: analysis.bus_labels.length,
    };
  }

  function whatifCore() {
    // strip bus elements (always last nBus rows/cols of the final matrix)
    const n = whatif.base.labels.length - whatif.nBus;
    const mat = whatif.base.matrix.slice(0, n).map((r) => r.slice(0, n));
    return { mat, clusters: whatif.clusters.slice(0, n), n };
  }

  function renderWhatifBar() {
    const { mat, clusters, n } = whatifCore();
    const baseCl = whatif.base.clusters.slice(0, n);
    const cost = T.thebeauCost(mat, clusters);
    const ext = T.externalRatio(mat, clusters);
    const baseCost = T.thebeauCost(mat, baseCl);
    const baseExt = T.externalRatio(mat, baseCl);
    const cmp = (v, b) => v < b - 1e-9 ? "improved" : (v > b + 1e-9 ? "worse" : "");

    const clusterIds = [...new Set(clusters)].sort((a, b) => a - b);
    whatifBar.innerHTML = `
      <span class="whatif-select-wrap">
        <label for="wiElement">Move</label>
        <select id="wiElement">${whatif.base.labels.slice(0, n).map((l, i) =>
          `<option value="${i}">${esc(l)}</option>`).join("")}</select>
        <label for="wiCluster">to cluster</label>
        <select id="wiCluster">${clusterIds.map((c) =>
          `<option value="${c}">${c + 1}</option>`).join("")}
          <option value="new">new cluster</option></select>
        <button class="mini-btn" id="wiApply">Apply</button>
      </span>
      <span class="whatif-metric ${cmp(cost, baseCost)}" title="Thebeau cost — algorithm result: ${baseCost.toFixed(1)}">Cost <b>${cost.toFixed(1)}</b> <small>(algo: ${baseCost.toFixed(1)})</small></span>
      <span class="whatif-metric ${cmp(ext, baseExt)}" title="External coupling — algorithm result: ${(baseExt * 100).toFixed(1)}%">External <b>${(ext * 100).toFixed(1)}%</b> <small>(algo: ${(baseExt * 100).toFixed(1)}%)</small></span>
      <button class="mini-btn" id="wiReset">Reset to algorithm result</button>
      <button class="mini-btn" id="wiFinalize">Use for download</button>`;

    $("wiApply").onclick = () => {
      const el = parseInt($("wiElement").value, 10);
      const v = $("wiCluster").value;
      const target = v === "new" ? Math.max(...whatif.clusters) + 1 : parseInt(v, 10);
      whatif.clusters[el] = target;
      renderTab("whatif");
    };
    $("wiReset").onclick = () => {
      whatif.clusters = whatif.base.clusters.slice();
      renderTab("whatif");
    };
    $("wiFinalize").onclick = async () => {
      const view = whatifView();
      await doFinalizeRaw("final", view.matrix, view.labels, view.clusters);
    };
  }

  function whatifView() {
    // Regroup: order core elements by (cluster, current position); bus stay last.
    const n = whatif.base.labels.length;
    const nCore = n - whatif.nBus;
    const order = [];
    [...new Set(whatif.clusters.slice(0, nCore))].sort((a, b) => a - b)
      .forEach((c) => {
        for (let i = 0; i < nCore; i++) if (whatif.clusters[i] === c) order.push(i);
      });
    for (let i = nCore; i < n; i++) order.push(i);
    const matrix = order.map((i) => order.map((j) => whatif.base.matrix[i][j]));
    const labels = order.map((i) => whatif.base.labels[i]);
    const clusters = order.map((i) => whatif.clusters[i]);
    return { matrix, labels, clusters };
  }

  // ── Stability tab ────────────────────────────────────────────────────────
  function renderStabilityBar() {
    const avail = ["spectral", "thebeau", "louvain"].filter((a) => analysis.candidates[a]);
    const cached = stabilityCache[avail[0]];
    stabilityBar.innerHTML = `
      <span class="whatif-select-wrap">
        <label for="stAlgo">Algorithm</label>
        <select id="stAlgo">${avail.map((a) => `<option value="${a}">${ALGO_NAMES[a]}</option>`).join("")}</select>
        <label for="stRuns">runs</label>
        <input type="number" id="stRuns" value="20" min="5" max="50" style="width:60px;">
        <button class="mini-btn" id="stRun">Analyze</button>
      </span>
      <span id="stSummary" class="whatif-metric"></span>`;
    $("stRun").onclick = () => runStability($("stAlgo").value, parseInt($("stRuns").value, 10) || 20);
    $("stAlgo").onchange = () => {
      const c = stabilityCache[$("stAlgo").value];
      if (c) drawStability(c); else clearStabilityView();
    };
    const first = stabilityCache[$("stAlgo") ? $("stAlgo").value : avail[0]] || cached;
    if (first) drawStability(first); else clearStabilityView();
  }

  function clearStabilityView() {
    matrixCanvas.style.display = "none";
    chartCanvas.style.display = "none";
    legend.style.display = "none";
    busNote.textContent = "Pick an algorithm and click Analyze. MCL is deterministic, so it has no seed variance to measure.";
    const s = $("stSummary"); if (s) s.textContent = "";
  }

  async function runStability(algorithm, runs) {
    showLoading(`Running ${ALGO_NAMES[algorithm]} \u00d7 ${runs} seeds...`);
    try {
      const res = await fetch("/api/stability", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ algorithm, runs }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Stability analysis failed.");
      stabilityCache[algorithm] = data;
      drawStability(data);
    } catch (e) {
      showError(e.message || String(e));
    } finally {
      hideLoading();
    }
  }

  function drawStability(data) {
    matrixCanvas.style.display = "block";
    chartCanvas.style.display = "none";
    legend.style.display = "none";
    const s = $("stSummary");
    if (s) s.innerHTML = `Mean consistency <b>${(data.mean_consistency * 100).toFixed(1)}%</b> \u00b7 ${data.n_distinct_partitions} distinct partition${data.n_distinct_partitions === 1 ? "" : "s"} in ${data.runs} runs`;
    drawHeatmapOn(matrixCanvas, data.co_cluster, data.labels,
      (v) => blueScale(v),
      (i, j, v) => `${data.labels[i]} + ${data.labels[j]}: same cluster in ${(v * 100).toFixed(0)}% of runs`);
    const weak = data.labels.filter((_, i) => data.consistency[i] < 0.7);
    busNote.textContent = weak.length
      ? `Unsettled elements (consistency < 70% — decide these manually): ${weak.join(", ")}`
      : "All module assignments are stable across seeds — safe to trust this partition.";
  }

  // ── Diff & propagation ───────────────────────────────────────────────────
  diffFileInput.addEventListener("change", async () => {
    if (!diffFileInput.files.length) return;
    if (!W.loaded) { showError("Load a base matrix first, then a second one to diff."); return; }
    const file = diffFileInput.files[0];
    hideError();
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("convention", conventionSel.value);
      const res = await fetch("/api/parse", { method: "POST", body: fd });
      const data = await res.json();
      if (!res.ok) throw new Error(data.error || "Could not parse comparison file.");
      diffData = T.diffMatrices(W.labels, W.matrix, data.labels, data.matrix);
      diffName = data.source_name;
      propMatrix = T.propagationRisk(W.matrix);
      diffTabBtn.style.display = "inline-block";
      propTabBtn.style.display = "inline-block";
      if (resultsEl.style.display === "none") {
        resultsEl.style.display = "block";
        statStrip.style.display = "none";
        comparePanel.style.display = "none";
        loopsPanel.style.display = "none";
        stepsBar.style.display = "none";
      }
      setActiveTab("diff");
    } catch (e) {
      showError(e.message || String(e));
    } finally {
      diffFileInput.value = "";
    }
  });

  // ── Tabs ─────────────────────────────────────────────────────────────────
  tabs.forEach((btn) => btn.addEventListener("click", () => setActiveTab(btn.dataset.tab)));

  function setActiveTab(tab) {
    tabs.forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
    activeTab = tab;
    renderTab(tab);
  }

  function updateSteps() {
    if (analysisType !== "component") return;
    stepCluster.className = "step done";
    stepChoose.className = "step " + (stage2 ? "done" : "current");
    stepFinal.className = "step " + (stage2 ? "done" : "");
  }

  function renderTab(tab) {
    whatifBar.style.display = tab === "whatif" ? "flex" : "none";
    stabilityBar.style.display = tab === "stability" ? "flex" : "none";
    finalizeBtn.style.display = "none";
    busNote.textContent = "";
    panelNote.textContent = "";

    if (tab === "whatif") {
      if (!whatif) { emptyPanel("What-if", "Sequence a clustering first."); return; }
      panelTitle.textContent = "What-if — refine cluster membership by hand";
      renderWhatifBar();
      const view = whatifView();
      showMatrix(view.matrix, view.labels, view.clusters, analysis.bus_labels);
      busNote.textContent = "Move elements between clusters and watch cost/external update. Engineers often know constraints the matrix doesn't — trust yourself on close calls.";
      return;
    }
    if (tab === "stability") {
      if (!analysis || analysisType !== "component") { emptyPanel("Stability", "Run clustering first."); return; }
      panelTitle.textContent = "Stability — is this partition robust, or a coin flip?";
      renderStabilityBar();
      return;
    }
    if (tab === "diff") {
      panelTitle.textContent = `Diff — ${W.sourceName || "current"} vs ${diffName || "?"}`;
      renderDiff();
      return;
    }
    if (tab === "propagation") {
      panelTitle.textContent = "Change propagation risk (current matrix)";
      renderPropagation();
      return;
    }

    // Matrix / chart tabs
    const meta = matrixTabMeta(tab);
    if (!meta) return;
    panelTitle.textContent = meta.title;
    if (meta.type === "matrix") {
      const src = meta.src();
      if (!src) { emptyPanel(meta.title, meta.emptyMsg || "No result yet."); return; }
      panelNote.textContent = `${src.labels.length} \u00d7 ${src.labels.length}`;
      showMatrix(src.matrix, src.labels, src.clusters, src.busLabels || []);
      updateFinalizeButton(meta, src);
      if (src.clusters && analysis && analysis.bus_labels && analysis.bus_labels.length) {
        busNote.textContent = `Bus elements (appended last, connect broadly by definition): ${analysis.bus_labels.join(", ")}`;
      }
      if (meta.note) busNote.textContent = meta.note;
    } else if (meta.type === "pareto") {
      showChart();
      panelNote.textContent = `${analysis.pareto.length} points`;
      drawParetoChart(analysis.pareto);
      busNote.textContent = "Diagnostic: spectral at every k (core elements). Look for the knee — where adding clusters stops reducing external coupling.";
    } else if (meta.type === "fiedler") {
      showChart();
      const comps = analysis.core_components_labels;
      panelNote.textContent = comps ? "largest connected group" : "core elements";
      drawFiedlerChart(analysis.fiedler, analysis.fiedler_labels || []);
      if (comps) {
        const islands = comps.slice(1).map((c) =>
          c.length <= 4 ? c.join(", ") : `${c.length} elements`).join("  |  ");
        busNote.innerHTML = `<b>The core matrix is disconnected — it splits into ${comps.length} independent groups`
          + ` with no dependencies between them.</b> That alone is its most natural decomposition`
          + ` (separate islands: ${islands} — often accessories that only connected to the rest via the removed bus elements).`
          + ` The Fiedler profile below is computed <i>within the largest group</i>, where it is meaningful:`
          + ` the blue/red sign split is that group's natural 2-way division, near-zero elements are weakly attached.`;
      } else {
        busNote.textContent = "Diagnostic: elements sorted by Fiedler value. The sign split (blue vs red) is the matrix's most natural 2-way decomposition; elements near zero are the weakly-attached ones. Bus elements are excluded.";
      }
    }
  }

  function matrixTabMeta(tab) {
    if (tab === "original") {
      return {
        title: "Original DSM", type: "matrix", source: null,
        src: () => analysis
          ? { matrix: analysis.original.matrix, labels: analysis.original.labels, clusters: null }
          : (W.loaded ? { matrix: W.matrix, labels: W.labels, clusters: null } : null),
      };
    }
    if (ALGOS.includes(tab)) {
      return {
        title: `${ALGO_NAMES[tab]} clustering (raw, pre-sequencing)`, type: "matrix", source: tab,
        emptyMsg: `No valid ${ALGO_NAMES[tab]} result for this matrix.`,
        src: () => {
          const c = analysis && analysis.candidates && analysis.candidates[tab];
          return c ? { matrix: c.matrix, labels: c.labels, clusters: c.clusters } : null;
        },
      };
    }
    if (tab === "final") {
      if (analysisType === "process") {
        return {
          title: "Partitioned & sequenced", type: "matrix", source: null,
          note: "Blocks in execution order; boxed blocks of size > 1 are iteration loops. Remaining above-diagonal marks are unavoidable loop feedback.",
          src: () => ({
            matrix: analysis.final.matrix, labels: analysis.final.labels,
            clusters: analysis.final.clusters,
          }),
        };
      }
      return {
        title: "Final (sequenced)", type: "matrix", source: "final",
        emptyMsg: "No sequenced result yet — choose an algorithm above.",
        src: () => stage2
          ? { matrix: stage2.final.matrix, labels: stage2.final.labels, clusters: stage2.final.clusters, busLabels: analysis.bus_labels }
          : null,
      };
    }
    if (tab === "pareto") return { title: "Pareto sweep — k vs. coupling / cost", type: "pareto" };
    if (tab === "fiedler") return { title: "Fiedler vector — natural decomposition", type: "fiedler" };
    return null;
  }

  function emptyPanel(title, msg) {
    panelTitle.textContent = title;
    matrixCanvas.style.display = "none";
    chartCanvas.style.display = "none";
    legend.style.display = "none";
    busNote.textContent = msg;
  }

  function showMatrix(matrix, labels, clusters, busLabels) {
    matrixCanvas.style.display = "block";
    chartCanvas.style.display = "none";
    legend.style.display = "flex";
    drawMatrixOn(matrixCanvas, matrix, labels, clusters, busLabels || []);
    renderLegend(clusters !== null && clusters !== undefined);
  }

  function showChart() {
    matrixCanvas.style.display = "none";
    chartCanvas.style.display = "block";
    legend.style.display = "none";
  }

  // ── Diff rendering ───────────────────────────────────────────────────────
  function renderDiff() {
    if (!diffData) { emptyPanel("Diff", "Load a second DSM from the sidebar."); return; }
    matrixCanvas.style.display = "block";
    chartCanvas.style.display = "none";
    const d = diffData;
    panelNote.textContent = `+${d.added} added \u00b7 \u2212${d.removed} removed \u00b7 ${d.changed} reweighted`;
    drawHeatmapOn(matrixCanvas, d.status, d.labels,
      (v, i, j) => (i === j ? DIAG_COLOR : (DIFF_COLORS[v] || EMPTY_COLOR)),
      (i, j, v) => {
        const names = { 1: "unchanged", 2: "added in new version", 3: "removed in new version", 4: "weight changed" };
        return `${d.labels[i]} \u2192 ${d.labels[j]}: ${names[v] || "no dependency"}`;
      });
    legend.style.display = "flex";
    legend.innerHTML = "";
    [["Unchanged", DIFF_COLORS[1]], ["Added", DIFF_COLORS[2]],
     ["Removed", DIFF_COLORS[3]], ["Weight changed", DIFF_COLORS[4]]].forEach(([l, c]) => {
      const el = document.createElement("div");
      el.className = "legend-item";
      el.innerHTML = `<span class="legend-swatch" style="background:${c}"></span>${l}`;
      legend.appendChild(el);
    });
    const parts = [];
    if (d.newEls.length) parts.push(`New elements: ${d.newEls.join(", ")}`);
    if (d.goneEls.length) parts.push(`Removed elements: ${d.goneEls.join(", ")}`);
    busNote.textContent = parts.join("  \u00b7  ");
  }

  function renderPropagation() {
    if (!W.loaded) { emptyPanel("Propagation", "Load a matrix first."); return; }
    const n = W.labels.length;
    if (n > 400) { emptyPanel("Propagation", `Matrix too large for in-browser propagation (${n} elements, limit 400).`); return; }
    if (!propMatrix || propStale) {
      propMatrix = T.propagationRisk(W.matrix);
      propStale = false;
    }
    matrixCanvas.style.display = "block";
    chartCanvas.style.display = "none";
    panelNote.textContent = "strongest path, \u2264 4 hops";
    drawHeatmapOn(matrixCanvas, propMatrix, W.labels,
      (v, i, j) => (i === j ? DIAG_COLOR : heatRamp(v)),
      (i, j, v) => `A change in ${W.labels[j]} reaches ${W.labels[i]} \u2014 strength ${(v * 100).toFixed(0)}%`);
    legend.style.display = "flex";
    legend.innerHTML = `<div style="display:flex; align-items:center; gap:10px; font-size:11px; font-family:var(--font-mono); color:var(--ink-soft);">
      <span>none</span>
      <span style="position:relative; display:inline-block; width:260px; height:12px; border:1px solid var(--rule-strong); border-radius:3px; background:${heatCSSGradient()};">
        <span title="4 hops away" style="position:absolute; left:21.6%; top:-3px; width:1px; height:18px; background:#14181C;"></span>
        <span title="3 hops away" style="position:absolute; left:36%; top:-3px; width:1px; height:18px; background:#14181C;"></span>
        <span title="2 hops away" style="position:absolute; left:60%; top:-3px; width:1px; height:18px; background:#14181C;"></span>
      </span>
      <span>direct</span>
      <span style="color:var(--ink-faint);">ticks = 2/3/4-hop bands</span>
    </div>`;

    // Per-element susceptibility summary: which elements drive change through
    // the system, and which are most exposed to change made elsewhere.
    const driver = new Array(n).fill(0);   // column mean: change HERE reaches many
    const prone = new Array(n).fill(0);    // row mean: change ANYWHERE reaches it
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      if (i === j) continue;
      driver[j] += propMatrix[i][j] / (n - 1);
      prone[i] += propMatrix[i][j] / (n - 1);
    }
    const rank = (arr) => arr.map((v, i) => [v, i]).sort((a, b) => b[0] - a[0])
      .slice(0, 6).filter((p) => p[0] > 0.01)
      .map((p) => `${esc(W.labels[p[1]])} <small>(${(p[0] * 100).toFixed(0)}%)</small>`);
    busNote.innerHTML =
      `<b>Change drivers</b> — modifying these ripples widest through the system (freeze their interfaces early): ${rank(driver).join(" \u00b7 ") || "none"}<br>`
      + `<b>Most change-prone</b> — these absorb changes made elsewhere (design them tolerant, verify them late): ${rank(prone).join(" \u00b7 ") || "none"}<br>`
      + `<span style="color:var(--ink-faint)">Model: strongest propagation path, attenuated 40% per interface hop (Clarkson-style), up to 4 hops — full red = direct dependency, lighter bands = 2nd/3rd/4th-hand exposure. Column j = "if j changes, who's at risk"; percentages are mean reach strength.</span>`;
  }

  // ── Finalize / download / report ─────────────────────────────────────────
  function updateFinalizeButton(meta, src) {
    const downloadReady = (analysisType === "component" && stage2);
    if (!meta.source || !downloadReady || !src || !src.clusters) {
      finalizeBtn.style.display = "none";
      return;
    }
    finalizeBtn.style.display = "inline-block";
    const isFinal = meta.source === finalizedSource;
    finalizeBtn.textContent = isFinal ? "Currently set for download" : "Set as final for download";
    finalizeBtn.classList.toggle("is-final", isFinal);
    finalizeBtn.disabled = isFinal;
    finalizeBtn.onclick = isFinal ? null :
      () => doFinalizeRaw(meta.source, src.matrix, src.labels, src.clusters);
  }

  async function doFinalizeRaw(source, matrix, labels, clusters) {
    try {
      const res = await fetch("/api/finalize", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ source, matrix, labels, clusters }),
      });
      const out = await res.json();
      if (!res.ok) throw new Error(out.error || "Could not set as final.");
      finalizedSource = source;
      downloadBtn.disabled = false;
      updateFinalizeStatus();
      renderTab(activeTab);
    } catch (e) {
      showError(e.message || String(e));
    }
  }

  function updateFinalizeStatus() {
    finalizeStatus.textContent = finalizedSource
      ? `Download: ${SOURCE_LABELS[finalizedSource] || finalizedSource}` : "";
  }

  downloadBtn.addEventListener("click", async () => {
    downloadBtn.disabled = true;
    try {
      const res = await fetch("/api/save", { method: "POST" });
      const out = await res.json();
      if (!res.ok) throw new Error(out.error || "Could not save.");
      toast(`Saved: ${out.path}`);
    } catch (e) {
      showError(e.message || String(e));
    } finally {
      downloadBtn.disabled = false;
    }
  });

  reportBtn.addEventListener("click", buildReport);

  function offscreenMatrix(matrix, labels, clusters, busLabels) {
    const c = document.createElement("canvas");
    drawMatrixOn(c, matrix, labels, clusters, busLabels || []);
    return `<img src="${c.toDataURL("image/png")}">`;
  }

  function buildReport() {
    if (!analysis) return;
    const meta = `${W.sourceName} \u00b7 ${analysis.n_elements} elements \u00b7 generated ${new Date().toLocaleString()} \u00b7 DSM Optimizer`;
    const sections = [];
    const p = gatherParams();

    if (analysisType === "process") {
      const m = analysis.metrics;
      sections.push({ h: "Summary", html: `<table>
        <tr><th>Loops</th><th>Coupled tasks</th><th>Parallel levels</th><th>Feedback marks</th></tr>
        <tr><td>${m.n_loops}</td><td>${m.coupled_elements} of ${m.n_elements}</td>
        <td>${m.n_levels}</td><td>${m.feedback_before} \u2192 ${m.feedback_after}</td></tr></table>` });
      sections.push({ h: "Original DSM", html: offscreenMatrix(analysis.original.matrix, analysis.original.labels, null) });
      sections.push({ h: "Partitioned & sequenced", html: offscreenMatrix(analysis.final.matrix, analysis.final.labels, analysis.final.clusters) });
      if (analysis.loops.length) {
        const rows = analysis.loops.map((lp, i) =>
          lp.tears.map((t) => `<tr><td>${i + 1}</td><td>${esc(t.from_label)} \u2192 ${esc(t.to_label)}</td><td>${t.weight}</td><td>${t.impact}</td><td>${t.fully_resolves ? "yes" : "no"}</td></tr>`).join("")).join("");
        sections.push({ h: "Tearing suggestions", html: `<table><tr><th>Loop</th><th>Dependency</th><th>Weight</th><th>Tasks freed</th><th>Breaks loop</th></tr>${rows}</table>` });
      }
    } else {
      const rows = ALGOS.map((a) => {
        const c = analysis.candidates[a];
        return `<tr><td>${ALGO_NAMES[a]}${a === analysis.recommended ? " (recommended)" : ""}${a === chosenAlgo ? " (chosen)" : ""}</td>
          <td>${c ? c.n_clusters : "\u2014"}</td><td>${c ? c.cost.toFixed(1) : "\u2014"}</td>
          <td>${c ? (c.external_ratio * 100).toFixed(1) + "%" : "\u2014"}</td></tr>`;
      }).join("");
      sections.push({ h: "Algorithm comparison", html: `<table><tr><th>Algorithm</th><th>Clusters</th><th>Thebeau cost</th><th>External</th></tr>${rows}</table>` });
      sections.push({ h: "Parameters", html: `<table><tr><th>k range</th><th>Cluster size</th><th>Bus threshold</th><th>Seed</th></tr>
        <tr><td>${p.min_k}\u2013${p.max_k}</td><td>${p.min_cluster}\u2013${p.max_cluster}</td>
        <td>${p.bus_threshold || "adaptive"}</td><td>${p.seed || "none"}</td></tr></table>` });
      sections.push({ h: "Original DSM", html: offscreenMatrix(analysis.original.matrix, analysis.original.labels, null) });
      if (stage2) {
        const m = stage2.metrics, s = stage2.sequencing;
        sections.push({ h: `Final (sequenced, ${ALGO_NAMES[chosenAlgo]})`, html:
          `<table><tr><th>Clusters</th><th>External coupling</th><th>Thebeau cost</th><th>Feedback marks</th></tr>
          <tr><td>${m.n_clusters}</td><td>${(m.external_ratio * 100).toFixed(1)}%</td>
          <td>${m.cost.toFixed(1)}</td><td>${s.feedback_before} \u2192 ${s.feedback_after}</td></tr></table>`
          + offscreenMatrix(stage2.final.matrix, stage2.final.labels, stage2.final.clusters, analysis.bus_labels) });
        const members = {};
        stage2.final.labels.forEach((l, i) => {
          const c = stage2.final.clusters[i];
          (members[c] = members[c] || []).push(l);
        });
        const mrows = Object.keys(members).map((c) =>
          `<tr><td>${+c + 1}</td><td>${members[c].map(esc).join(", ")}</td></tr>`).join("");
        sections.push({ h: "Cluster membership", html: `<table><tr><th>Cluster</th><th>Members</th></tr>${mrows}</table>` });
      }
      const st = stabilityCache[chosenAlgo] || Object.values(stabilityCache)[0];
      if (st) {
        sections.push({ h: `Stability (${ALGO_NAMES[st.algorithm]}, ${st.runs} runs)`, html:
          `<p>Mean consistency ${(st.mean_consistency * 100).toFixed(1)}% \u00b7 ${st.n_distinct_partitions} distinct partitions.</p>` });
      }
    }
    if (diffData) {
      sections.push({ h: `Diff vs ${esc(diffName)}`, html:
        `<p>+${diffData.added} added \u00b7 \u2212${diffData.removed} removed \u00b7 ${diffData.changed} reweighted.` +
        (diffData.newEls.length ? ` New elements: ${diffData.newEls.map(esc).join(", ")}.` : "") +
        (diffData.goneEls.length ? ` Removed elements: ${diffData.goneEls.map(esc).join(", ")}.` : "") + `</p>` });
    }
    const html = T.reportHTML(`DSM Report — ${W.sourceName}`, meta, sections);
    fetch("/api/save_report", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ html }),
    }).then((r) => r.json().then((out) => {
      if (!r.ok) throw new Error(out.error || "Could not save report.");
      toast(`Report saved: ${out.path} — open it and print to PDF`);
    })).catch((e) => showError(e.message || String(e)));
  }

  // ── Canvas: matrix ───────────────────────────────────────────────────────
  function fitText(ctx, text, maxWidth) {
    if (ctx.measureText(text).width <= maxWidth) return text;
    let lo = 1, hi = text.length;
    while (lo < hi) {
      const mid = (lo + hi + 1) >> 1;
      if (ctx.measureText(text.slice(0, mid) + "\u2026").width <= maxWidth) lo = mid;
      else hi = mid - 1;
    }
    return text.slice(0, lo) + "\u2026";
  }

  function drawMatrixOn(canvas, matrix, labels, clusters, busLabels) {
    const n = labels.length;
    const dpr = window.devicePixelRatio || 1;
    const cell = Math.max(8, Math.min(20, Math.floor(720 / n)));
    const labelSpace = Math.min(210, 22 + Math.max(...labels.map((l) => l.length)) * 5.6);
    const size = labelSpace + cell * n + 4;

    canvas.width = size * dpr; canvas.height = size * dpr;
    canvas.style.width = size + "px"; canvas.style.height = size + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);
    ctx.fillStyle = "#FFFFFF"; ctx.fillRect(0, 0, size, size);
    ctx.textBaseline = "middle";

    const busSet = new Set(busLabels || []);
    ctx.font = `${Math.min(cell - 1, 10)}px 'IBM Plex Mono', monospace`;
    for (let j = 0; j < n; j++) {
      const x = labelSpace + j * cell + cell / 2;
      ctx.save(); ctx.translate(x, labelSpace - 6); ctx.rotate(-Math.PI / 2);
      ctx.fillStyle = busSet.has(labels[j]) ? BUS_COLOR : "#14181C";
      ctx.textAlign = "left"; ctx.fillText(fitText(ctx, labels[j], labelSpace - 12), 0, 0); ctx.restore();
    }
    ctx.textAlign = "right";
    for (let i = 0; i < n; i++) {
      ctx.fillStyle = busSet.has(labels[i]) ? BUS_COLOR : "#14181C";
      ctx.fillText(fitText(ctx, labels[i], labelSpace - 12), labelSpace - 6, labelSpace + i * cell + cell / 2);
    }
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      const x = labelSpace + j * cell, y = labelSpace + i * cell;
      let fill = EMPTY_COLOR;
      if (i === j) fill = DIAG_COLOR;
      else if (matrix[i][j] > 0) {
        if (clusters == null) fill = "#1F5FA8";
        else if (busSet.has(labels[i]) || busSet.has(labels[j])) fill = "#AEB9C4";
        else if (clusters[i] === clusters[j]) fill = CLUSTER_COLORS[clusters[i] % CLUSTER_COLORS.length];
        else fill = EXTERNAL_COLOR;
      }
      ctx.fillStyle = fill; ctx.fillRect(x, y, cell, cell);
      ctx.strokeStyle = GRID_LINE; ctx.lineWidth = 0.5;
      ctx.strokeRect(x + 0.25, y + 0.25, cell - 0.5, cell - 0.5);
    }
    if (clusters != null) {
      [...new Set(clusters)].forEach((c) => {
        const pos = [];
        clusters.forEach((cl, idx) => { if (cl === c) pos.push(idx); });
        if (!pos.length) return;
        const r0 = Math.min(...pos), r1 = Math.max(...pos);
        ctx.strokeStyle = CLUSTER_BORDER; ctx.lineWidth = 1.6;
        ctx.strokeRect(labelSpace + r0 * cell, labelSpace + r0 * cell,
                       (r1 - r0 + 1) * cell, (r1 - r0 + 1) * cell);
      });
    }
    ctx.strokeStyle = "#8B95A0"; ctx.lineWidth = 1;
    ctx.strokeRect(labelSpace, labelSpace, cell * n, cell * n);

    if (canvas === matrixCanvas) {
      canvas.onmousemove = (e) => {
        const rect = canvas.getBoundingClientRect();
        const col = Math.floor((e.clientX - rect.left - labelSpace) / cell);
        const row = Math.floor((e.clientY - rect.top - labelSpace) / cell);
        if (row < 0 || col < 0 || row >= n || col >= n) { tooltip.style.display = "none"; return; }
        tooltip.style.display = "block";
        tooltip.style.left = e.clientX + 14 + "px";
        tooltip.style.top = e.clientY + 14 + "px";
        if (row === col) tooltip.textContent = labels[row];
        else {
          const rel = clusters == null ? "" : (clusters[row] === clusters[col] ? " (intra-cluster)" : " (external)");
          tooltip.textContent = `${labels[row]} \u2192 ${labels[col]}: ${matrix[row][col]}${rel}`;
        }
      };
      canvas.onmouseleave = () => { tooltip.style.display = "none"; };
    }
  }

  // ── Canvas: generic heatmap (stability, diff, propagation) ──────────────
  function drawHeatmapOn(canvas, values, labels, colorFn, tipFn) {
    const n = labels.length;
    const dpr = window.devicePixelRatio || 1;
    const cell = Math.max(8, Math.min(20, Math.floor(720 / n)));
    const labelSpace = Math.min(210, 22 + Math.max(...labels.map((l) => l.length)) * 5.6);
    const size = labelSpace + cell * n + 4;
    canvas.width = size * dpr; canvas.height = size * dpr;
    canvas.style.width = size + "px"; canvas.style.height = size + "px";
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, size, size);
    ctx.fillStyle = "#FFFFFF"; ctx.fillRect(0, 0, size, size);
    ctx.textBaseline = "middle";
    ctx.font = `${Math.min(cell - 1, 10)}px 'IBM Plex Mono', monospace`;
    for (let j = 0; j < n; j++) {
      ctx.save(); ctx.translate(labelSpace + j * cell + cell / 2, labelSpace - 6);
      ctx.rotate(-Math.PI / 2); ctx.fillStyle = "#14181C";
      ctx.textAlign = "left"; ctx.fillText(fitText(ctx, labels[j], labelSpace - 12), 0, 0); ctx.restore();
    }
    ctx.textAlign = "right"; ctx.fillStyle = "#14181C";
    for (let i = 0; i < n; i++)
      ctx.fillText(fitText(ctx, labels[i], labelSpace - 12), labelSpace - 6, labelSpace + i * cell + cell / 2);
    for (let i = 0; i < n; i++) for (let j = 0; j < n; j++) {
      ctx.fillStyle = colorFn(values[i][j], i, j);
      ctx.fillRect(labelSpace + j * cell, labelSpace + i * cell, cell, cell);
      ctx.strokeStyle = GRID_LINE; ctx.lineWidth = 0.5;
      ctx.strokeRect(labelSpace + j * cell + 0.25, labelSpace + i * cell + 0.25, cell - 0.5, cell - 0.5);
    }
    ctx.strokeStyle = "#8B95A0"; ctx.lineWidth = 1;
    ctx.strokeRect(labelSpace, labelSpace, cell * n, cell * n);

    canvas.onmousemove = (e) => {
      const rect = canvas.getBoundingClientRect();
      const col = Math.floor((e.clientX - rect.left - labelSpace) / cell);
      const row = Math.floor((e.clientY - rect.top - labelSpace) / cell);
      if (row < 0 || col < 0 || row >= n || col >= n) { tooltip.style.display = "none"; return; }
      tooltip.style.display = "block";
      tooltip.style.left = e.clientX + 14 + "px";
      tooltip.style.top = e.clientY + 14 + "px";
      tooltip.textContent = row === col ? labels[row] : tipFn(row, col, values[row][col]);
    };
    canvas.onmouseleave = () => { tooltip.style.display = "none"; };
  }

  function blueScale(v) {
    const t = Math.max(0, Math.min(1, v));
    const mix = (a, b) => Math.round(a + (b - a) * t);
    return `rgb(${mix(255, 31)}, ${mix(255, 95)}, ${mix(255, 168)})`;
  }
  // Multi-hue sequential ramp (white -> yellow -> orange -> red -> dark red).
  // Single-hue red compressed the model's distinct hop-bands into
  // near-identical pinks; multi-hue keeps every band visually separable.
  const HEAT_STOPS = [
    [0.00, [255, 255, 255]],
    [0.12, [255, 246, 200]],
    [0.25, [252, 217, 125]],
    [0.42, [244, 152,  62]],
    [0.65, [219,  82,  46]],
    [1.00, [138,  16,  28]],
  ];
  function heatRamp(v) {
    const t = Math.max(0, Math.min(1, v));
    for (let s = 1; s < HEAT_STOPS.length; s++) {
      if (t <= HEAT_STOPS[s][0]) {
        const [t0, c0] = HEAT_STOPS[s - 1];
        const [t1, c1] = HEAT_STOPS[s];
        const f = (t - t0) / (t1 - t0);
        const mix = (a, b) => Math.round(a + (b - a) * f);
        return `rgb(${mix(c0[0], c1[0])}, ${mix(c0[1], c1[1])}, ${mix(c0[2], c1[2])})`;
      }
    }
    return "rgb(138,16,28)";
  }
  function heatCSSGradient() {
    return "linear-gradient(to right, " +
      HEAT_STOPS.map(([t, c]) => `rgb(${c[0]},${c[1]},${c[2]}) ${t * 100}%`).join(", ") + ")";
  }

  function renderLegend(hasClusters) {
    legend.innerHTML = "";
    const items = hasClusters
      ? [["Intra-cluster mark", CLUSTER_COLORS[0]], ["Inter-cluster (external) mark", EXTERNAL_COLOR], ["Bus element", BUS_COLOR]]
      : [["Mark", "#1F5FA8"]];
    items.push(["Diagonal", DIAG_COLOR]);
    items.forEach(([label, color]) => {
      const el = document.createElement("div");
      el.className = "legend-item";
      el.innerHTML = `<span class="legend-swatch" style="background:${color}"></span>${label}`;
      legend.appendChild(el);
    });
  }

  // ── Pareto & Fiedler (unchanged renderers) ───────────────────────────────
  function drawParetoChart(pareto) {
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(600, Math.min(900, matrixCanvas.parentElement.clientWidth - 20));
    const h = 380, padL = 52, padR = 52, padT = 24, padB = 40;
    chartCanvas.width = w * dpr; chartCanvas.height = h * dpr;
    chartCanvas.style.width = w + "px"; chartCanvas.style.height = h + "px";
    const ctx = chartCanvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    if (!pareto.length) return;
    const ks = pareto.map((p) => p.k);
    const kMin = Math.min(...ks), kMax = Math.max(...ks);
    const extMax = Math.max(...pareto.map((p) => p.external_ratio), 0.01);
    const costMax = Math.max(...pareto.map((p) => p.cost), 0.01);
    const xFor = (k) => padL + ((k - kMin) / Math.max(kMax - kMin, 1)) * (w - padL - padR);
    const yExt = (v) => h - padB - (v / extMax) * (h - padT - padB);
    const yCost = (v) => h - padB - (v / costMax) * (h - padT - padB);
    ctx.strokeStyle = "#D8DCE0"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(padL, padT); ctx.lineTo(padL, h - padB); ctx.lineTo(w - padR, h - padB); ctx.stroke();
    ctx.font = "11px 'IBM Plex Mono', monospace"; ctx.fillStyle = "#8B95A0"; ctx.textAlign = "center";
    ks.forEach((k) => ctx.fillText(String(k), xFor(k), h - padB + 16));
    ctx.fillText("k (cluster count)", (padL + w - padR) / 2, h - 8);
    const line = (color, y) => {
      ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath();
      pareto.forEach((p, i) => { i === 0 ? ctx.moveTo(xFor(p.k), y(p)) : ctx.lineTo(xFor(p.k), y(p)); });
      ctx.stroke();
      pareto.forEach((p) => { ctx.fillStyle = color; ctx.beginPath(); ctx.arc(xFor(p.k), y(p), 3, 0, Math.PI * 2); ctx.fill(); });
    };
    line("#1F5FA8", (p) => yExt(p.external_ratio));
    line("#C77A17", (p) => yCost(p.cost));
    ctx.textAlign = "left";
    ctx.fillStyle = "#1F5FA8"; ctx.fillRect(padL, padT - 16, 10, 10);
    ctx.fillStyle = "#14181C"; ctx.fillText("external ratio (left)", padL + 16, padT - 9);
    ctx.fillStyle = "#C77A17"; ctx.fillRect(padL + 180, padT - 16, 10, 10);
    ctx.fillStyle = "#14181C"; ctx.fillText("Thebeau cost (right)", padL + 196, padT - 9);
    chartCanvas.onmousemove = (e) => {
      const rect = chartCanvas.getBoundingClientRect();
      const mx = e.clientX - rect.left;
      let closest = pareto[0], dist = Infinity;
      pareto.forEach((p) => { const d = Math.abs(xFor(p.k) - mx); if (d < dist) { dist = d; closest = p; } });
      if (dist < 20) {
        tooltip.style.display = "block";
        tooltip.style.left = e.clientX + 14 + "px";
        tooltip.style.top = e.clientY + 14 + "px";
        tooltip.textContent = `k=${closest.k}  external=${(closest.external_ratio * 100).toFixed(1)}%  cost=${closest.cost.toFixed(1)}`;
      } else tooltip.style.display = "none";
    };
    chartCanvas.onmouseleave = () => { tooltip.style.display = "none"; };
  }

  function drawFiedlerChart(rawFiedler, rawLabels) {
    // Sort by value: the sorted profile is how Fiedler vectors are read —
    // the sign change is the natural split, near-zero entries are the
    // weakly-attached elements.
    const pairs = rawFiedler.map((v, i) => [v, rawLabels[i] || `#${i}`])
                            .sort((a, b) => b[0] - a[0]);
    const fiedler = pairs.map((p) => p[0]);
    const labels = pairs.map((p) => p[1]);
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(600, Math.min(900, matrixCanvas.parentElement.clientWidth - 20));
    const barH = 16, padL = 140, padR = 30, padT = 20, padB = 20;
    const h = padT + padB + fiedler.length * barH;
    chartCanvas.width = w * dpr; chartCanvas.height = h * dpr;
    chartCanvas.style.width = w + "px"; chartCanvas.style.height = h + "px";
    const ctx = chartCanvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);
    const maxAbs = Math.max(...fiedler.map((v) => Math.abs(v)), 1e-9);
    const zeroX = padL + (w - padL - padR) / 2;
    const scale = (w - padL - padR) / 2 / maxAbs;
    ctx.font = "10.5px 'IBM Plex Mono', monospace";
    ctx.strokeStyle = "#D8DCE0";
    ctx.beginPath(); ctx.moveTo(zeroX, padT); ctx.lineTo(zeroX, h - padB); ctx.stroke();
    fiedler.forEach((v, i) => {
      const y = padT + i * barH;
      ctx.textAlign = "right"; ctx.fillStyle = "#4B5560";
      ctx.fillText(labels[i] || `#${i}`, padL - 8, y + barH / 2 + 3);
      const bw = Math.abs(v) * scale;
      ctx.fillStyle = v >= 0 ? "#1F5FA8" : "#C64B3C";
      ctx.fillRect(v >= 0 ? zeroX : zeroX - bw, y + 2, bw, barH - 5);
    });
    chartCanvas.onmousemove = (e) => {
      const rect = chartCanvas.getBoundingClientRect();
      const idx = Math.floor((e.clientY - rect.top - padT) / barH);
      if (idx < 0 || idx >= fiedler.length) { tooltip.style.display = "none"; return; }
      tooltip.style.display = "block";
      tooltip.style.left = e.clientX + 14 + "px";
      tooltip.style.top = e.clientY + 14 + "px";
      tooltip.textContent = `${labels[idx] || "#" + idx}: ${fiedler[idx].toFixed(4)}`;
    };
    chartCanvas.onmouseleave = () => { tooltip.style.display = "none"; };
  }

  // ── Helpers ──────────────────────────────────────────────────────────────
  function esc(s) { return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;"); }
  let toastTimer = null;
  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toastEl.classList.remove("show"), 6000);
  }

  function showLoading(text) { loadingText.textContent = text; loadingOverlay.classList.add("active"); }
  function hideLoading() { loadingOverlay.classList.remove("active"); }
  function showError(msg) { errorBanner.textContent = msg; errorBanner.classList.add("active"); }
  function hideError() { errorBanner.classList.remove("active"); errorBanner.textContent = ""; }
})();
