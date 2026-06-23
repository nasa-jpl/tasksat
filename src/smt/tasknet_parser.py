from __future__ import annotations
from typing import List, Optional
from pprint import pprint

import ply.lex as lex
import ply.yacc as yacc

from tasknet_ast import *
from tasknet_ast import TaskKind


# ============================================================
# 1. LEXER
# ============================================================

reserved = {
    "tasknet":        "TASKNET",
    "timelines":      "TIMELINES",
    "initial":        "INITIAL",
    "initial_rate":   "INITIAL_RATE",
    "task":           "TASK",
    "taskdef":        "TASKDEF",
    "optional":       "OPTIONAL",
    "request":        "REQUEST",
    "end":            "END",
    "id":             "ID_KW",
    "priority":       "PRIORITY",
    "start_range":    "START_RANGE",
    "end_range":      "END_RANGE",
    "duration_range": "DURATION_RANGE",
    "duration":       "DURATION",
    "start":          "START_KW",
    "after":          "AFTER",
    "containedin":    "CONTAINEDIN",
    # task-local constraints + impacts
    "constraints": "CONSTRAINTS",
    "impacts":     "IMPACTS",
    "pre":         "PRE",
    "maint":       "MAINT",
    "post":        "POST",
    "inv":         "INV",
    "in":          "IN",
    # timelines
    "state":       "STATE",
    "atomic":      "ATOMIC",
    "claim":       "CLAIM",
    "claimable":   "CLAIMABLE",
    "cumul":       "CUMUL",
    "cumulative":  "CUMULATIVE",
    "rate":        "RATE",
    "bounds":      "BOUNDS",
    # booleans
    "true":        "TRUE",
    "false":       "FALSE",
    # TL props
    "prop":        "PROP",
    "properties":  "PROPERTIES",
    # temporal logic
    "always":      "ALWAYS",
    "eventually":  "EVENTUALLY",
    "sofar":       "SOFAR",
    "once":        "ONCE",
    "until":       "UNTIL",
    "since":       "SINCE",
    "not":         "NOT",
    "and":         "AND",
    "or":          "OR",
    "implies":     "IMPLIES_KW",
    # task predicates
    "active":      "ACTIVE",
    "time":        "TIME",
    # sequencing
    "sequence":    "SEQUENCE",
}

tokens = [
    "NAME",
    "NUMBER",
    "STRING",
    "LBRACE",
    "RBRACE",
    "LPAREN",
    "RPAREN",
    "LBRACKET",
    "RBRACKET",
    "COLON",
    "SEMI",
    "COMMA",
    "DOT",
    "EQ",
    "PLUS_EQ",
    "MINUS_EQ",
    "PLUS_RATE",
    "MINUS_RATE",
    "ASSIGN_RATE",
    "GE",
    "LE",
    "GT",
    "LT",
    "IMPLIES",
] + list(set(reserved.values()))

t_LBRACE    = r"\{"
t_RBRACE    = r"\}"
t_LPAREN    = r"\("
t_RPAREN    = r"\)"
t_LBRACKET  = r"\["
t_RBRACKET  = r"\]" 
t_COLON     = r":"
t_SEMI      = r";"
t_COMMA     = r","
t_DOT       = r"\."
t_PLUS_EQ   = r"\+="
t_MINUS_EQ  = r"-="
t_PLUS_RATE = r"\+~"
t_MINUS_RATE= r"-~"
t_ASSIGN_RATE= r"=~"
t_GE        = r">="
t_LE        = r"<="
t_GT        = r">"
t_LT        = r"<"
t_EQ        = r"="
t_IMPLIES   = r"->"

t_ignore = " \t\r"


def t_COMMENT(t):
    r"(\#|//)[^\n]*"
    pass


def t_NEWLINE(t):
    r"\n+"
    t.lexer.lineno += len(t.value)


def t_STRING(t):
    r"\"([^\"\\]|\\.)*\""
    s = t.value[1:-1]
    s = s.replace(r"\\", "\\").replace(r"\"", "\"")
    t.value = s
    return t


def t_NUMBER(t):
    r"-?\d+(\.\d+)?"
    t.value = float(t.value)
    return t


def t_NAME(t):
    r"[A-Za-z_][A-Za-z_0-9]*"
    t.type = reserved.get(t.value, "NAME")
    return t


def t_error(t):
    raise SyntaxError(f"Illegal character {t.value[0]!r} at line {t.lexer.lineno}")


lexer = lex.lex()


# ============================================================
# 2. PARSER
# ============================================================

def p_empty(p):
    "empty :"
    pass


# ------------ start ------------

def p_start(p):
    "start : tasknet"
    p[0] = p[1]


# ------------ tasknet ------------

