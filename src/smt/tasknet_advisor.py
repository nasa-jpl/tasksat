"""LLM-assisted TaskNet advisor.

Reads a ``.tn`` file, runs the verifier to gather diagnostics, asks an LLM to
propose a rewrite (e.g. introduce a session + ``invariant`` so the network can be
checked compositionally), applies the proposal **to a copy**, re-verifies, and
either iterates autonomously (``--mode loop``) or hands back to the user after one
iteration (``--mode step``). The original file is never modified.

Design notes:

- The verifier is run **out-of-process** (its Z3 solves cannot be interrupted
  in-process), reusing the subprocess-with-timeout pattern from
  ``tasknet_web.run_verifier``. Diagnostics are read from the JSON artifacts the
  verifier already writes (``metadata.json`` / ``properties.json`` /
  ``unsat_core.json``) rather than by parsing stdout.
- The LLM backend is the Anthropic API, imported **lazily** inside
  :func:`propose_rewrite`, so this module (and its tests) import without the
  ``anthropic`` SDK or an API key. Tests monkeypatch :func:`propose_rewrite`.
- Every LLM rewrite passes a syntactic gate (:func:`validate_rewrite`, which uses
  the real parser) before any solve; a parse error is fed back to the LLM as the
  next turn's context rather than aborting.

The whole session is persisted to ``session.json`` / ``report.json`` under
``.tasksat/advisor/<stem>/<timestamp>/`` so both the CLI and the Flask web view
render the same conversation.
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

# Flat imports mirror the other src/smt tools; make them work whether this module
# is run as a script (its own dir is sys.path[0]) or imported from tests.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from tasknet_parser import parse_tasknet  # noqa: E402
from tasknet_printer import print_tasknet_to_string  # noqa: E402
from tasknet_ast import (  # noqa: E402
    TaskKind, ImpactAssign, ImpactCumulative, ImpactRateCumulative,
    ImpactRateAssignment,
)


DEFAULT_MODEL = "claude-opus-4-8"
SEP = "=" * 70

# The two rate-timeline modeling rules discovered while validating the
# compositional waypoint model. Embedded (not read from the gitignored internal
# doc) so the advisor is self-contained and never depends on internal files.
MODELING_RULES = """\
Two rules for making a rate-timeline model compositional (verify one session, hold
for all N via `invariant compositional { P }`):

1. LEAVE THE RATE TIMELINE'S INITIAL VALUE FREE. On a declaration like
   `battery : rate [..] bounds [..] = 50.0 initial_rate = 0.01`, the `= 50.0` is the
   timeline's VALUE and `initial_rate` is its RATE. Declaring the VALUE pins zone 0 to
   a single point and collapses the invariant band P to that point, so the check
   passes VACUOUSLY. Declare only `initial_rate`; leave the value free so the init
   region equals P's whole band and the checker explores the worst case.

2. CONSTRAIN THE SESSION SO *EVERY* SCHEDULE PRESERVES P (safety/AA), NOT JUST *SOME*
   (realizability/AE). E.g. fixed durations that net to zero over one session. If a
   session only ever pumps a resource one way (drains or charges) with no return, no
   predicate P is preserved and the compositional check is correctly VIOLATED.
