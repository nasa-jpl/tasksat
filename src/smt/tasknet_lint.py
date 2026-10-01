"""Static checks on a TaskNet that go beyond well-formedness.

Well-formedness is a type checker: names resolve, impacts suit their timelines,
conditions have the right shape. It says nothing about whether the network can be
scheduled. The solver answers that — but only if it finishes, and on the MEXEC
networks it does not: the 50-downlink `wp0-20` net exceeds a four-minute budget
without a verdict. Everything here runs on the AST in milliseconds, whatever the size.

Findings carry one of two severities, and keeping them apart is the point — a single
undifferentiated stream is how a linter gets ignored:

``Severity.PROVEN``
    No schedule exists, and no reading of the spec makes it acceptable. Established
    from the AST alone and sound under TaskSAT's semantics.

``Severity.ADVISORY``
    Something the spec cannot do, or does not say. May be deliberate.

**No rule currently emits PROVEN.** The one that did — `unsatisfiable-initial` — was
downgraded after the MEXEC review: a timeline that nothing writes may be managed
outside the plan (set by ground command), so "no task impacts it" can be correct and
deliberate rather than an omission. The analysis is still exact; what is uncertain is
whether the user considers it a defect, and that is not something severity should
assert on their behalf. ``PROVEN`` is kept for a rule that can — see
``_unsatisfiable_initial`` for the declaration that would restore it here.

Nothing here is fatal in any case. The solver remains the authority; this pass only
arrives sooner and says why, in the spec's own terms::

    from tasknet_lint import lint
    findings = lint(tn)
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from tasknet_ast import *


class Severity(Enum):
    """How much a finding can be trusted. See the module docstring."""

    PROVEN = "proven"
    ADVISORY = "advisory"


@dataclass
class LintFinding:
    """One lint result: a severity, the rule that produced it, and an explanation."""

    severity: Severity
    rule: str
    message: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.message}"

    def to_dict(self) -> dict:
        """JSON form, for the `lint.json` artifact the web UI reads."""
        return {'severity': self.severity.value, 'rule': self.rule,
                'message': self.message}


# ---------------------------------------------------------------------------
# Value domains
#
# A TlCon is a DISJUNCTION over its `cons` (see TaskNetSMT._con_holds_zone: "A
# TlCon is OR over such formulas"), so the values it admits are the union of what
# each Con admits. Two shapes cover every timeline kind:
#
#   ('set', frozenset)        state and atomic — finite, so membership is exact
#   ('interval', (lo, hi))    cumulative, rate, claimable — closed interval
#
# A union of intervals is approximated by its convex hull, which is sound for the
# only use made of it: a hull-disjointness test cannot report disjoint for sets
# that actually meet. None means "could not decide", and every rule below treats
# that as "say nothing".
# ---------------------------------------------------------------------------

Domain = Optional[Tuple[str, object]]


def _state_key(v) -> Optional[str]:
    """Normalize a condition value to the string a StateTimeline names it by.

    State names are strings even when they look numeric: `state(0, 1)` has states
    `['0', '1']` and initial `'0'`, while a condition on it parses as
    `ConVal(v=IntVal(v=1))`. Comparing those without normalizing silently never
    matches, which would make the PROVEN rule below miss its own motivating case.
    """
    if isinstance(v, StrVal):
        return str(v.v)
    if isinstance(v, (IntVal, RealVal)):
        return str(v.v)
    if isinstance(v, ParamRef):
        return str(v.name)
    return None


def _numeric(v) -> Optional[float]:
    if isinstance(v, (IntVal, RealVal)):
        return float(v.v)
    return None


def _is_discrete(tl: Timeline) -> bool:
    return isinstance(tl, (StateTimeline, AtomicTimeline))


def con_domain(tl: Timeline, con: Con) -> Domain:
    """What values of `tl` a single Con admits, or None if undecidable."""
    if isinstance(con, ConVal):
        if _is_discrete(tl):
            k = _state_key(con.v)
            return ('set', frozenset({k})) if k is not None else None
        x = _numeric(con.v)
        return ('interval', (x, x)) if x is not None else None
    r = getattr(con, 'r', None)
    if r is not None and getattr(r, 'low', None) is not None:
        lo, hi = float(r.low), float(r.high)
        if _is_discrete(tl):
            # An integer range over a finite domain: enumerate the states it covers.
            return ('set', frozenset(str(s) for s in _states(tl)
                                     if _as_float(s) is not None
                                     and lo <= _as_float(s) <= hi))
        return ('interval', (lo, hi))
    return None


def _states(tl: Timeline) -> List[str]:
    if isinstance(tl, StateTimeline):
        return [str(s) for s in tl.states]
    return ['0', '1']            # atomic


def _as_float(s) -> Optional[float]:
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


def tlcon_domain(tl: Timeline, tlcon: TlCon) -> Domain:
    """The union over `tlcon.cons`. None if ANY disjunct is undecidable.

    Undecidable-means-give-up is deliberate: an unreadable disjunct could admit
    anything, so a union computed without it would be too small, and every rule
    here draws its conclusion from a domain being too small.
    """
    parts = [con_domain(tl, c) for c in (tlcon.cons or [])]
    if not parts or any(p is None for p in parts):
        return None
    if all(p[0] == 'set' for p in parts):
        out: Set[str] = set()
        for _, s in parts:
            out |= s
        return ('set', frozenset(out))
    if all(p[0] == 'interval' for p in parts):
        los = [p[1][0] for p in parts]
        his = [p[1][1] for p in parts]
        return ('interval', (min(los), max(his)))
    return None


def domains_disjoint(a: Domain, b: Domain) -> bool:
    """True only when the two provably cannot both hold of one value."""
    if a is None or b is None:
        return False
    if a[0] == 'set' and b[0] == 'set':
        return not (a[1] & b[1])
    if a[0] == 'interval' and b[0] == 'interval':
        (alo, ahi), (blo, bhi) = a[1], b[1]
        return ahi < blo or bhi < alo
    return False


def initial_admitted(tl: Timeline, dom: Domain) -> Optional[bool]:
    """Does `tl`'s declared initial value lie in `dom`? None if undecidable."""
    if dom is None:
        return None
    if dom[0] == 'set':
        return str(tl.initial) in dom[1]
    x = _as_float(tl.initial)
    if x is None:
        return None
    lo, hi = dom[1]
    return lo <= x <= hi