def p_tasknet(p):
    "tasknet : TASKNET NAME LBRACE tasknet_body_items RBRACE"
    name = p[2]
    items = p[4]

    end_time: int | None = None
    timelines: List[Timeline] = []
    tasks: List[Task] = []
    init_cons: List[TlCon] = [] 
    constraints_tl: List[TemporalProperty] = []
    properties: List[TemporalProperty] = []

    for kind, value in items:
        if kind == "end":
            end_time = value
        elif kind == "timelines":
            timelines = value
        elif kind == "task":
            tasks.append(value)
        elif kind == "initial":
            init_cons.extend(value)
        elif kind == "constraints_tl":
            constraints_tl.extend(value)
        elif kind == "properties":
            properties.extend(value)
        else:
            raise ValueError(f"Unknown tasknet_body_item kind: {kind!r}")

    if end_time is None:
        raise ValueError("Missing 'end = ...;' declaration in tasknet")

    p[0] = TaskNet(
        id=name,
        timelines=timelines,
        tasks=tasks,
        endTime=end_time,
        initial_constraints=init_cons,
        constraints=constraints_tl,
        properties=properties,
    )


def p_tasknet_body_items_single(p):
    "tasknet_body_items : tasknet_body_item"
    p[0] = [p[1]]


def p_tasknet_body_items_many(p):
    "tasknet_body_items : tasknet_body_items tasknet_body_item"
    p[0] = p[1] + [p[2]]


def p_tasknet_body_item_end(p):
    "tasknet_body_item : end_decl"
    p[0] = ("end", p[1])


def p_tasknet_body_item_timelines(p):
    "tasknet_body_item : timelines_block"
    p[0] = ("timelines", p[1])

def p_tasknet_body_item_initial(p):
    "tasknet_body_item : initial_block"
    p[0] = ("initial", p[1])

def p_tasknet_body_item_task(p):
    "tasknet_body_item : task_def"
    p[0] = ("task", p[1])


def p_tasknet_body_item_constraints_tl(p):
    "tasknet_body_item : constraints_tl_block"
    p[0] = ("constraints_tl", p[1])


def p_tasknet_body_item_properties(p):
    "tasknet_body_item : properties_block"
    p[0] = ("properties", p[1])


def p_end_decl(p):
    "end_decl : END EQ NUMBER SEMI"
    p[0] = int(p[3])


# ------------ timelines ------------

def p_timelines_block(p):
    "timelines_block : TIMELINES LBRACE timeline_decl_list RBRACE"
    p[0] = p[3]


def p_timeline_decl_list_empty(p):
    "timeline_decl_list : empty"
    p[0] = []


def p_timeline_decl_list_nonempty(p):
    "timeline_decl_list : timeline_decl_list timeline_decl"
    p[0] = p[1] + [p[2]]


def p_timeline_decl_list_single(p):
    "timeline_decl_list : timeline_decl"
    p[0] = [p[1]]


def p_timeline_decl(p):
    "timeline_decl : NAME COLON timeline_kind SEMI"
    name = p[1]
    tl = p[3]
    tl.id = name
    p[0] = tl


def p_timeline_kind_state_name(p):
    "timeline_kind : STATE LPAREN state_list RPAREN EQ NAME"
    states = p[3]
    initial = p[6]
    p[0] = StateTimeline(id=None, states=states, initial=initial)


def p_timeline_kind_state_number(p):
    "timeline_kind : STATE LPAREN state_list RPAREN EQ NUMBER"
    states = p[3]
    initial = str(int(p[6])) if float(p[6]).is_integer() else str(p[6])
    p[0] = StateTimeline(id=None, states=states, initial=initial)


def p_state_list_single_name(p):
    "state_list : NAME"
    p[0] = [p[1]]


def p_state_list_single_number(p):
    "state_list : NUMBER"
    p[0] = [str(int(p[1])) if float(p[1]).is_integer() else str(p[1])]


def p_state_list_many_name(p):
    "state_list : state_list COMMA NAME"
    p[0] = p[1] + [p[3]]


def p_state_list_many_number(p):
    "state_list : state_list COMMA NUMBER"
    num_str = str(int(p[3])) if float(p[3]).is_integer() else str(p[3])
    p[0] = p[1] + [num_str]

def p_timeline_kind_atomic(p):
    "timeline_kind : ATOMIC init_int_opt"
    p[0] = AtomicTimeline(id=None, initial=p[2])


def p_claim_kw(p):
    "claim_kw : CLAIM"
    p[0] = "claim"


def p_claim_kw_alt(p):
    "claim_kw : CLAIMABLE"
    p[0] = "claimable"


def p_cumul_kw(p):
    "cumul_kw : CUMUL"
    p[0] = "cumul"


def p_cumul_kw_alt(p):
    "cumul_kw : CUMULATIVE"
    p[0] = "cumulative"