"""


def tasksat_root() -> Path:
    """Repo root: this file is ``src/smt/tasknet_advisor.py``."""
    return Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Diagnostics: run the verifier out-of-process and read its JSON artifacts.
# ---------------------------------------------------------------------------

def run_verifier_capture(tn_path, flags=None, timeout=120, workdir=None,
                         task_id=None, running_tasks=None, running_lock=None):
    """Verify ``tn_path`` in a subprocess and return structured diagnostics.

    Runs ``tasknet_verifier.py`` with ``cwd=workdir`` so artifacts land under
    ``workdir/.tasksat/schedules/<stem>/latest/``, then reads them back. A
    ``subprocess.TimeoutExpired`` after ``timeout`` seconds is reported as
    ``timed_out=True`` (the verifier has no in-process wall-clock cap).

    If ``task_id``/``running_tasks``/``running_lock`` are supplied, the live process
    is registered there for the duration so a caller (the web UI) can cancel it.

    Returns a dict:
        status        'success' | 'violated' | 'unsat' | 'timeout' | 'error' | ...
        timed_out     bool
        outcome       'completed' | 'timeout' | 'killed'
        returncode    int | None
        durations     {'total', 'validity', 'property', 'compositional', ...}
        compositional 'holds' | 'violated' | 'unknown' | None
        realizability same shape | None
        properties    list of per-property dicts (name/status/formula/...)
        unsat_core    dict | None
        stdout_tail   last lines of stdout (for a crash with no metadata)
        stderr_tail   last lines of stderr
    """
    flags = list(flags or [])
    tn_path = Path(tn_path).resolve()
    workdir = Path(workdir or tn_path.parent)
    workdir.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable,
           str(tasksat_root() / "src" / "smt" / "tasknet_verifier.py"),
           str(tn_path), "--mode", "optimize", *flags]

    start = time.time()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=str(workdir))
    if task_id and running_tasks is not None and running_lock is not None:
        with running_lock:
            running_tasks[task_id] = proc

    outcome = "completed"
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        outcome = "timeout"
    finally:
        if task_id and running_tasks is not None and running_lock is not None:
            with running_lock:
                running_tasks.pop(task_id, None)

    if outcome == "completed" and proc.returncode is not None and proc.returncode < 0:
        outcome = "killed"

    duration = time.time() - start
    latest = workdir / ".tasksat" / "schedules" / tn_path.stem / "latest"
    diag = _read_diagnostics(latest)
    diag["outcome"] = outcome
    diag["returncode"] = proc.returncode
    diag["stdout_tail"] = _tail(stdout)
    diag["stderr_tail"] = _tail(stderr)
    diag.setdefault("durations", {}).setdefault("wall", round(duration, 3))

    if outcome == "timeout":
        diag["timed_out"] = True
        diag["status"] = "timeout"
    else:
        diag.setdefault("timed_out", False)
        if diag.get("status") is None:
            # No metadata written -> the verifier crashed before recording.
            diag["status"] = "error"
    return diag


def _read_diagnostics(latest_dir: Path) -> dict:
    """Assemble the diagnostics dict from the verifier's JSON artifacts."""
    diag = {"status": None, "durations": {}, "compositional": None,
            "realizability": None, "properties": [], "unsat_core": None}
    meta = _read_json(latest_dir / "metadata.json")
    if meta:
        diag["status"] = meta.get("status")
        d = diag["durations"]
        for src, dst in (("duration_sec", "total"),
                         ("validity_check_sec", "validity"),
                         ("property_check_sec", "property"),
                         ("compositional_check_sec", "compositional"),
                         ("realizability_check_sec", "realizability")):
            if meta.get(src) is not None:
                d[dst] = meta[src]
        diag["compositional"] = meta.get("compositional")
        diag["realizability"] = meta.get("realizability")
        if meta.get("error_message"):
            diag["error_message"] = meta["error_message"]
        if meta.get("num_violations") is not None:
            diag["num_violations"] = meta["num_violations"]
    props = _read_json(latest_dir / "properties.json")
    if isinstance(props, list):
        diag["properties"] = props
    for core_name in ("unsat_core.json", "compositional_unsat_core.json",
                      "realizability_unsat_core.json"):
        core = _read_json(latest_dir / core_name)
        if core:
            diag["unsat_core"] = {"file": core_name, **_core_summary(core)}
            break
    return diag


def _core_summary(core: dict) -> dict:
    """Keep the unsat core compact for the prompt (drop raw SMT formulas)."""
    if not isinstance(core, dict):
        return {"raw": str(core)[:500]}
    return {k: core[k] for k in ("empty", "core_size", "by_category", "analysis",
                                 "raw_core", "hint") if k in core}