# ---------------------------------------------------------------------------
# The checker
# ---------------------------------------------------------------------------

CONDITION_FIELDS = ('pre', 'inv', 'post')


class Linter:
    """Runs every rule over one network and collects the findings."""

    def __init__(self, tn: TaskNet):
        self.tn = tn
        self.findings: List[LintFinding] = []
        self.timelines: Dict[str, Timeline] = {tl.id: tl for tl in tn.timelines}

        # Writers are collected over ALL tasks, taskdefs included. A taskdef's
        # impacts are inherited by its instances, so an impact declared only on a
        # definition still writes the timeline; ignoring definitions would report
        # a timeline unwritable when in fact every instance writes it.
        self.writers: Dict[str, Set[str]] = {}
        for t in tn.tasks:
            for imp in (t.impacts or []):
                self.writers.setdefault(imp.id, set()).add(t.id)

        # (task_id, field, tlcon) for every condition mentioning a timeline.
        self.readers: Dict[str, List[Tuple[str, str, TlCon]]] = {}
        for t in tn.tasks:
            for fld in CONDITION_FIELDS:
                for c in (getattr(t, fld, None) or []):
                    self.readers.setdefault(c.id, []).append((t.id, fld, c))
        for src, kind in ((tn.initial_constraints, 'initial'),
                          (tn.final_constraints, 'final')):
            for c in (src or []):
                self.readers.setdefault(c.id, []).append(('<tasknet>', kind, c))

    def run(self) -> List[LintFinding]:
        self.findings = []
        self._unsatisfiable_initial()
        self._unsupported_transition()
        self._unused_timeline()
        self._no_op_impact()
        return self.findings

    def _add(self, sev: Severity, rule: str, message: str):
        self.findings.append(LintFinding(sev, rule, message))

    # ----- PROVEN -----

    def _unsatisfiable_initial(self):
        """A timeline no impact writes, whose initial value fails a condition on it.

        With no impact on `T`, every zone holds `T`'s initial value, so a condition
        that value fails can never hold and the task is unschedulable *as modelled*.
        Unlike the per-taskdef rules this quantifies over the WHOLE network, so no
        other task can be the missing writer.

        ADVISORY nonetheless, and the reason is a real modelling pattern rather than a
        gap in the analysis. A timeline may be managed OUTSIDE the plan — set by ground
        command before execution — in which case having no task impact it is correct
        and deliberate, and the spec is merely silent about who owns it. That is the
        finding: not "this model is wrong" but "nothing in this model can make this
        true". Which of the two it is depends on information the spec does not carry.

        This is exactly what happened on the MEXEC wp0-20 networks: the rule found
        `opsci_enabled` (required `= 1`, declared `0`, written by nothing), and the
        answer was that the ground system owns it. See
        jpl/mexec/debug/WP0_20_FINDINGS.md observation D, which proposes declaring such
        timelines explicitly. If TaskSAT grows that declaration, an UNDECLARED
        never-written timeline becomes a genuine error again and this can be promoted.
        """
        for tl_id, reads in sorted(self.readers.items()):
            tl = self.timelines.get(tl_id)
            if tl is None or tl_id in self.writers:
                continue
            for task_id, fld, tlcon in reads:
                dom = tlcon_domain(tl, tlcon)
                if initial_admitted(tl, dom) is False:
                    self._add(
                        Severity.ADVISORY, 'unsatisfiable-initial',
                        f"timeline '{tl_id}' is written by no impact anywhere, so it "
                        f"holds its initial value {tl.initial!r} for the whole plan — "
                        f"but '{task_id}' requires {_show(dom)} in its {fld}. Nothing "
                        f"in this spec can schedule '{task_id}'; if '{tl_id}' is set "
                        f"outside the plan, the spec does not say so.")

    # ----- ADVISORY -----

    def _unsupported_transition(self):
        """A taskdef whose `pre` and `inv` on one timeline are disjoint, with no impact.

        The task demands a change it does not itself cause. ADVISORY, not PROVEN:
        another task may overlap and supply the value. This is the rule
        jpl/mexec/debug/debug1/find_missing_impacts.py applies to the XML.
        """
        for t in self.tn.tasks:
            impacted = {imp.id for imp in (t.impacts or [])}
            pre = {c.id: c for c in (t.pre or [])}
            inv = {c.id: c for c in (t.inv or [])}
            for tl_id in sorted(set(pre) & set(inv)):
                tl = self.timelines.get(tl_id)
                if tl is None or tl_id in impacted:
                    continue
                a, b = tlcon_domain(tl, pre[tl_id]), tlcon_domain(tl, inv[tl_id])
                if domains_disjoint(a, b):
                    self._add(
                        Severity.ADVISORY, 'unsupported-transition',
                        f"'{t.id}' requires {tl_id} {_show(a)} at start and "
                        f"{_show(b)} throughout, with no impact of its own on "
                        f"{tl_id}. Needs an impact, or a task guaranteed to overlap "
                        f"and supply it.")

    def _unused_timeline(self):
        """Declared, then neither read by a condition nor written by an impact."""
        for tl in self.tn.timelines:
            if tl.id not in self.writers and tl.id not in self.readers:
                self._add(Severity.ADVISORY, 'unused-timeline',
                          f"timeline '{tl.id}' is declared but never read or written.")

    def _no_op_impact(self):
        """An impact that changes nothing — `+= 0` or `+~ 0`.

        Harmless to the solver, but it is how an unfilled number looks: ten of the
        sixteen battery impacts in the MEXEC nets are `battery_soc +~ 0`, including
        every preheat, whose whole purpose is to draw power.
        """
        for t in self.tn.tasks:
            for imp in (t.impacts or []):
                d = getattr(imp.how, 'v', getattr(imp.how, 'delta', None))
                if isinstance(d, (int, float)) and d == 0:
                    self._add(Severity.ADVISORY, 'no-op-impact',
                              f"'{t.id}' has an impact on '{imp.id}' of 0, which "
                              f"changes nothing.")