def p_range(p):
    "range : LBRACKET NUMBER COMMA NUMBER RBRACKET"
    p[0] = (float(p[2]), float(p[4]))


def p_range_opt_empty(p):
    "range_opt : empty"
    p[0] = None


def p_range_opt_some(p):
    "range_opt : range"
    p[0] = p[1]


def p_bounds_opt_empty(p):
    "bounds_opt : empty"
    p[0] = None


def p_bounds_opt_some(p):
    "bounds_opt : BOUNDS range"
    p[0] = p[2]


def p_init_opt_empty(p):
    "init_opt : empty"
    p[0] = None


def p_init_opt_some(p):
    "init_opt : EQ NUMBER"
    p[0] = float(p[2])


def p_initial_rate_opt_empty(p):
    "initial_rate_opt : empty"
    p[0] = None


def p_initial_rate_opt_some(p):
    "initial_rate_opt : INITIAL_RATE EQ NUMBER"
    p[0] = float(p[3])


def p_init_int_opt_empty(p):
    "init_int_opt : empty"
    p[0] = 0  # Default to 0

def p_init_int_opt_some(p):
    "init_int_opt : EQ NUMBER"
    val = int(p[2])
    if val not in (0, 1):
        print(f"Error: Atomic timeline initialization must be 0 or 1, got {val}")
        raise SyntaxError(f"Invalid atomic timeline initial value: {val}")
    p[0] = val




def p_timeline_kind_claimlike(p):
    "timeline_kind : claim_kw range_opt init_opt"
    _kw = p[1]
    rng = p[2]
    init = p[3]
    BIG = 1e9

    if rng is None:
        lo, hi = 0.0, BIG
    else:
        lo, hi = rng

    init_val = None if init is None else float(init)

    p[0] = ClaimableTimeline(
        id=None,
        range=RealRange(lo, hi),
        initial=init_val, # <-- None means unconstrained
    )

def p_timeline_kind_cumul(p):
    "timeline_kind : cumul_kw range_opt bounds_opt init_opt"
    _kw = p[1]
    rng = p[2]
    bnds = p[3]
    init = p[4]
    BIG = 1e9

    if rng is None:
        r_lo, r_hi = 0.0, BIG
    else:
        r_lo, r_hi = rng

    # Don't default bounds to range - they should be independent
    bounds_val = None if bnds is None else RealRange(bnds[0], bnds[1])

    init_val = None if init is None else float(init)

    p[0] = CumulativeTimeline(
        id=None,
        range=RealRange(r_lo, r_hi),
        bounds=bounds_val,  # None unless explicitly specified
        initial=init_val,          # <-- None means unconstrained
    )

def p_timeline_kind_rate(p):
    "timeline_kind : RATE range_opt bounds_opt init_opt initial_rate_opt"
    rng = p[2]
    bnds = p[3]
    init = p[4]
    init_rate = p[5]
    BIG = 1e9

    if rng is None:
        r_lo, r_hi = 0.0, BIG
    else:
        r_lo, r_hi = rng

    # Don't default bounds to range - they should be independent
    bounds_val = None if bnds is None else RealRange(bnds[0], bnds[1])

    init_val = None if init is None else float(init)
    init_rate_val = None if init_rate is None else float(init_rate)

    p[0] = RateTimeline(
        id=None,
        range=RealRange(r_lo, r_hi),
        bounds=bounds_val,  # None unless explicitly specified
        initial=init_val,          # <-- None means unconstrained
        initial_rate=init_rate_val,
    )

# ------------ initial timeline values ------------

def p_initial_block(p):
    "initial_block : INITIAL LBRACE tlcon_list RBRACE"
    p[0] = p[3]  # list[TlCon]

# ------------ tasks ------------

def p_task_def_taskdef(p):
    "task_def : TASKDEF NAME LBRACE task_body_items RBRACE"
    p[0] = _build_task(p[2], p[4], kind=TaskKind.DEFINITION, definition=None)

def p_task_def_task_with_body(p):
    "task_def : task_modifier_opt TASK NAME extends_opt LBRACE task_body_items RBRACE"
    modifier = p[1]  # "optional", "request", or None
    name = p[3]
    extends = p[4]  # None or definition name
    items = p[6]

    if modifier == "optional":
        kind = TaskKind.OPTIONAL
    elif modifier == "request":
        kind = TaskKind.REQUEST
    else:
        kind = TaskKind.INSTANCE

    p[0] = _build_task(name, items, kind=kind, definition=extends)

def p_task_def_task_no_body(p):
    "task_def : task_modifier_opt TASK NAME extends_opt SEMI"
    modifier = p[1]  # "optional", "request", or None
    name = p[3]
    extends = p[4]  # None or definition name
    items = []

    if modifier == "optional":
        kind = TaskKind.OPTIONAL
    elif modifier == "request":
        kind = TaskKind.REQUEST
    else:
        kind = TaskKind.INSTANCE

    p[0] = _build_task(name, items, kind=kind, definition=extends)