def _read_json(path: Path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _tail(text: str, n: int = 25) -> str:
    lines = (text or "").strip().splitlines()
    return "\n".join(lines[-n:])


# ---------------------------------------------------------------------------
# Reference material for the LLM prompt (read at runtime, never hand-copied).
# ---------------------------------------------------------------------------

def build_reference() -> str:
    """Assemble authoritative TaskNet reference for the system prompt."""
    root = tasksat_root()
    parts = ["# TaskNet language reference\n"]

    grammar = _read_text(root / "website" / "docs" / "reference" / "grammar-formal.md")
    if grammar:
        parts.append("## Formal grammar (EBNF)\n" + _strip_frontmatter(grammar))

    manual = _read_text(root / "website" / "docs" / "reference" / "manual.md")
    if manual:
        sections = _extract_sections(
            manual, ("Session", "Compositional", "Rate Timeline", "Invariant",
                     "Initial and Final", "Final Block"))
        if sections:
            parts.append("## Relevant semantics (from the manual)\n" + sections)

    parts.append("## Modeling rules\n" + MODELING_RULES)

    examples = []
    for rel in ("tests/tasknet_files/examples/rover2.tn",
                "tests/tasknet_files/valid/tasknet62_compositional_holds.tn",
                "tests/tasknet_files/valid/tasknet59_session_basic.tn",
                "tests/tasknet_files/valid/tasknet20_rate_cumulative.tn"):
        txt = _read_text(root / rel)
        if txt:
            examples.append(f"### Example: {rel}\n```tasknet\n{txt.strip()}\n```")
    if examples:
        parts.append("## Example .tn files\n" + "\n\n".join(examples))

    return "\n\n".join(parts)


def _read_text(path: Path):
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _strip_frontmatter(md: str) -> str:
    if md.startswith("---"):
        end = md.find("\n---", 3)
        if end != -1:
            md = md[end + 4:]
    return md.strip()


def _extract_sections(md: str, keywords) -> str:
    """Return the ``##``/``###`` sections whose heading contains any keyword."""
    lines = md.splitlines()
    out, keep = [], False
    for line in lines:
        m = re.match(r"^(#{2,3})\s+(.*)$", line)
        if m:
            keep = any(k.lower() in m.group(2).lower() for k in keywords)
        if keep:
            out.append(line)
    return "\n".join(out).strip()


# ---------------------------------------------------------------------------
# LLM proposal (Anthropic; lazy import so the module loads without the SDK).
# ---------------------------------------------------------------------------

def propose_rewrite(source, diagnostics, reference, goal, history, model=DEFAULT_MODEL):
    """Ask the LLM for one rewrite of ``source``.

    Returns ``{"tn": <full rewritten .tn or None>, "rationale": <str>}``. Tests
    monkeypatch this function so the loop runs without an API key.
    """
    import anthropic  # lazy: only needed for a real proposal

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env
    system = (
        "You improve TaskSAT `.tn` scheduling specifications. You are given the "
        "language reference, the current spec, and verifier diagnostics. Propose ONE "
        "rewrite that advances the stated goal while preserving the spec's intent.\n\n"
        "Respond with a short rationale, then the COMPLETE rewritten spec in a single "
        "fenced code block:\n\nRATIONALE: <2-5 sentences>\n\n```tasknet\n<the entire "
        ".tn file>\n```\n\nThe code block must be a full, self-contained, parseable "
        ".tn file (not a diff).\n\n" + reference
    )
    user = _build_user_prompt(source, diagnostics, goal, history)
    msg = client.messages.create(
        model=model, max_tokens=8000, system=system,
        messages=[{"role": "user", "content": user}],
    )
    text = "".join(getattr(b, "text", "") for b in msg.content)
    return _extract_proposal(text)


def _build_user_prompt(source, diagnostics, goal, history) -> str:
    lines = [f"## Goal\n{goal}\n",
             "## Current spec\n```tasknet\n" + source.strip() + "\n```\n",
             "## Current diagnostics\n```json\n"
             + json.dumps(_diag_for_prompt(diagnostics), indent=2) + "\n```\n"]
    if history:
        lines.append("## Previous attempts (most recent last)")
        for h in history:
            verdict = (h.get("parse_error") or h.get("fidelity_error")
                       or _verdict_label(h.get("diagnostics")))
            lines.append(f"- iteration {h['iteration']}: {h.get('rationale','').strip()[:300]}"
                         f"\n  -> {verdict}")
    lines.append("\nPropose the next rewrite now.")
    return "\n".join(lines)


def _diag_for_prompt(diag) -> dict:
    """Trim diagnostics to what the LLM needs (drop long stdout/raw formulas)."""
    if not diag:
        return {}
    keep = {k: diag.get(k) for k in ("status", "timed_out", "compositional",
                                     "realizability", "durations", "num_violations")}
    keep["properties"] = [{"name": p.get("name"), "status": p.get("status")}
                          for p in diag.get("properties", [])]
    if diag.get("unsat_core"):
        keep["unsat_core"] = {k: diag["unsat_core"].get(k)
                              for k in ("by_category", "analysis", "hint")}
    if diag.get("stderr_tail") and diag.get("status") == "error":
        keep["error"] = diag["stderr_tail"]
    return keep


def _extract_proposal(text: str) -> dict:
    """Pull the fenced .tn block and rationale out of the model's reply."""
    m = re.search(r"```(?:tasknet|tn)?\s*\n(.*?)```", text, re.DOTALL)
    tn = m.group(1).strip() if m else None
    if m:
        rationale = (text[:m.start()] + text[m.end():]).strip()
    else:
        rationale = text.strip()
    rationale = re.sub(r"^RATIONALE:\s*", "", rationale, flags=re.IGNORECASE).strip()
    return {"tn": tn, "rationale": rationale}


# ---------------------------------------------------------------------------
# Validation, scoring, single iteration, driver.
# ---------------------------------------------------------------------------

def validate_rewrite(text):
    """Syntactic gate: parse (and round-trip) the candidate. Returns (ok, error)."""
    if not text or not text.strip():
        return False, "empty proposal (no .tn code block found)"
    try:
        tn = parse_tasknet(text)
        print_tasknet_to_string(tn)  # normalization / structural sanity
        return True, None
    except Exception as e:  # parser raises many exception types
        return False, f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# Fidelity guard: reject rewrites that keep declarations but gut the semantics.
#
# A rewrite that reaches HOLDS/success by deleting the hard parts is not a
# faithful improvement. Two subtle cheats seen in practice on the real MEXEC
# 199 model (see jpl/mexec/compositional/FINDINGS_199.md):
#   (a) keep a taskdef by NAME but zero its impact (`+~ -0.01` -> `+~ 0.0`), so
#       it stops touching the shared timeline the invariant is about;
#   (b) demote a REQUIRED `task` to a `request task`, so `--compositional`'s
#       single-session projection discards it from the proof entirely.
# The guard compares the candidate's AST to the original's and refuses either,
# on top of the plain no-deletion checks. Refusals are fed back to the LLM like
# a parse error (no solve), so the next turn must restructure rather than gut.
# ---------------------------------------------------------------------------

def _iter_all_tasks(tn):
    """Yield every Task/TaskRange node, descending into session children."""
    stack = list(tn.tasks)
    while stack:
        t = stack.pop()
        yield t
        stack.extend(getattr(t, "children", None) or [])


def _impact_is_active(imp) -> bool:
    """True unless the impact is a no-op (a zeroed delta / zeroed rate set)."""
    how = imp.how
    if isinstance(how, ImpactCumulative):
        return how.v != 0
    if isinstance(how, ImpactRateCumulative):
        return how.delta != 0
    if isinstance(how, ImpactRateAssignment):
        return how.r != 0
    if isinstance(how, ImpactAssign):
        return True  # a state/value assignment is meaningful
    return True


def _timeline_ids(tn) -> set:
    return {tl.id for tl in tn.timelines}


def _taskdef_names(tn) -> set:
    return {t.id for t in _iter_all_tasks(tn)
            if getattr(t, "kind", None) == TaskKind.DEFINITION}


def _taskdef_active_timelines(tn) -> dict:
    """{taskdef name -> set of timelines its OWN impacts actively touch}."""
    out = {}
    for t in _iter_all_tasks(tn):
        if getattr(t, "kind", None) != TaskKind.DEFINITION:
            continue
        active = {imp.id for imp in (t.impacts or []) if _impact_is_active(imp)}
        if active:
            out[t.id] = active
    return out


def _is_required(t) -> bool:
    """A required instantiation: a plain `task` (INSTANCE), or a range whose
    minimum is >= 1 and is not a request range. Optional/request do not count."""
    kind = getattr(t, "kind", None)
    if kind is not None:
        return kind == TaskKind.INSTANCE
    return getattr(t, "min_instances", 0) > 0 and not getattr(t, "is_request", False)


def _required_live_defs(tn) -> set:
    """Taskdefs exercised by at least one REQUIRED instantiation, following
    session children transitively (a required session makes its required
    children's taskdefs required-live too)."""
    defs = {t.id: t for t in _iter_all_tasks(tn)
            if getattr(t, "kind", None) == TaskKind.DEFINITION}
    live, stack = set(), []
    for t in tn.tasks:
        if _is_required(t) and getattr(t, "definition", None):
            stack.append(t.definition)
    while stack:
        name = stack.pop()
        if name in live:
            continue
        live.add(name)
        d = defs.get(name)
        if not d:
            continue
        for ch in (d.children or []):
            if _is_required(ch) and getattr(ch, "definition", None):
                stack.append(ch.definition)
    return live


def check_fidelity(original_source, candidate_source):
    """Guard against semantic-deletion cheats. Returns ``(ok, error_or_None)``.

    Both arguments must already be parseable (call after :func:`validate_rewrite`).
    Rejects a candidate that, relative to the original:

    - drops a declared timeline or taskdef;
    - keeps a taskdef by name but drops all of its active impact on a timeline it
      used to drive (impact zeroed or removed);
    - demotes a required taskdef to request/optional-only (so a compositional
      projection would discard it).
    """
    try:
        orig = parse_tasknet(original_source)
        cand = parse_tasknet(candidate_source)
    except Exception as e:  # original should parse; be defensive
        return True, None  # don't block on a parse hiccup the syntactic gate owns

    problems = []

    dropped_tl = _timeline_ids(orig) - _timeline_ids(cand)
    if dropped_tl:
        problems.append(f"dropped timeline(s): {sorted(dropped_tl)} — every timeline "
                        "in the original must remain declared")

    dropped_def = _taskdef_names(orig) - _taskdef_names(cand)
    if dropped_def:
        problems.append(f"dropped taskdef(s): {sorted(dropped_def)} — every taskdef "
                        "in the original must remain declared")

    orig_act, cand_act = _taskdef_active_timelines(orig), _taskdef_active_timelines(cand)
    for name, tls in orig_act.items():
        if name in dropped_def:
            continue  # already reported as a deletion
        lost = tls - cand_act.get(name, set())
        if lost:
            problems.append(
                f"taskdef `{name}` no longer actively impacts {sorted(lost)} "
                "(impact zeroed or removed) — keep its effect on the shared "
                "timeline, do not neutralize it to reach a verdict")

    demoted = _required_live_defs(orig) - _required_live_defs(cand)
    demoted -= dropped_def
    if demoted:
        problems.append(
            f"taskdef(s) demoted from required to request/optional-only or "
            f"un-instantiated: {sorted(demoted)} — a compositional projection "
            "would discard them; keep them scheduled as required")

    if problems:
        return False, ("fidelity violation (the rewrite keeps names but guts "
                       "the model): " + "; ".join(problems))
    return True, None


def _goal_wants_compositional(session) -> bool:
    flags = " ".join(session.get("verify_flags", []))
    return "--compositional" in flags or "compositional" in session.get("goal", "").lower()


def score(diagnostics, session):
    """Rank a result; higher is better. Returns (rank:int, -total_seconds:float)."""
    if not diagnostics or diagnostics.get("timed_out"):
        return (0, 0.0)
    dur = (diagnostics.get("durations") or {}).get("total")
    dur = dur if dur is not None else (diagnostics.get("durations") or {}).get("wall", 0.0)
    if _goal_wants_compositional(session):
        comp = (diagnostics.get("compositional") or "").lower()
        rank = {"holds": 5, "unknown": 2, "violated": 1}.get(comp, 0)
    else:
        rank = {"success": 4, "violated": 2, "unsat": 1}.get(diagnostics.get("status"), 0)
    return (rank, -float(dur))


def _goal_met(diagnostics, session) -> bool:
    return score(diagnostics, session)[0] >= (5 if _goal_wants_compositional(session) else 4)


def _verdict_label(diag) -> str:
    if not diag:
        return "no result"
    if diag.get("timed_out"):
        return "TIMEOUT"
    bits = [str(diag.get("status"))]
    if diag.get("compositional"):
        bits.append(f"compositional={diag['compositional']}")
    dur = (diag.get("durations") or {}).get("total")
    if dur is not None:
        bits.append(f"{dur}s")
    return ", ".join(bits)


def advise_once(session, timeout=120, proposer=None, reg=None):
    """Run ONE iteration in-place on ``session`` and return it.

    propose -> validate -> (if valid) write copy + verify -> score -> record.
    ``proposer`` defaults to :func:`propose_rewrite`; tests inject a mock. ``reg``
    is an optional ``{"task_id", "running_tasks", "running_lock"}`` dict forwarded
    to the verifier subprocess so the web UI can cancel it.
    """
    proposer = proposer or propose_rewrite
    reg = reg or {}
    k = len(session["history"])
    workdir = Path(session["workdir"])
    reference = session.get("_reference") or build_reference()

    proposal = proposer(session["original_source"], _current_diag(session),
                        reference, session["goal"], session["history"],
                        session.get("model", DEFAULT_MODEL))
    entry = {"iteration": k, "rationale": proposal.get("rationale", ""),
             "tn": proposal.get("tn"), "valid": False, "parse_error": None,
             "fidelity_error": None,
             "diagnostics": None, "attempt_path": None, "score": None,
             "diff": None, "timestamp": datetime.now().isoformat(timespec="seconds")}

    ok, err = validate_rewrite(proposal.get("tn"))
    if not ok:
        entry["parse_error"] = err
        session["history"].append(entry)
        _persist(session)
        return session

    if session.get("fidelity_guard", True):
        fok, ferr = check_fidelity(session["original_source"], proposal["tn"])
        if not fok:
            entry["fidelity_error"] = ferr
            session["history"].append(entry)
            _persist(session)
            return session

    entry["valid"] = True
    attempt = workdir / f"attempt_{k}.tn"
    attempt.write_text(proposal["tn"], encoding="utf-8")
    entry["attempt_path"] = str(attempt)
    entry["diff"] = _diff(session["original_source"], proposal["tn"],
                          Path(session["source_path"]).name, attempt.name)

    diag = run_verifier_capture(attempt, session.get("verify_flags"), timeout,
                                workdir=workdir / f"verify_{k}",
                                task_id=reg.get("task_id"),
                                running_tasks=reg.get("running_tasks"),
                                running_lock=reg.get("running_lock"))
    entry["diagnostics"] = diag
    entry["score"] = list(score(diag, session))
    session["history"].append(entry)

    best = session.get("best")
    if best is None or tuple(entry["score"]) > tuple(best["score"]):
        session["best"] = {"iteration": k, "attempt_path": str(attempt),
                           "score": entry["score"], "diagnostics": diag,
                           "tn": proposal["tn"]}
    _persist(session)
    return session


def _current_diag(session):
    """Diagnostics to show the LLM: the latest verified attempt, else baseline."""
    for h in reversed(session["history"]):
        if h.get("diagnostics"):
            return h["diagnostics"]
    return session.get("baseline")


def advise(path, goal, mode="step", max_iters=5, budget=300, verify_flags=None,
           model=DEFAULT_MODEL, out_dir=None, resume=None, feedback=None,
           timeout=120, proposer=None, reg=None, fidelity_guard=True):
    """Driver. Fresh session (baseline + iterate) or resume an existing one."""
    if resume:
        session = _read_json(Path(resume))
        if session is None:
            raise SystemExit(f"cannot read session: {resume}")
        if feedback:
            session.setdefault("feedback", []).append(feedback)
            # Surface feedback to the next proposal via a synthetic history note.
            session["history"].append({"iteration": len(session["history"]),
                                        "rationale": f"[user feedback] {feedback}",
                                        "tn": None, "valid": False,
                                        "parse_error": None, "diagnostics": None,
                                        "note": "feedback"})
    else:
        session = _new_session(path, goal, mode, verify_flags, model, out_dir,
                               timeout, proposer, fidelity_guard)

    session["_reference"] = session.get("_reference") or build_reference()

    if mode == "step":
        advise_once(session, timeout, proposer, reg)
        session["stop_reason"] = "step"
    else:
        start = time.time()
        while len(_verified_iters(session)) < max_iters and time.time() - start < budget:
            advise_once(session, timeout, proposer, reg)
            if session.get("best") and _goal_met(session["best"]["diagnostics"], session):
                session["stop_reason"] = "goal met"
                break
        else:
            session["stop_reason"] = ("max-iters" if len(_verified_iters(session)) >= max_iters
                                      else "budget")

    session.pop("_reference", None)
    write_report(session)
    _persist(session)
    return session


def _new_session(path, goal, mode, verify_flags, model, out_dir, timeout, proposer,
                 fidelity_guard=True):
    src = Path(path).resolve()
    original = src.read_text(encoding="utf-8")
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    workdir = Path(out_dir) if out_dir else (
        tasksat_root() / ".tasksat" / "advisor" / src.stem / stamp)
    workdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, workdir / src.name)  # keep an untouched copy of the original

    session = {"source_path": str(src), "stem": src.stem, "goal": goal, "mode": mode,
               "verify_flags": list(verify_flags or []), "model": model,
               "workdir": str(workdir), "original_source": original,
               "timestamp": stamp, "history": [], "best": None,
               "fidelity_guard": fidelity_guard,
               "stop_reason": None}
    baseline_flags = session["verify_flags"]
    session["baseline"] = run_verifier_capture(
        workdir / src.name, baseline_flags, timeout, workdir=workdir / "baseline")
    _persist(session)
    return session


