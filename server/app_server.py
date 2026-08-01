"""
DSM Optimizer - local web server.

Serves the static HTML/CSS/JS frontend and a JSON API wrapping the
dsm_optimizer pipeline. Runs entirely on localhost; nothing leaves the
machine.

API surface:

  POST /api/parse      - file (or sample) -> {matrix, labels}. Parsing only;
                         the client owns the working matrix from here (it can
                         be edited in the matrix editor before any analysis).
  POST /api/sheets     - list visible sheets of an uploaded workbook.
  POST /api/cluster    - JSON {matrix, labels, params, dsm_type}.
                         dsm_type='component': bus detection + four clustering
                         candidates (spectral, MCL, Thebeau, Louvain), each
                         independently scored; nothing committed.
                         dsm_type='process': partitioning - Tarjan SCCs,
                         topological sequencing, per-loop SA ordering, and
                         tearing suggestions. Complete in one step.
  POST /api/sequence   - {algorithm}: carry the user's chosen candidate
                         through size constraints + SA sequencing.
  POST /api/stability  - {algorithm, runs}: co-clustering consensus across
                         seeds for stochastic algorithms.
  POST /api/finalize   - point the download at any candidate the client holds.
  GET  /api/download   - color-coded .xlsx of the finalized result.
"""
import os
import sys
import io
import tempfile
import traceback

from flask import Flask, request, jsonify, send_file, send_from_directory

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BASE_DIR)

import openpyxl
import numpy as np

from dsm_optimizer import DSMOptimizer, DSMConstraints
from dsm_optimizer.io.reader import read_dsm
from dsm_optimizer.io.writer import write_excel
from dsm_optimizer.algorithms.partitioning import partition_dsm
from dsm_optimizer.analysis.stability import stability_analysis
from server.jsonsafe import to_jsonable

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")
SAMPLE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_dsm.xlsx")

app = Flask(__name__, static_folder=STATIC_DIR, static_url_path="")

# Single-user local app: one global session slot.
SESSION = {
    "matrix": None,        # np.ndarray - matrix used in the last /api/cluster
    "labels": None,
    "stage1": None,        # cluster_stage() result (component mode)
    "optimizer": None,
    "dsm_type": None,      # 'component' | 'process'
    "convention": "IR",    # how the user's file was interpreted (for export)
    "source_name": None,
    "params": {},
}

LAST_RESULT = {
    "matrix": None, "labels": None, "clusters": None,
    "title": "Optimized DSM", "source": "final",
}

ALGORITHMS = ("spectral", "mcl", "thebeau", "louvain")


# ── Static frontend ────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


# ── Parsing ────────────────────────────────────────────────────────────────

@app.route("/api/sheets", methods=["POST"])
def sheets():
    f = request.files.get("file")
    if f is None:
        return jsonify({"error": "No file uploaded."}), 400
    filename = f.filename or "upload"
    if filename.lower().endswith(".csv"):
        return jsonify({"sheets": []})
    try:
        with tempfile.NamedTemporaryFile(suffix=os.path.splitext(filename)[1], delete=False) as tmp:
            f.save(tmp.name)
            tmp_path = tmp.name
        wb = openpyxl.load_workbook(tmp_path, read_only=True, keep_links=False)
        visible = [ws.title for ws in wb.worksheets if ws.sheet_state == "visible"]
        wb.close()
        os.unlink(tmp_path)
        return jsonify({"sheets": visible})
    except Exception as e:
        return jsonify({"error": f"Could not read sheets: {e}"}), 400