def p_task_modifier_opt_none(p):
    "task_modifier_opt : empty"
    p[0] = None

def p_task_modifier_opt_optional(p):
    "task_modifier_opt : OPTIONAL"
    p[0] = "optional"

def p_task_modifier_opt_request(p):
    "task_modifier_opt : REQUEST"
    p[0] = "request"

def p_extends_opt_none(p):
    "extends_opt : empty"
    p[0] = None

def p_extends_opt_some(p):
    "extends_opt : COLON NAME"
    p[0] = p[2]

def _build_task(name: str, items: List, kind: TaskKind, definition: Optional[str]) -> Task:
    """Helper function to build a Task from parsed items"""
    ident = None
    priority = None
    startrng = None
    endrng = None
    durrng = None
    dur = None
    start = None
    after_instances = None
    after_definitions = None
    containedin_instances = None
    containedin_definitions = None
    pre = None
    inv = None
    post = None
    impacts = None

    # Extract values from items
    after_instances_list: List[str] = []
    after_definitions_list: List[str] = []
    containedin_instances_list: List[str] = []
    containedin_definitions_list: List[str] = []
    pre_list: List[TlCon] = []
    inv_list: List[TlCon] = []
    post_list: List[TlCon] = []
    impacts_list: List[Impact] = []

    for item_kind, value in items:
        if item_kind == "id":
            ident = value
        elif item_kind == "priority":
            priority = value
        elif item_kind == "start_range":
            startrng = value
        elif item_kind == "end_range":
            endrng = value
        elif item_kind == "duration_range":
            durrng = value
        elif item_kind == "duration":
            dur = value
        elif item_kind == "start":
            start = value
        elif item_kind == "after":
            if kind == TaskKind.DEFINITION:
                after_definitions_list.extend(value)
            else:  # INSTANCE or OPTIONAL
                after_instances_list.extend(value)
        elif item_kind == "containedin":
            if kind == TaskKind.DEFINITION:
                containedin_definitions_list.extend(value)
            else:  # INSTANCE or OPTIONAL
                containedin_instances_list.extend(value)
        elif item_kind == "constraints":
            pre_c, inv_c, post_c = value
            pre_list.extend(pre_c)
            inv_list.extend(inv_c)
            post_list.extend(post_c)
        elif item_kind == "pre":
            pre_list.extend(value)
        elif item_kind == "inv":
            inv_list.extend(value)
        elif item_kind == "post":
            post_list.extend(value)
        elif item_kind == "impacts":
            impacts_list.extend(value)
        else:
            raise ValueError(f"Unknown task_body_item kind: {item_kind!r}")

    # Set optional fields if they have values
    if after_instances_list:
        after_instances = after_instances_list
    if after_definitions_list:
        after_definitions = after_definitions_list
    if containedin_instances_list:
        containedin_instances = containedin_instances_list
    if containedin_definitions_list:
        containedin_definitions = containedin_definitions_list
    if pre_list:
        pre = pre_list
    if inv_list:
        inv = inv_list
    if post_list:
        post = post_list
    if impacts_list:
        impacts = impacts_list

    # Set default ident if not specified
    if ident is None:
        ident = 0

    return Task(
        id=name,
        ident=ident,
        kind=kind,
        definition=definition,
        priority=priority,
        startrng=startrng,
        endrng=endrng,
        durrng=durrng,
        dur=dur,
        start=start,
        after_instances=after_instances,
        after_definitions=after_definitions,
        containedin_instances=containedin_instances,
        containedin_definitions=containedin_definitions,
        pre=pre,
        inv=inv,
        post=post,
        impacts=impacts,
    )


def p_task_body_items_empty(p):
    "task_body_items : empty"
    p[0] = []


def p_task_body_items_single(p):
    "task_body_items : task_body_item"
    p[0] = [p[1]]


def p_task_body_items_many(p):
    "task_body_items : task_body_items task_body_item"
    p[0] = p[1] + [p[2]]


def p_task_body_item_id(p):
    "task_body_item : task_id"
    p[0] = ("id", p[1])


def p_task_body_item_priority(p):
    "task_body_item : task_priority"
    p[0] = ("priority", p[1])


def p_task_body_item_start_range(p):
    "task_body_item : task_start_range"
    p[0] = ("start_range", p[1])


def p_task_body_item_end_range(p):
    "task_body_item : task_end_range"
    p[0] = ("end_range", p[1])


def p_task_body_item_duration_range(p):
    "task_body_item : task_duration_range"
    p[0] = ("duration_range", p[1])


def p_task_body_item_duration(p):
    "task_body_item : task_duration"
    p[0] = ("duration", p[1])