def _verified_iters(session):
    return [h for h in session["history"] if h.get("diagnostics")]


def _persist(session):
    workdir = Path(session["workdir"])
    slim = {k: v for k, v in session.items() if not k.startswith("_")}
    (workdir / "session.json").write_text(json.dumps(slim, indent=2), encoding="utf-8")


def write_report(session):
    """Write report.json (machine) and report.md (human/web) for the session."""
    workdir = Path(session["workdir"])
    report = {k: session[k] for k in ("source_path", "stem", "goal", "mode",
                                      "verify_flags", "model", "timestamp",
                                      "baseline", "best", "stop_reason")}
    report["iterations"] = [{k: h.get(k) for k in ("iteration", "rationale",
                             "valid", "parse_error", "fidelity_error",
                             "attempt_path", "diagnostics",
                             "score", "diff", "note")} for h in session["history"]]
    (workdir / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (workdir / "report.md").write_text(_render_markdown(report), encoding="utf-8")
    return report


def _render_markdown(report) -> str:
    out = [f"# Advisor session: {report['stem']}", "",
           f"- **Goal:** {report['goal']}",
           f"- **Mode:** {report['mode']}  |  **Model:** {report['model']}",
           f"- **Verify flags:** `{' '.join(report['verify_flags']) or '(none)'}`",
           f"- **Baseline:** {_verdict_label(report['baseline'])}",
           f"- **Stop reason:** {report['stop_reason']}", ""]
    best = report.get("best")
    if best:
        out += [f"- **Best:** iteration {best['iteration']} — "
                f"{_verdict_label(best['diagnostics'])} "
                f"(`{Path(best['attempt_path']).name}`)", ""]
    out.append("## Iterations\n")
    for h in report["iterations"]:
        out.append(f"### Iteration {h['iteration']}")
        if h.get("note") == "feedback":
            out.append(f"_{h['rationale']}_\n"); continue
        if h.get("rationale"):
            out.append(h["rationale"] + "\n")
        if h.get("parse_error"):
            out.append(f"**Rejected (parse error):** `{h['parse_error']}`\n"); continue
        if h.get("fidelity_error"):
            out.append(f"**Rejected (fidelity guard):** {h['fidelity_error']}\n"); continue
        out.append(f"**Verdict:** {_verdict_label(h.get('diagnostics'))}\n")
        if h.get("diff"):
            out.append("```diff\n" + h["diff"].strip() + "\n```\n")
    return "\n".join(out)


def _diff(a, b, a_name, b_name) -> str:
    return "".join(difflib.unified_diff(
        a.splitlines(keepends=True), b.splitlines(keepends=True),
        fromfile=a_name, tofile=b_name))


def accept(session_path, out_path):
    """Copy the session's best attempt to ``out_path`` (never touches the original)."""
    session = _read_json(Path(session_path))
    if not session or not session.get("best"):
        raise SystemExit("no best attempt to accept in that session")
    shutil.copy2(session["best"]["attempt_path"], out_path)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None):
    p = argparse.ArgumentParser(description="LLM-assisted TaskNet advisor.")
    p.add_argument("tasknet_file", nargs="?", help="Path to .tn file")
    p.add_argument("--mode", choices=["step", "loop"], default="step")
    p.add_argument("--goal", default="Reduce verification time while preserving the "
                   "spec's intent; where sound, restructure into a uniform session "
                   "with an `invariant compositional { P }` so it checks N-independently.")
    p.add_argument("--verify-flags", default="",
                   help="Flags passed to the verifier, e.g. \"--compositional\".")
    p.add_argument("--max-iters", type=int, default=5)
    p.add_argument("--budget", type=float, default=300.0)
    p.add_argument("--timeout", type=float, default=120.0,
                   help="Per-verification wall-clock cap (seconds).")
    p.add_argument("--model", default=DEFAULT_MODEL)
    p.add_argument("--out", default=None, help="Working directory for this run.")
    p.add_argument("--continue", dest="resume", default=None,
                   help="Resume a session.json from a prior step-mode run.")
    p.add_argument("--feedback", default=None,
                   help="Feedback threaded into the next proposal (with --continue).")
    p.add_argument("--accept", default=None,
                   help="Copy the session's best attempt to this path and exit.")
    p.add_argument("--no-fidelity-guard", dest="fidelity_guard", action="store_false",
                   help="Disable the fidelity guard (allow rewrites that drop/neutralize "
                        "timelines/taskdefs or demote required tasks). On by default.")
    args = p.parse_args(argv)

    if args.accept and args.resume:
        dest = accept(args.resume, args.accept)
        print(f"Accepted best attempt -> {dest}")
        return

    verify_flags = args.verify_flags.split() if args.verify_flags else []
    session = advise(args.tasknet_file, args.goal, mode=args.mode,
                     max_iters=args.max_iters, budget=args.budget,
                     verify_flags=verify_flags, model=args.model, out_dir=args.out,
                     resume=args.resume, feedback=args.feedback, timeout=args.timeout,
                     fidelity_guard=args.fidelity_guard)
    _print_cli_summary(session)