@app.route("/api/parse", methods=["POST"])
def parse():
    """
    Parse a DSM file (or the bundled sample) into {matrix, labels}. The
    client keeps and may edit this matrix; analysis happens later via
    /api/cluster with the (possibly edited) matrix posted back as JSON.

    convention: 'IR' (default) - matrix[i][j] means row i depends on
    column j (Inputs-in-Rows / FAD). 'IC' - the transpose convention
    (Inputs-in-Columns / FBD); the matrix is transposed on import so the
    internal representation is always IR.
    """
    convention = request.form.get("convention", "IR")
    if request.form.get("use_sample") == "1":
        source_name = "sample_dsm.xlsx"
        try:
            matrix, labels = read_dsm(SAMPLE_FILE, 0)
        except Exception as e:
            return jsonify({"error": f"Could not read sample: {e}"}), 500
    else:
        f = request.files.get("file")
        if f is None:
            return jsonify({"error": "No file uploaded."}), 400
        source_name = f.filename or "upload.xlsx"
        sheet_param = request.form.get("sheet", "0")
        try:
            sheet = int(sheet_param)
        except ValueError:
            sheet = sheet_param
        try:
            with tempfile.NamedTemporaryFile(suffix=os.path.splitext(source_name)[1], delete=False) as tmp:
                f.save(tmp.name)
                tmp_path = tmp.name
            matrix, labels = read_dsm(tmp_path, sheet)
            os.unlink(tmp_path)
        except Exception as e:
            return jsonify({"error": f"Could not read file: {e}"}), 400

    if convention == "IC":
        matrix = matrix.T.copy()

    return jsonify(to_jsonable({
        "matrix": matrix, "labels": labels,
        "source_name": source_name, "convention": convention,
    }))


# ── Analysis (stage 1) ─────────────────────────────────────────────────────

def _constraints_from(params):
    def _int_or_none(v):
        return None if v in (None, "") else int(v)

    def _float_or_none(v):
        return None if v in (None, "") else float(v)

    return DSMConstraints(
        min_cluster_size=int(params.get("min_cluster", 2)),
        max_cluster_size=int(params.get("max_cluster", 20)),
        min_clusters=int(params.get("min_k", 2)),
        max_clusters=int(params.get("max_k", 10)),
        bus_threshold=_float_or_none(params.get("bus_threshold")),
        max_external_ratio=float(params.get("max_external_ratio", 0.30)),
        seed=_int_or_none(params.get("seed")),
    )


def _candidate_view(cand):
    if cand is None:
        return None
    return {k: v for k, v in cand.items() if k != "raw_clusters"}


def _validate_square(matrix, labels):
    if not matrix or not labels:
        return "matrix and labels are required."
    n = len(labels)
    if len(matrix) != n or any(len(row) != n for row in matrix):
        return f"matrix must be {n}x{n} to match {n} labels."
    return None


@app.route("/api/cluster", methods=["POST"])
def cluster():
    data = request.get_json(silent=True) or {}
    matrix = data.get("matrix")
    labels = data.get("labels")
    err = _validate_square(matrix, labels)
    if err:
        return jsonify({"error": err}), 400

    params = data.get("params", {}) or {}
    dsm_type = data.get("dsm_type", "component")
    matrix = np.array(matrix, dtype=float)
    np.fill_diagonal(matrix, 0)

    SESSION.update(matrix=matrix, labels=labels, dsm_type=dsm_type,
                   convention=data.get("convention", "IR"),
                   source_name=data.get("source_name", "matrix"),
                   params=params)
    LAST_RESULT.update(matrix=None, labels=None, clusters=None, source="final")

    try:
        if dsm_type == "process":
            seed = params.get("seed")
            seed = int(seed) if seed not in (None, "") else None
            result = partition_dsm(matrix, labels, seed=seed)
            SESSION["stage1"] = None
            SESSION["optimizer"] = None

            LAST_RESULT.update(
                matrix=result["matrix"], labels=result["labels"],
                clusters=result["clusters"], source="final",
                title=f"Partitioned DSM - {SESSION['source_name']}")

            payload = {
                "dsm_type": "process",
                "source_name": SESSION["source_name"],
                "n_elements": len(labels),
                "original": {"matrix": matrix, "labels": labels},
                "final": {"matrix": result["matrix"], "labels": result["labels"],
                          "clusters": result["clusters"], "levels": result["levels"]},
                "loops": result["loops"],
                "blocks": result["blocks"],
                "metrics": result["metrics"],
            }
            return jsonify(to_jsonable(payload))

        # component mode
        opt = DSMOptimizer(_constraints_from(params))
        stage1 = opt.cluster_stage(matrix, labels, verbose=False)

        core = stage1["core_idx"]
        core_mat = matrix[np.ix_(core, core)]
        pareto_raw = opt.pareto_sweep(core_mat)
        pareto = [{"k": k, "external_ratio": er, "cost": cost}
                  for k, er, cost in pareto_raw]

        SESSION["stage1"] = stage1
        SESSION["optimizer"] = opt

        payload = {
            "dsm_type": "component",
            "source_name": SESSION["source_name"],
            "n_elements": len(labels),
            "original": {"matrix": matrix, "labels": labels},
            "candidates": {name: _candidate_view(stage1.get(name))
                           for name in ALGORITHMS},
            "recommended": stage1["recommended"],
            "bus_elements": stage1["bus_elements"],
            "bus_labels": [labels[i] for i in stage1["bus_elements"]],
            "fiedler": stage1["fiedler"],
            "fiedler_labels": [labels[stage1["core_idx"][i]]
                               for i in stage1["fiedler_idx"]],
            "core_components_labels": (
                [[labels[stage1["core_idx"][i]] for i in comp]
                 for comp in stage1["core_components"]]
                if len(stage1["core_components"]) > 1 else None),
            "pareto": pareto,
        }
        return jsonify(to_jsonable(payload))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Analysis failed: {e}"}), 500