def p_task_body_item_start_opt(p):
    "task_body_item : task_start_opt"
    p[0] = ("start", p[1])


def p_task_body_item_after(p):
    "task_body_item : task_after"
    p[0] = ("after", p[1])


def p_task_body_item_containedin(p):
    "task_body_item : task_containedin"
    p[0] = ("containedin", p[1])


def p_task_body_item_constraints_block(p):
    "task_body_item : constraints_block"
    p[0] = ("constraints", p[1])


def p_task_body_item_pre_block(p):
    "task_body_item : pre_block"
    tag, tlcons = p[1]
    p[0] = (tag, tlcons)


def p_task_body_item_inv_block(p):
    "task_body_item : inv_block"
    tag, tlcons = p[1]
    p[0] = (tag, tlcons)


def p_task_body_item_post_block(p):
    "task_body_item : post_block"
    tag, tlcons = p[1]
    p[0] = (tag, tlcons)


def p_task_body_item_impacts(p):
    "task_body_item : task_impacts"
    p[0] = ("impacts", p[1])


def p_task_id(p):
    "task_id : ID_KW NUMBER SEMI"
    p[0] = int(p[2])


def p_task_priority(p):
    "task_priority : PRIORITY NUMBER SEMI"
    p[0] = int(p[2])


def p_task_start_range(p):
    "task_start_range : START_RANGE range SEMI"
    lo, hi = p[2]
    p[0] = IntRange(int(lo), int(hi))


def p_task_end_range(p):
    "task_end_range : END_RANGE range SEMI"
    lo, hi = p[2]
    p[0] = IntRange(int(lo), int(hi))


def p_task_duration_range(p):
    "task_duration_range : DURATION_RANGE range SEMI"
    lo, hi = p[2]
    p[0] = IntRange(int(lo), int(hi))


def p_task_duration(p):
    "task_duration : DURATION NUMBER SEMI"
    p[0] = int(p[2])


def p_task_start_opt_some(p):
    "task_start_opt : START_KW NUMBER SEMI"
    p[0] = int(p[2])


def p_task_start_opt_empty(p):
    "task_start_opt : empty"
    p[0] = 0


def p_task_after(p):
    "task_after : AFTER name_list SEMI"
    p[0] = p[2]


def p_task_containedin(p):
    "task_containedin : CONTAINEDIN name_list SEMI"
    p[0] = p[2]


def p_name_list_empty(p):
    "name_list : empty"
    p[0] = []


def p_name_list_single(p):
    "name_list : NAME"
    p[0] = [p[1]]


def p_name_list_many(p):
    "name_list : name_list COMMA NAME"
    p[0] = p[1] + [p[3]]


# ------------ task constraints (pre/inv/post) ------------

def p_constraints_block(p):
    "constraints_block : CONSTRAINTS LBRACE constraints_items RBRACE"
    pre_list: List[TlCon] = []
    inv_list: List[TlCon] = []
    post_list: List[TlCon] = []
    for tag, tlcons in p[3]:
        if tag == "pre":
            pre_list.extend(tlcons)
        elif tag == "inv":
            inv_list.extend(tlcons)
        elif tag == "post":
            post_list.extend(tlcons)
        else:
            raise ValueError(f"Unknown constraints_item tag: {tag!r}")
    p[0] = (pre_list, inv_list, post_list)


def p_constraints_items_empty(p):
    "constraints_items : empty"
    p[0] = []


def p_constraints_items_single(p):
    "constraints_items : constraints_item"
    p[0] = [p[1]]


def p_constraints_items_many(p):
    "constraints_items : constraints_items constraints_item"
    p[0] = p[1] + [p[2]]


def p_constraints_item_pre(p):
    "constraints_item : pre_block"
    p[0] = p[1]


def p_constraints_item_inv(p):
    "constraints_item : inv_block"
    p[0] = p[1]


def p_constraints_item_post(p):
    "constraints_item : post_block"
    p[0] = p[1]


def p_pre_block(p):
    "pre_block : PRE LBRACE tlcon_list RBRACE"
    p[0] = ("pre", p[3])


def p_inv_block(p):
    "inv_block : INV LBRACE tlcon_list RBRACE"
    p[0] = ("inv", p[3])


def p_post_block(p):
    "post_block : POST LBRACE tlcon_list RBRACE"
    p[0] = ("post", p[3])


def p_tlcon_list_empty(p):
    "tlcon_list : empty"
    p[0] = []


def p_tlcon_list_single(p):
    "tlcon_list : tlcon_stmt"
    p[0] = [p[1]]


def p_tlcon_list_many(p):
    "tlcon_list : tlcon_list tlcon_stmt"
    p[0] = p[1] + [p[2]]


