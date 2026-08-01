![DSM Optimizer: load a matrix, compare four algorithms, sequence, explore change propagation](docs/demo.gif)

# DSM Optimizer

**See the hidden structure of your system - then fix it.**

A free, local-first Design Structure Matrix workbench for systems engineers. Feed it your system's dependencies; it shows you which parts belong together, what order the work should happen in, which single dependencies cause your iteration loops, and which components will hurt most when requirements change.

No cloud. No account. No data leaves your machine.

---

## The problem this solves

Every complex product - a machine, a spacecraft, a software platform, a development process - is really a web of dependencies. That web is invisible, so teams discover it the expensive way:

- A "simple" change to one component ripples into five others, three sprints late.
- Two teams iterate against each other for months because their tasks form a loop nobody mapped.
- Module boundaries follow the org chart from 2019, not how the parts actually interact.
- At the design review, "why is it partitioned this way?" gets answered with a shrug.

A **Design Structure Matrix** makes the web visible: elements on both axes, a mark where one depends on another. It's the standard tool in the systems-engineering literature (Steward 1981; Eppinger & Browning, *Design Structure Matrix Methods and Applications*, MIT Press) - and it's chronically underused, because doing anything beyond looking at it means research code, MATLAB scripts, or expensive commercial tools.

DSM Optimizer is the missing middle: **research-grade algorithms, one-click app.**

## What it answers

**"How should this system be partitioned into modules?"** *(component / architecture DSMs)*
Four clustering algorithms - Spectral, Markov Clustering, **Thebeau's classic DSM algorithm**, and Louvain - compete on your matrix, each scored by coordination cost and external coupling. Highly-connected bus elements (power rails, data buses, shared frames) are detected and set aside automatically. **You** pick the winner: the tool recommends the lowest-cost partition but never overrides your judgment, and a live **what-if mode** lets you drag elements between modules and watch the cost update - because you know constraints the matrix doesn't.

**"What order should this work happen in?"** *(process / task DSMs)*
Tarjan's algorithm finds your iteration loops - the cycles no amount of reordering can remove. Everything else is topologically sequenced (dependencies first, parallel stages identified), and inside each loop, simulated annealing minimizes residual feedback. Then the part almost no free tool does: **tearing analysis** ranks every dependency inside a loop by how much the loop collapses if you treat that one input as an assumption - telling you precisely which decoupling buys the most.

**"If X changes, what breaks?"** *(both)*
A change-propagation map (attenuated strongest-path, Clarkson-style) shows every element's exposure, and ranks your **change drivers** (freeze their interfaces early) and **most change-prone** elements (design tolerant, verify late).

**"Would I get the same answer tomorrow?"**
Stability analysis reruns the stochastic algorithms across dozens of seeds and shows a consensus heatmap - which module assignments are robust, and which are coin flips you should decide by engineering judgment. Bring *that* to a design review.

## Get it

Pick whichever fits how you work — all three run the identical app, fully offline.

**Desktop app** — the fastest way to start. From [Releases](../../releases):
- **Windows:** `DSM_Optimizer_Setup.exe` (recommended — adds Start-menu shortcuts and gives `.dsmproj` project files their own icon), or the portable `DSM_Optimizer_Windows.zip` if you prefer nothing installed.
- **macOS:** `DSM_Optimizer_macOS.zip` — unzip and run. First launch: right-click → Open (the app is unsigned, so macOS asks once).
- **Linux:** use the Python package below — same app, opens in your browser.

*First-launch note:* the binaries are unsigned open-source builds, so Windows SmartScreen may show "Windows protected your PC" — click **More info → Run anyway**. This is about the missing paid signing certificate, not the software.

**Python package** — one command, opens in your browser:
```bash
pip install dsm-optimizer
dsm-optimizer
```

**From source** — for hacking on it:
```bash
pip install flask numpy scikit-learn openpyxl flask matplotlib waitress
python server/app_server.py        # then open http://127.0.0.1:8765
```

## Five-minute tour

1. Click **"Use the sample DSM"** (a small spacecraft-style system ships with the app), or drop in your own `.xlsx`/`.csv` - labels in the first column, square matrix of marks. Interview data as `from,to,weight` pairs? Drop the edge-list CSV straight in.
2. Don't have a matrix yet? **New blank matrix** opens the built-in editor: click cells to toggle dependencies, double-click for weights, rename and add elements, undo/redo. Building the matrix is 90% of DSM work - you shouldn't need Excel for it.
3. Pick the **DSM type** (component → clustering; process → sequencing and tearing) and the **mark convention** (row-depends-on-column or the transpose - one toggle, because getting this wrong silently flips the meaning of "feedback").
4. **Run.** Compare the four candidates, open their tabs, check **Stability**, then sequence the one you trust. Refine by hand in **What-if**.
5. **Save**: a color-coded `.xlsx` lands in your Downloads. **Report** writes a print-ready HTML file - matrices, comparison tables, cluster membership, tearing tables - ready for the design review PDF.
6. **Save project** (`.dsmproj`): your entire session - matrix, all results, hand edits, stability runs. Reopen it at the next review, or load next quarter's matrix alongside it with **Compare** to see exactly which dependencies changed.