# ── Stage 2 (component mode) ───────────────────────────────────────────────

@app.route("/api/sequence", methods=["POST"])
def sequence():
    if SESSION["stage1"] is None:
        return jsonify({"error": "No clustering session - run stage 1 first."}), 400
    data = request.get_json(silent=True) or {}
    algorithm = data.get("algorithm")
    if algorithm not in ALGORITHMS:
        return jsonify({"error": f"algorithm must be one of {ALGORITHMS}."}), 400

    try:
        opt = SESSION["optimizer"]
        result = opt.sequence_stage(SESSION["matrix"], SESSION["labels"],
                                    SESSION["stage1"], algorithm, verbose=False)
        LAST_RESULT.update(
            matrix=result["matrix"], labels=result["labels"],
            clusters=result["clusters"], source="final",
            title=f"Optimized DSM - {SESSION['source_name']}")

        payload = {
            "final": {"matrix": result["matrix"], "labels": result["labels"],
                      "clusters": result["clusters"]},
            "metrics": result["metrics"],
            "sequencing": result["sequencing"],
            "after_constraints": result["after_constraints"],
            "winner": result["winner"],
        }
        return jsonify(to_jsonable(payload))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Sequencing failed: {e}"}), 500


# ── Stability analysis ─────────────────────────────────────────────────────

@app.route("/api/stability", methods=["POST"])
def stability():
    if SESSION["stage1"] is None:
        return jsonify({"error": "No clustering session - run clustering first."}), 400
    data = request.get_json(silent=True) or {}
    algorithm = data.get("algorithm")
    runs = min(int(data.get("runs", 20)), 50)
    if algorithm == "mcl":
        return jsonify({"error": "MCL is deterministic - stability analysis "
                                 "applies to the stochastic algorithms "
                                 "(spectral, thebeau, louvain)."}), 400
    if algorithm not in ("spectral", "thebeau", "louvain"):
        return jsonify({"error": "algorithm must be spectral, thebeau, or louvain."}), 400

    stage1 = SESSION["stage1"]
    cand = stage1.get(algorithm)
    if cand is None:
        return jsonify({"error": f"No valid {algorithm} candidate to analyse."}), 400

    try:
        core = stage1["core_idx"]
        core_mat = SESSION["matrix"][np.ix_(core, core)]
        res = stability_analysis(core_mat, algorithm, cand["raw_clusters"],
                                 runs=runs, min_k=stage1["min_k"],
                                 max_k=stage1["max_k"])
        # Order the co-cluster matrix by the candidate's clustering so blocks
        # are visible; return labels in that order too.
        order = []
        for cid in sorted(set(cand["raw_clusters"])):
            order.extend([i for i, c in enumerate(cand["raw_clusters"]) if c == cid])
        co = res["co_cluster"][np.ix_(order, order)]
        core_labels = [SESSION["labels"][core[i]] for i in order]
        consistency = [res["consistency"][i] for i in order]

        return jsonify(to_jsonable({
            "algorithm": algorithm,
            "runs": res["runs"],
            "n_distinct_partitions": res["n_distinct_partitions"],
            "mean_consistency": res["mean_consistency"],
            "labels": core_labels,
            "co_cluster": co,
            "consistency": consistency,
        }))
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Stability analysis failed: {e}"}), 500