def p_tlcon_eq(p):
    "tlcon_stmt : NAME EQ value SEMI"
    tl_name = p[1]
    v = p[3]
    p[0] = TlCon(id=tl_name, cons=[ConVal(v)])


def p_tlcon_in(p):
    "tlcon_stmt : NAME IN con_list SEMI"
    tl_name = p[1]
    cons = p[3]
    p[0] = TlCon(id=tl_name, cons=cons)


def p_con_list_single(p):
    "con_list : con_item"
    p[0] = [p[1]]


def p_con_list_many(p):
    "con_list : con_list con_item"
    p[0] = p[1] + [p[2]]


def p_con_item_val(p):
    "con_item : value"
    p[0] = ConVal(p[1])


def p_con_item_range(p):
    "con_item : range"
    lo, hi = p[1]
    p[0] = ConRealRange(RealRange(lo, hi))


# ------------ task impacts ------------

def p_task_impacts_block(p):
    "task_impacts : impacts_block"
    p[0] = p[1]


def p_task_impacts_empty(p):
    "task_impacts : empty"
    p[0] = []


def p_impacts_block(p):
    "impacts_block : IMPACTS LBRACE impact_group_list RBRACE"
    groups = p[3]
    impacts: List[Impact] = []
    for g in groups:
        impacts.extend(g)
    p[0] = impacts


def p_impact_group_list_empty(p):
    "impact_group_list : empty"
    p[0] = []


def p_impact_group_list_single(p):
    "impact_group_list : impact_group"
    p[0] = [p[1]]


def p_impact_group_list_many(p):
    "impact_group_list : impact_group_list impact_group"
    p[0] = p[1] + [p[2]]


def p_impact_group(p):
    "impact_group : impact_when LBRACE impact_group_entries RBRACE"
    when = p[1]
    entries = p[3]
    impacts: List[Impact] = []
    for tl_name, kind, payload in entries:
        if kind == "assign":
            how = ImpactAssign(payload)
        elif kind == "cumul":
            how = ImpactCumulative(payload)
        elif kind == "rate_cumul":
            how = ImpactRateCumulative(payload)
        elif kind == "rate_assign":
            how = ImpactRateAssignment(payload)
        else:
            raise ValueError(f"Unknown impact kind: {kind}")
        impacts.append(Impact(id=tl_name, when=when, how=how))
    p[0] = impacts


def p_impact_when_pre(p):
    "impact_when : PRE"
    p[0] = "pre"


def p_impact_when_maint(p):
    "impact_when : MAINT"
    p[0] = "maint"


def p_impact_when_post(p):
    "impact_when : POST"
    p[0] = "post"


def p_impact_group_entries_empty(p):
    "impact_group_entries : empty"
    p[0] = []


def p_impact_group_entries_single(p):
    "impact_group_entries : impact_group_entry"
    p[0] = [p[1]]


def p_impact_group_entries_many(p):
    "impact_group_entries : impact_group_entries impact_group_entry"
    p[0] = p[1] + [p[2]]


def p_impact_group_entry(p):
    "impact_group_entry : NAME impact_rhs SEMI"
    tl_name = p[1]
    kind, payload = p[2]
    p[0] = (tl_name, kind, payload)


def p_impact_rhs_assign(p):
    "impact_rhs : EQ value"
    p[0] = ("assign", p[2])


def p_impact_rhs_cumul_plus(p):
    "impact_rhs : PLUS_EQ NUMBER"
    p[0] = ("cumul", float(p[2]))


def p_impact_rhs_cumul_minus(p):
    "impact_rhs : MINUS_EQ NUMBER"
    p[0] = ("cumul", -float(p[2]))


def p_impact_rhs_rate_plus(p):
    "impact_rhs : PLUS_RATE NUMBER"
    p[0] = ("rate_cumul", float(p[2]))


def p_impact_rhs_rate_minus(p):
    "impact_rhs : MINUS_RATE NUMBER"
    p[0] = ("rate_cumul", -float(p[2]))


def p_impact_rhs_rate_assign(p):
    "impact_rhs : ASSIGN_RATE NUMBER"
    p[0] = ("rate_assign", float(p[2]))


# ------------ top-level temporal constraints & properties ------------

def p_constraints_tl_block(p):
    "constraints_tl_block : CONSTRAINTS LBRACE temporal_prop_list RBRACE"
    p[0] = p[3]


def p_properties_block(p):
    "properties_block : PROPERTIES LBRACE temporal_prop_list RBRACE"
    p[0] = p[3]


def p_temporal_prop_list_empty(p):
    "temporal_prop_list : empty"
    p[0] = []


def p_temporal_prop_list_single(p):
    "temporal_prop_list : temporal_prop"
    p[0] = [p[1]]


def p_temporal_prop_list_many(p):
    "temporal_prop_list : temporal_prop_list temporal_prop"
    p[0] = p[1] + [p[2]]