## Who uses this, and for what

| You are… | You use it to… |
|---|---|
| Systems / mechanical engineer | Partition a product architecture into modules with minimal cross-module coupling; justify the partition with cost numbers and stability evidence |
| Program / project manager | Sequence a work plan, expose iteration loops between teams, and pick the cheapest dependency to "tear" (assume now, verify later) |
| Change-control board member | See propagation risk before approving an ECN: what does touching this component actually reach? |
| Software architect | Map service/package dependencies, find the natural module boundaries, compare against your current ones |
| Researcher / student | A faithful, tested, `pip`-installable implementation of Thebeau clustering, Tarjan partitioning, tearing, and consensus analysis to build on |

## The science (and its honesty)

- **Clustering objective:** Thebeau's coordination cost (Thebeau 2001), the standard in the DSM literature. Thebeau's stochastic algorithm itself is implemented faithfully from the published pseudocode and validated in the test suite against synthetic ground truth (planted block structures recovered at the planted structure's own cost; disconnected cliques recovered exactly). His original elevator dataset is not bundled, so those published numbers are not reproduced here - stated plainly rather than implied.
- **Partitioning:** Tarjan strongly-connected components → topological sequencing with parallel levels → per-loop simulated annealing → exhaustive single-tear impact ranking.
- **Spectral clustering:** normalized Laplacian, eigengap-selected k. The Fiedler diagnostic is component-aware: on a disconnected core it reports the islands (which *are* the first-order decomposition) and computes the profile within the largest component, where it's meaningful.
- **Change propagation:** strongest-path with 40% per-hop attenuation, in the spirit of Clarkson's CPM. This is a simplification of the full method (which uses elicited likelihood × impact per dependency) - labeled as such in the UI.
- **33 automated tests** cover the algorithms, including provably-correct-answer cases, determinism under seeds, and constraint enforcement.

## FAQ

**My process DSM shows one giant loop and identical feedback before/after.** Check whether your marks are symmetric (every dependency runs both ways). That's component/architecture data - on a symmetric matrix, *every* ordering has identical feedback (that's mathematics, not a failed run). The app detects this and tells you; switch DSM type to Component.

**MCL gave me more clusters than my max.** Candidates are raw algorithm output - an algorithm's natural granularity can't always be dialed. Your k range and size limits are enforced when you *sequence* the chosen candidate (small clusters merged, oversized split); out-of-range candidates are badged.

**Is my data uploaded anywhere?** No. The app is a local server talking to a local window. 

**Weighted dependencies?** Yes - any positive number. Weights feed the cost function, MCL flow, tearing preferences, and propagation strengths.

## For developers

The algorithms are a clean Python library, independent of the UI:

```python
from dsm_optimizer import DSMOptimizer, DSMConstraints
from dsm_optimizer.algorithms.partitioning import partition_dsm
from dsm_optimizer.analysis.stability import stability_analysis

opt = DSMOptimizer(DSMConstraints(seed=42))
stage1 = opt.cluster_stage(matrix, labels)        # 4 scored candidates
result = opt.sequence_stage(matrix, labels, stage1, algorithm="thebeau")

r = partition_dsm(matrix, labels, seed=42)        # loops, levels, tears
s = stability_analysis(matrix, "louvain", result["clusters"][:len(matrix)], runs=20)
```

`pytest tests/ -v` runs the suite. Releases publish to PyPI automatically on version tags via `.github/workflows/publish.yml` (PyPI Trusted Publishing - setup steps in the file). Windows installer with `.dsmproj` file association: `installer.iss` (Inno Setup). Full change history: [CHANGELOG.md](CHANGELOG.md).

## Roadmap

Multi-domain matrices (components × teams - does your org structure match your architecture?), full Clarkson CPM with elicited likelihood/impact, canvas-based editor for 200+ element matrices, worked case studies from the Eppinger & Browning book.

## License & citation

MIT. If this tool contributes to published work, cite the underlying methods (Steward 1981; Thebeau 2001; Eppinger & Browning 2012; Clarkson et al. 2004) - and a link back here helps others find it.

---

*Issues and PRs welcome - especially real-world matrices that break things.*