# ── Finalize / download ───────────────────────────────────────────────────

_SOURCE_TITLES = {
    "spectral": "Spectral clustering",
    "mcl": "MCL clustering",
    "thebeau": "Thebeau clustering",
    "louvain": "Louvain clustering",
    "final": "Final (sequenced)",
    "process": "Partitioned (sequenced)",
}


@app.route("/api/finalize", methods=["POST"])
def finalize():
    data = request.get_json(silent=True) or {}
    source = data.get("source")
    matrix = data.get("matrix")
    labels = data.get("labels")
    clusters = data.get("clusters")

    if source not in _SOURCE_TITLES:
        return jsonify({"error": f"Unknown source '{source}'."}), 400
    err = _validate_square(matrix, labels)
    if err or clusters is None or len(clusters) != len(labels):
        return jsonify({"error": err or "clusters must match labels length."}), 400

    LAST_RESULT.update(
        matrix=np.array(matrix, dtype=float), labels=labels, clusters=clusters,
        source=source, title=f"Optimized DSM - {_SOURCE_TITLES[source]}")
    return jsonify({"ok": True, "source": source, "title": LAST_RESULT["title"]})


@app.route("/api/download")
def download():
    if LAST_RESULT["matrix"] is None:
        return jsonify({"error": "No result to download yet."}), 400

    matrix = LAST_RESULT["matrix"]
    # Round-trip the user's convention: if their file was IC, export IC too.
    if SESSION.get("convention") == "IC":
        matrix = matrix.T

    buf = io.BytesIO()
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp_path = tmp.name
    write_excel(tmp_path, matrix, LAST_RESULT["labels"],
                LAST_RESULT["clusters"], title=LAST_RESULT["title"])
    with open(tmp_path, "rb") as fh:
        buf.write(fh.read())
    os.unlink(tmp_path)
    buf.seek(0)
    return send_file(buf, as_attachment=True,
                     download_name=f"optimized_dsm_{LAST_RESULT['source']}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")


@app.route("/api/session_dump")
def session_dump():
    """
    Snapshot of the server-side session for embedding in a .dsmproj file.
    Includes stage-1 internals (raw_clusters) that the normal API strips,
    so a restored session can still sequence / run stability without
    re-running clustering (which, without a fixed seed, could give
    different results than the ones the user saved).
    """
    if SESSION["matrix"] is None:
        return jsonify({"has_session": False})
    dump = {
        "has_session": True,
        "matrix": SESSION["matrix"],
        "labels": SESSION["labels"],
        "stage1": SESSION["stage1"],
        "params": SESSION.get("params", {}),
        "dsm_type": SESSION["dsm_type"],
        "convention": SESSION["convention"],
        "source_name": SESSION["source_name"],
        "last_result": ({
            "matrix": LAST_RESULT["matrix"], "labels": LAST_RESULT["labels"],
            "clusters": LAST_RESULT["clusters"], "source": LAST_RESULT["source"],
            "title": LAST_RESULT["title"],
        } if LAST_RESULT["matrix"] is not None else None),
    }
    return jsonify(to_jsonable(dump))


@app.route("/api/session_restore", methods=["POST"])
def session_restore():
    """Rebuild the server session from a project file's embedded dump."""
    data = request.get_json(silent=True) or {}
    if not data.get("has_session") or data.get("matrix") is None:
        return jsonify({"ok": True, "restored": False})
    try:
        params = data.get("params", {}) or {}
        stage1 = data.get("stage1")
        if stage1 is not None:
            # candidate display matrices arrive as lists; sequence/stability
            # only read raw_clusters + scalars, but normalise anyway so any
            # future numpy consumer doesn't trip on plain lists.
            for name in ALGORITHMS:
                cand = stage1.get(name)
                if cand and cand.get("matrix") is not None:
                    cand["matrix"] = np.array(cand["matrix"], dtype=float)
        SESSION.update(
            matrix=np.array(data["matrix"], dtype=float),
            labels=data["labels"],
            stage1=stage1,
            optimizer=DSMOptimizer(_constraints_from(params)),
            params=params,
            dsm_type=data.get("dsm_type", "component"),
            convention=data.get("convention", "IR"),
            source_name=data.get("source_name", "project"),
        )
        lr = data.get("last_result")
        if lr and lr.get("matrix") is not None:
            LAST_RESULT.update(
                matrix=np.array(lr["matrix"], dtype=float),
                labels=lr["labels"], clusters=lr["clusters"],
                source=lr.get("source", "final"),
                title=lr.get("title", "Optimized DSM"))
        else:
            LAST_RESULT.update(matrix=None, labels=None, clusters=None, source="final")
        return jsonify({"ok": True, "restored": True})
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"Could not restore session: {e}"}), 400