def p_temporal_prop(p):
    "temporal_prop : PROP NAME COLON tl_formula SEMI"
    name = p[2]
    formula = p[4]
    p[0] = TemporalProperty(name=name, formula=formula)


# ------------ temporal logic formulas ------------

def p_tl_formula(p):
    "tl_formula : tl_imp"
    p[0] = p[1]


def p_tl_imp_single(p):
    "tl_imp : tl_or"
    p[0] = p[1]


def p_tl_imp_chain_arrow(p):
    "tl_imp : tl_or IMPLIES tl_imp"
    p[0] = TLImplies(left=p[1], right=p[3])


def p_tl_imp_chain_keyword(p):
    "tl_imp : tl_or IMPLIES_KW tl_imp"
    p[0] = TLImplies(left=p[1], right=p[3])


def p_tl_or_single(p):
    "tl_or : tl_and"
    p[0] = p[1]


def p_tl_or_chain(p):
    "tl_or : tl_or OR tl_and"
    p[0] = TLOr(left=p[1], right=p[3])


def p_tl_and_single(p):
    "tl_and : tl_u"
    p[0] = p[1]


def p_tl_and_chain(p):
    "tl_and : tl_and AND tl_u"
    p[0] = TLAnd(left=p[1], right=p[3])


def p_tl_u_single(p):
    "tl_u : tl_unary"
    p[0] = p[1]


def p_tl_u_until(p):
    "tl_u : tl_unary UNTIL tl_unary"
    p[0] = TLUntil(left=p[1], right=p[3])


def p_tl_u_since(p):
    "tl_u : tl_unary SINCE tl_unary"
    p[0] = TLSince(left=p[1], right=p[3])


def p_tl_unary_not(p):
    "tl_unary : NOT tl_unary"
    p[0] = TLNot(sub=p[2])


def p_tl_unary_always(p):
    "tl_unary : ALWAYS tl_unary"
    p[0] = TLAlways(sub=p[2])


def p_tl_unary_eventually(p):
    "tl_unary : EVENTUALLY tl_unary"
    p[0] = TLEventually(sub=p[2])


def p_tl_unary_sofar(p):
    "tl_unary : SOFAR tl_unary"
    p[0] = TLSoFar(sub=p[2])


def p_tl_unary_once(p):
    "tl_unary : ONCE tl_unary"
    p[0] = TLOnce(sub=p[2])


def p_tl_unary_parens(p):
    "tl_unary : LPAREN tl_formula RPAREN"
    p[0] = p[2]


def p_tl_unary_atom(p):
    "tl_unary : tl_atom"
    p[0] = p[1]


def p_tl_atom_num_cmp(p):
    "tl_atom : NAME cmp_op NUMBER"
    tl_name = p[1]
    op = p[2]
    bound = float(p[3])
    p[0] = TLNumCmp(tl=tl_name, op=op, bound=bound)


def p_tl_atom_state_eq_name(p):
    "tl_atom : NAME EQ NAME"
    tl_name = p[1]
    value_name = p[3]
    p[0] = TLStateIs(tl=tl_name, value=value_name)


# Removed: NAME EQ NUMBER now goes through NAME cmp_op NUMBER -> TLNumCmp
# This makes atomic timelines (A = 0, A = 1) use numeric syntax consistently
# State timelines with numeric state names still work via NAME EQ NAME -> TLStateIs


# Parser rules for state timelines with "true"/"false" state names
# (e.g., bool timelines which desugar to state(true, false))
def p_tl_atom_state_eq_true(p):
    "tl_atom : NAME EQ TRUE"
    tl_name = p[1]
    p[0] = TLStateIs(tl=tl_name, value="true")


def p_tl_atom_state_eq_false(p):
    "tl_atom : NAME EQ FALSE"
    tl_name = p[1]
    p[0] = TLStateIs(tl=tl_name, value="false")


def p_tl_atom_active(p):
    "tl_atom : ACTIVE LPAREN NAME RPAREN"
    task_name = p[3]
    p[0] = TLTaskActive(task=task_name)


def p_tl_atom_true(p):
    "tl_atom : TRUE"
    p[0] = TLTrue()


def p_tl_atom_false(p):
    "tl_atom : FALSE"
    p[0] = TLFalse()


def p_tl_atom_time_cmp_num(p):
    "tl_atom : TIME cmp_op NUMBER"
    op = p[2]
    bound = float(p[3])
    left = TLTimeVar()
    p[0] = TLTimeCmp(left=left, op=op, right=bound)


def p_tl_atom_time_cmp_task_start(p):
    "tl_atom : TIME cmp_op NAME DOT START_KW"
    task_name = p[3]
    op = p[2]
    left = TLTimeVar()
    right = TLTaskBoundary(task=task_name, boundary="start")
    p[0] = TLTimeCmp(left=left, op=op, right=right)