def _show(dom: Domain) -> str:
    if dom is None:
        return '?'
    if dom[0] == 'set':
        return '= ' + ' | '.join(sorted(dom[1]))
    lo, hi = dom[1]
    return f"= {lo:g}" if lo == hi else f"in [{lo:g}, {hi:g}]"


def lint(tn: TaskNet) -> List[LintFinding]:
    """Run every rule over `tn` and return the findings, worst severity first."""
    out = Linter(tn).run()
    return sorted(out, key=lambda f: (f.severity != Severity.PROVEN, f.rule, f.message))


def report(findings: List[LintFinding], quiet_if_clean: bool = True) -> int:
    """Print `findings` grouped by severity. Returns the number of PROVEN ones.

    Silent when there is nothing to say, since lint runs on every verification and a
    banner announcing no findings is just noise between the user and their schedule.
    `quiet_if_clean=False` forces the section, which `--lint-only` needs — there, the
    report IS the output, and printing nothing would look like a failure.
    """
    from color_utils import error, warning, success, bold, dim

    if not findings and quiet_if_clean:
        return 0

    proven = [f for f in findings if f.severity is Severity.PROVEN]
    advisory = [f for f in findings if f.severity is Severity.ADVISORY]

    print("\n" + "=" * 70)
    print(bold("LINT"))
    print("=" * 70)

    if not findings:
        print(success("\nNo findings.\n"))
        return 0

    if proven:
        print(error(bold(f"\n{len(proven)} proven unschedulable "
                         f"(no solver needed, no false positives):")))
        for i, f in enumerate(proven, 1):
            print(error(f"  {i}. {f}"))
    if advisory:
        print(warning(bold(f"\n{len(advisory)} advisory (may be deliberate):")))
        for i, f in enumerate(advisory, 1):
            print(warning(f"  {i}. {f}"))
    print(dim("\nLint never blocks a run; the solver remains the authority.\n"))
    return len(proven)