def _save_dir():
    d = os.path.join(os.path.expanduser("~"), "Downloads")
    return d if os.path.isdir(d) else os.path.expanduser("~")


@app.route("/api/save", methods=["POST"])
def save():
    """
    Write the finalized result straight to the user's Downloads folder and
    return the path. Used instead of a browser download because the desktop
    shell (pywebview) does not handle navigation downloads; works identically
    when the app is opened in a normal browser, since the server is local.
    """
    if LAST_RESULT["matrix"] is None:
        return jsonify({"error": "No result to save yet."}), 400
    matrix = LAST_RESULT["matrix"]
    if SESSION.get("convention") == "IC":
        matrix = matrix.T
    import time
    fname = f"optimized_dsm_{LAST_RESULT['source']}_{time.strftime('%Y%m%d_%H%M%S')}.xlsx"
    path = os.path.join(_save_dir(), fname)
    try:
        write_excel(path, matrix, LAST_RESULT["labels"],
                    LAST_RESULT["clusters"], title=LAST_RESULT["title"])
        return jsonify({"ok": True, "path": path})
    except Exception as e:
        return jsonify({"error": f"Could not save: {e}"}), 500


@app.route("/api/save_report", methods=["POST"])
def save_report():
    """Save a client-assembled HTML report to Downloads (print to PDF from any browser)."""
    data = request.get_json(silent=True) or {}
    html = data.get("html")
    if not html or not isinstance(html, str):
        return jsonify({"error": "No report content."}), 400
    if len(html) > 40 * 1024 * 1024:
        return jsonify({"error": "Report too large."}), 400
    import time
    path = os.path.join(_save_dir(), f"dsm_report_{time.strftime('%Y%m%d_%H%M%S')}.html")
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        return jsonify({"ok": True, "path": path})
    except Exception as e:
        return jsonify({"error": f"Could not save report: {e}"}), 500


def create_app():
    return app


def serve(flask_app, host="127.0.0.1", port=8765):
    """
    Serve the app without the Flask development-server warning.

    Preferred: waitress - a small, pure-Python, threaded production WSGI
    server, so the warning disappears because it no longer applies (rather
    than being hidden). Fallback (waitress not installed, e.g. running from
    a source checkout): the dev server with its banner and per-request log
    lines silenced - for a localhost-only, single-user tool the dev server
    is functionally fine; the noise was the problem, not the safety.
    """
    try:
        from waitress import serve as _waitress_serve
        _waitress_serve(flask_app, host=host, port=port, threads=6)
    except ImportError:
        import logging
        logging.getLogger("werkzeug").setLevel(logging.ERROR)
        try:
            import flask.cli
            flask.cli.show_server_banner = lambda *a, **k: None
        except Exception:
            pass
        flask_app.run(host=host, port=port, debug=False,
                      use_reloader=False, threaded=True)


def main():
    """
    Console entry point (`dsm-optimizer` after pip install): starts the local
    server and pops the app open in the default browser - one command, no
    setup, nothing leaves the machine.
    """
    import socket
    import threading
    import webbrowser

    port = 8765
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex(("127.0.0.1", port)) == 0:   # taken - pick a free one
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s2:
                s2.bind(("127.0.0.1", 0))
                port = s2.getsockname()[1]

    url = f"http://127.0.0.1:{port}"
    print(f"DSM Optimizer running at {url}  (Ctrl+C to stop)")
    threading.Timer(1.0, lambda: webbrowser.open(url)).start()
    serve(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()