def p_tl_atom_time_cmp_task_end(p):
    "tl_atom : TIME cmp_op NAME DOT END"
    task_name = p[3]
    op = p[2]
    left = TLTimeVar()
    right = TLTaskBoundary(task=task_name, boundary="end")
    p[0] = TLTimeCmp(left=left, op=op, right=right)


def p_tl_atom_task_start_cmp_num(p):
    "tl_atom : NAME DOT START_KW cmp_op NUMBER"
    task_name = p[1]
    op = p[4]
    bound = float(p[5])
    left = TLTaskBoundary(task=task_name, boundary="start")
    p[0] = TLTimeCmp(left=left, op=op, right=bound)


def p_tl_atom_task_end_cmp_num(p):
    "tl_atom : NAME DOT END cmp_op NUMBER"
    task_name = p[1]
    op = p[4]
    bound = float(p[5])
    left = TLTaskBoundary(task=task_name, boundary="end")
    p[0] = TLTimeCmp(left=left, op=op, right=bound)


def p_tl_atom_task_start_cmp_task_start(p):
    "tl_atom : NAME DOT START_KW cmp_op NAME DOT START_KW"
    task_name1 = p[1]
    op = p[4]
    task_name2 = p[5]
    left = TLTaskBoundary(task=task_name1, boundary="start")
    right = TLTaskBoundary(task=task_name2, boundary="start")
    p[0] = TLTimeCmp(left=left, op=op, right=right)


def p_tl_atom_task_start_cmp_task_end(p):
    "tl_atom : NAME DOT START_KW cmp_op NAME DOT END"
    task_name1 = p[1]
    op = p[4]
    task_name2 = p[5]
    left = TLTaskBoundary(task=task_name1, boundary="start")
    right = TLTaskBoundary(task=task_name2, boundary="end")
    p[0] = TLTimeCmp(left=left, op=op, right=right)


def p_tl_atom_task_end_cmp_task_start(p):
    "tl_atom : NAME DOT END cmp_op NAME DOT START_KW"
    task_name1 = p[1]
    op = p[4]
    task_name2 = p[5]
    left = TLTaskBoundary(task=task_name1, boundary="end")
    right = TLTaskBoundary(task=task_name2, boundary="start")
    p[0] = TLTimeCmp(left=left, op=op, right=right)


def p_tl_atom_task_end_cmp_task_end(p):
    "tl_atom : NAME DOT END cmp_op NAME DOT END"
    task_name1 = p[1]
    op = p[4]
    task_name2 = p[5]
    left = TLTaskBoundary(task=task_name1, boundary="end")
    right = TLTaskBoundary(task=task_name2, boundary="end")
    p[0] = TLTimeCmp(left=left, op=op, right=right)


def p_tl_atom_sequence(p):
    "tl_atom : SEQUENCE LBRACKET task_name_list RBRACKET"
    tasks = p[3]
    p[0] = TLSequence(tasks=tasks)


def p_task_name_list_single(p):
    "task_name_list : NAME"
    p[0] = [p[1]]


def p_task_name_list_many(p):
    "task_name_list : task_name_list COMMA NAME"
    p[0] = p[1] + [p[3]]


def p_cmp_op_lt(p):
    "cmp_op : LT"
    p[0] = "<"


def p_cmp_op_le(p):
    "cmp_op : LE"
    p[0] = "<="


def p_cmp_op_eq(p):
    "cmp_op : EQ"
    p[0] = "="


def p_cmp_op_ge(p):
    "cmp_op : GE"
    p[0] = ">="


def p_cmp_op_gt(p):
    "cmp_op : GT"
    p[0] = ">"


# ------------ values ------------

def p_value_string(p):
    "value : STRING"
    p[0] = StrVal(p[1])


def p_value_number(p):
    "value : NUMBER"
    n = p[1]
    if float(n).is_integer():
        p[0] = IntVal(int(n))
    else:
        p[0] = RealVal(float(n))


def p_value_true(p):
    "value : TRUE"
    p[0] = BoolVal(True)


def p_value_false(p):
    "value : FALSE"
    p[0] = BoolVal(False)


def p_value_name(p):
    "value : NAME"
    p[0] = StrVal(p[1])


# ------------ error ------------

def p_error(p):
    if p is None:
        raise SyntaxError("Syntax error at EOF")
    raise SyntaxError(f"Syntax error at {p.value!r} (type {p.type}) on line {p.lineno}")


parser = yacc.yacc(start="start")


# ============================================================
# 3. Convenience functions
# ============================================================

def parse_tasknet(text: str) -> TaskNet:
    return parser.parse(text, lexer=lexer)


def parse_tasknet_file(path: str) -> TaskNet:
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    return parse_tasknet(text)