def _print_cli_summary(session):
    print("\n" + SEP)
    print(f"Advisor session: {session['stem']}  (mode={session['mode']})")
    print(f"Workdir: {session['workdir']}")
    print(f"Baseline: {_verdict_label(session.get('baseline'))}")
    last = session["history"][-1] if session["history"] else None
    if last:
        print(SEP)
        print(f"Iteration {last['iteration']}:")
        if last.get("parse_error"):
            print(f"  REJECTED (parse error): {last['parse_error']}")
        elif last.get("fidelity_error"):
            print(f"  REJECTED (fidelity guard): {last['fidelity_error']}")
        else:
            if last.get("rationale"):
                print(f"  Rationale: {last['rationale'][:500]}")
            print(f"  Verdict:   {_verdict_label(last.get('diagnostics'))}")
            if last.get("attempt_path"):
                print(f"  Copy:      {last['attempt_path']}")
    best = session.get("best")
    if best:
        print(SEP)
        print(f"Best so far: iteration {best['iteration']} — "
              f"{_verdict_label(best['diagnostics'])}")
        print(f"  {best['attempt_path']}")
    if session["mode"] == "step":
        sp = Path(session["workdir"]) / "session.json"
        print(SEP)
        print("Step mode: evaluate the proposal above, then continue with:")
        print(f'  python src/smt/tasknet_advisor.py --continue "{sp}" '
              f'[--feedback "..."]')
        print(f'  python src/smt/tasknet_advisor.py --continue "{sp}" '
              f'--accept OUT.tn   # save the best attempt')
    print(SEP)
    print(f"Report: {Path(session['workdir']) / 'report.md'}")


if __name__ == "__main__":
    main()
