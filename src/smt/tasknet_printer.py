"""
TaskNet AST → .tn syntax pretty-printer.

Converts the internal AST representation back to .tn syntax,
including auto-instantiated tasks.
"""

from tasknet_ast import *
from typing import TextIO
import sys


class TaskNetPrinter:
    """Pretty-print TaskNet AST to .tn syntax."""

    def __init__(self, indent_size: int = 2):
        self.indent_size = indent_size
        self.indent_level = 0

    def _indent(self) -> str:
        return " " * (self.indent_level * self.indent_size)

    def _write(self, out: TextIO, text: str):
        out.write(text)

    def _writeln(self, out: TextIO, text: str = ""):
        out.write(text + "\n")

    # ===== Values =====

    def print_value(self, v: Value) -> str:
        if isinstance(v, IntVal):
            return str(v.v)
        elif isinstance(v, RealVal):
            return str(v.v)
        elif isinstance(v, StrVal):
            return v.v
        elif isinstance(v, BoolVal):
            return "true" if v.v else "false"
        elif isinstance(v, ParamRef):
            return v.name
        else:
            return str(v)

    def print_param_value(self, v) -> str:
        """Print parameter value (can be Value or Range)"""
        if isinstance(v, IntRange):
            return self.print_int_range(v)
        elif isinstance(v, RealRange):
            return self.print_real_range(v)
        else:
            return self.print_value(v)

    def print_int_range(self, r: IntRange) -> str:
        return f"[{r.low}, {r.high}]"

    def print_real_range(self, r: RealRange) -> str:
        return f"[{r.low}, {r.high}]"

    # ===== Dependencies =====

    def _format_after_deps(self, deps) -> str:
        """Format list of AfterDependency objects as string."""
        items = []
        for dep in deps:
            if dep.gap is None:
                items.append(dep.task_id)
            else:
                # Print shorthand if gap.low == 0
                if dep.gap.low == 0:
                    items.append(f"{dep.task_id} {dep.gap.high}")
                else:
                    items.append(f"{dep.task_id} [{dep.gap.low}, {dep.gap.high}]")
        return ", ".join(items)

    def _format_containedin_deps(self, deps) -> str:
        """Format list of ContainedinDependency objects as string."""
        items = []
        for dep in deps:
            if dep.start_offset is None and dep.end_offset is None:
                items.append(dep.task_id)
            else:
                # Determine best format (single num, two nums, or full ranges/mixed)
                parts = [dep.task_id]

                # Check for shorthand formats
                start_is_zero = dep.start_offset and dep.start_offset.low == 0
                end_is_zero = dep.end_offset and dep.end_offset.low == 0
                same_range = (dep.start_offset and dep.end_offset and
                            dep.start_offset.high == dep.end_offset.high)

                if start_is_zero and end_is_zero and same_range:
                    # Single number shorthand: containedin A 10
                    parts.append(str(dep.start_offset.high))
                elif start_is_zero and end_is_zero:
                    # Two numbers shorthand: containedin A 10 20
                    parts.append(f"{dep.start_offset.high} {dep.end_offset.high}")
                else:
                    # Mixed or full ranges: containedin A [10,20] 30 or containedin A 10 [20,30]
                    if dep.start_offset:
                        if dep.start_offset.low == 0:
                            parts.append(str(dep.start_offset.high))
                        else:
                            parts.append(f"[{dep.start_offset.low}, {dep.start_offset.high}]")
                    if dep.end_offset:
                        if dep.end_offset.low == 0:
                            parts.append(str(dep.end_offset.high))
                        else:
                            parts.append(f"[{dep.end_offset.low}, {dep.end_offset.high}]")

                items.append(' '.join(parts))
        return ", ".join(items)

    # ===== Timelines =====

    def print_timeline(self, out: TextIO, tl: Timeline):
        ind = self._indent()

        if isinstance(tl, StateTimeline):
            states = ", ".join(tl.states)
            init = f" = {tl.initial}" if tl.initial else ""
            self._writeln(out, f"{ind}{tl.id} : state({states}){init};")

        elif isinstance(tl, AtomicTimeline):
            init = f" = {str(tl.initial).lower()}" if tl.initial is not None else ""
            self._writeln(out, f"{ind}{tl.id} : atomic{init};")

        elif isinstance(tl, ClaimableTimeline):
            rng = self.print_real_range(tl.range)
            init = f" = {tl.initial}" if tl.initial is not None else ""
            self._writeln(out, f"{ind}{tl.id} : claim {rng}{init};")

        elif isinstance(tl, CumulativeTimeline):
            rng = self.print_real_range(tl.range)
            bounds = f" bounds {self.print_real_range(tl.bounds)}" if tl.bounds else ""
            init = f" = {tl.initial}" if tl.initial is not None else ""
            self._writeln(out, f"{ind}{tl.id} : cumulative {rng}{bounds}{init};")

        elif isinstance(tl, RateTimeline):
            rng = self.print_real_range(tl.range)
            bounds = f" bounds {self.print_real_range(tl.bounds)}" if tl.bounds else ""
            init = f" = {tl.initial}" if tl.initial is not None else ""
            init_rate = f" initial_rate = {tl.initial_rate}" if tl.initial_rate is not None else ""
            self._writeln(out, f"{ind}{tl.id} : rate {rng}{bounds}{init}{init_rate};")

    # ===== Constraints =====

    def print_tlcon(self, out: TextIO, con: TlCon):
        ind = self._indent()
        tl_name = con.id

        # Check if it's a simple assignment (single value)
        if len(con.cons) == 1 and isinstance(con.cons[0], ConVal):
            val = self.print_value(con.cons[0].v)
            self._writeln(out, f"{ind}{tl_name} = {val};")
        else:
            # It's an "in" constraint with ranges/values
            items = []
            for c in con.cons:
                if isinstance(c, ConVal):
                    items.append(self.print_value(c.v))
                elif isinstance(c, ConIntRange):
                    items.append(self.print_int_range(c.r))
                elif isinstance(c, ConRealRange):
                    items.append(self.print_real_range(c.r))
            self._writeln(out, f"{ind}{tl_name} in {', '.join(items)};")

    # ===== Impacts =====

    def print_impact(self, out: TextIO, imp: Impact):
        ind = self._indent()
        tl = imp.id

        if isinstance(imp.how, ImpactAssign):
            val = self.print_value(imp.how.v)
            self._writeln(out, f"{ind}{tl} = {val};")

        elif isinstance(imp.how, ImpactCumulative):
            v = imp.how.v
            op = "+=" if v >= 0 else "-="
            self._writeln(out, f"{ind}{tl} {op} {abs(v)};")

        elif isinstance(imp.how, ImpactRateCumulative):
            v = imp.how.delta
            op = "+~" if v >= 0 else "-~"
            self._writeln(out, f"{ind}{tl} {op} {abs(v)};")

        elif isinstance(imp.how, ImpactRateAssignment):
            self._writeln(out, f"{ind}{tl} =~ {imp.how.rate};")

    def print_impacts_block(self, out: TextIO, impacts: List[Impact]):
        if not impacts:
            return

        ind = self._indent()
        self._writeln(out, f"{ind}impacts {{")
        self.indent_level += 1

        # Group by when
        pre = [i for i in impacts if i.when == "pre"]
        maint = [i for i in impacts if i.when == "maint"]
        post = [i for i in impacts if i.when == "post"]

        for when, group in [("pre", pre), ("maint", maint), ("post", post)]:
            if group:
                self._writeln(out, f"{self._indent()}{when} {{")
                self.indent_level += 1
                for imp in group:
                    self.print_impact(out, imp)
                self.indent_level -= 1
                self._writeln(out, f"{self._indent()}}}")

        self.indent_level -= 1
        self._writeln(out, f"{ind}}}")

    # ===== Tasks =====

    def print_task_range(self, out: TextIO, task_range: TaskRange):
        """Print unexpanded TaskRange syntax"""
        ind = self._indent()

        # Task range header
        kind_prefix = "request " if task_range.is_request else ""
        range_str = f"[{task_range.min_instances}..{task_range.max_instances}]"
        extends = f" : {task_range.definition}" if task_range.definition else ""
        self._writeln(out, f"{ind}{kind_prefix}task {task_range.id}{range_str}{extends} {{")

        self.indent_level += 1
        ind = self._indent()

        # Print all fields same as regular task
        if task_range.ident is not None and task_range.ident != 0:
            self._writeln(out, f"{ind}id {task_range.ident};")
        if task_range.priority is not None:
            self._writeln(out, f"{ind}priority {task_range.priority};")
        if task_range.start is not None:
            self._writeln(out, f"{ind}start {task_range.start};")
        if task_range.dur is not None:
            self._writeln(out, f"{ind}duration {task_range.dur};")
        if task_range.startrng:
            self._writeln(out, f"{ind}start_range {self.print_int_range(task_range.startrng)};")
        if task_range.endrng:
            self._writeln(out, f"{ind}end_range {self.print_int_range(task_range.endrng)};")
        if task_range.durrng:
            self._writeln(out, f"{ind}duration_range {self.print_int_range(task_range.durrng)};")

        # Dependencies
        if task_range.after_instances:
            items = self._format_after_deps(task_range.after_instances)
            self._writeln(out, f"{ind}after {items};")
        if task_range.after_definitions:
            items = self._format_after_deps(task_range.after_definitions)
            self._writeln(out, f"{ind}after {items};")
        if task_range.containedin_instances:
            items = self._format_containedin_deps(task_range.containedin_instances)
            self._writeln(out, f"{ind}containedin {items};")
        if task_range.containedin_definitions:
            items = self._format_containedin_deps(task_range.containedin_definitions)
            self._writeln(out, f"{ind}containedin {items};")

        # Constraints and impacts (same as regular task)
        if task_range.pre or task_range.inv or task_range.post:
            self._writeln(out, f"{ind}constraints {{")
            self.indent_level += 1
            if task_range.pre:
                self.print_con_block(out, "pre", task_range.pre)
            if task_range.inv:
                self.print_con_block(out, "inv", task_range.inv)
            if task_range.post:
                self.print_con_block(out, "post", task_range.post)
            self.indent_level -= 1
            ind = self._indent()
            self._writeln(out, f"{ind}}}")

        if task_range.impacts:
            self.print_impacts_block(out, task_range.impacts)

        self.indent_level -= 1
        ind = self._indent()
        self._writeln(out, f"{ind}}}")

    def print_task(self, out: TextIO, task: Task):
        ind = self._indent()

        # Task header
        kind_prefix = ""
        if task.kind == TaskKind.OPTIONAL:
            kind_prefix = "optional "
        elif task.kind == TaskKind.REQUEST:
            kind_prefix = "request "

        if task.kind == TaskKind.DEFINITION:
            self._writeln(out, f"{ind}taskdef {task.id} {{")
        else:
            extends = f" : {task.definition}" if task.definition else ""
            self._writeln(out, f"{ind}{kind_prefix}task {task.id}{extends} {{")

        self.indent_level += 1
        ind = self._indent()

        # Priority
        if task.priority is not None:
            self._writeln(out, f"{ind}priority {task.priority};")

        # Parameters
        if task.params:
            self._writeln(out, f"{ind}param {{")
            self.indent_level += 1
            ind2 = self._indent()
            for param in task.params:
                self._writeln(out, f"{ind2}{param.name} = {self.print_param_value(param.value)};")
            self.indent_level -= 1
            self._writeln(out, f"{ind}}}")

        # Timing
        if task.start is not None:
            self._writeln(out, f"{ind}start {task.start};")
        if task.dur is not None:
            self._writeln(out, f"{ind}duration {task.dur};")
        if task.startrng:
            self._writeln(out, f"{ind}start_range {self.print_int_range(task.startrng)};")
        if task.endrng:
            self._writeln(out, f"{ind}end_range {self.print_int_range(task.endrng)};")
        if task.durrng:
            self._writeln(out, f"{ind}duration_range {self.print_int_range(task.durrng)};")

        # Dependencies
        if task.after_instances:
            items = self._format_after_deps(task.after_instances)
            self._writeln(out, f"{ind}after {items};")
        if task.after_definitions:
            items = self._format_after_deps(task.after_definitions)
            self._writeln(out, f"{ind}after {items};")
        if task.containedin_instances:
            items = self._format_containedin_deps(task.containedin_instances)
            self._writeln(out, f"{ind}containedin {items};")
        if task.containedin_definitions:
            items = self._format_containedin_deps(task.containedin_definitions)
            self._writeln(out, f"{ind}containedin {items};")

        # Constraints
        if task.pre:
            self._writeln(out, f"{ind}pre {{")
            self.indent_level += 1
            for con in task.pre:
                self.print_tlcon(out, con)
            self.indent_level -= 1
            self._writeln(out, f"{ind}}}")

        if task.inv:
            self._writeln(out, f"{ind}inv {{")
            self.indent_level += 1
            for con in task.inv:
                self.print_tlcon(out, con)
            self.indent_level -= 1
            self._writeln(out, f"{ind}}}")

        if task.post:
            self._writeln(out, f"{ind}post {{")
            self.indent_level += 1
            for con in task.post:
                self.print_tlcon(out, con)
            self.indent_level -= 1
            self._writeln(out, f"{ind}}}")

        # Impacts
        if task.impacts:
            self.print_impacts_block(out, task.impacts)

        self.indent_level -= 1
        self._writeln(out, f"{self._indent()}}}")

    # ===== Temporal Logic =====

    def print_tl_formula(self, f: Formula) -> str:
        # Atomic formulas
        if isinstance(f, TLTaskActive):
            return f"active({f.task})"
        elif isinstance(f, TLNumCmp):
            return f"{f.tl} {f.op} {f.bound}"
        elif isinstance(f, TLStateIs):
            return f"{f.tl} = {f.value}"
        elif isinstance(f, TLBoolIs):
            val_str = "true" if f.value else "false"
            return f"{f.tl} = {val_str}"
        elif isinstance(f, TLTrue):
            return "true"
        elif isinstance(f, TLFalse):
            return "false"

        # Logical operators
        elif isinstance(f, TLNot):
            return f"not {self.print_tl_formula(f.sub)}"
        elif isinstance(f, TLAnd):
            left = self.print_tl_formula(f.left)
            right = self.print_tl_formula(f.right)
            return f"({left} and {right})"
        elif isinstance(f, TLOr):
            left = self.print_tl_formula(f.left)
            right = self.print_tl_formula(f.right)
            return f"({left} or {right})"
        elif isinstance(f, TLImplies):
            left = self.print_tl_formula(f.left)
            right = self.print_tl_formula(f.right)
            return f"({left} -> {right})"

        # Temporal operators
        elif isinstance(f, TLAlways):
            return f"always {self.print_tl_formula(f.sub)}"
        elif isinstance(f, TLEventually):
            return f"eventually {self.print_tl_formula(f.sub)}"
        elif isinstance(f, TLUntil):
            left = self.print_tl_formula(f.left)
            right = self.print_tl_formula(f.right)
            return f"({left} until {right})"
        elif isinstance(f, TLSoFar):
            return f"sofar {self.print_tl_formula(f.sub)}"
        elif isinstance(f, TLOnce):
            return f"once {self.print_tl_formula(f.sub)}"
        elif isinstance(f, TLSince):
            left = self.print_tl_formula(f.left)
            right = self.print_tl_formula(f.right)
            return f"({left} since {right})"

        # Derived constructs (normally desugared before printing)
        elif isinstance(f, TLMutex):
            group_a_str = ", ".join(f.group_a)
            if f.group_b is None:
                return f"mutex [{group_a_str}]"
            else:
                group_b_str = ", ".join(f.group_b)
                return f"mutex [{group_a_str}] with [{group_b_str}]"

        return str(f)

    # ===== TaskNet =====

    def print_tasknet(self, out: TextIO, tn: TaskNet):
        self._writeln(out, f"tasknet {tn.id} {{")
        self.indent_level += 1
        ind = self._indent()

        # End time
        self._writeln(out, f"{ind}end = {tn.endTime};")
        self._writeln(out)

        # Parameters (top-level)
        for param in tn.params:
            self._writeln(out, f"{ind}param {param.name} = {self.print_param_value(param.value)};")
        if tn.params:
            self._writeln(out)

        # Timelines
        if tn.timelines:
            self._writeln(out, f"{ind}timelines {{")
            self.indent_level += 1
            for tl in tn.timelines:
                self.print_timeline(out, tl)
            self.indent_level -= 1
            self._writeln(out, f"{ind}}}")
            self._writeln(out)

        # Init block
        if tn.initial_constraints:
            self._writeln(out, f"{ind}initial {{")
            self.indent_level += 1
            for con in tn.initial_constraints:
                self.print_tlcon(out, con)
            self.indent_level -= 1
            self._writeln(out, f"{ind}}}")
            self._writeln(out)

        # Final block (checked as a property, not enforced). Preserves the
        # `within initial` sugar: only the block's own constraints are printed;
        # the blockless form is used when there are no own constraints.
        if tn.final_constraints is not None:
            if tn.final_extends_initial and not tn.final_constraints:
                self._writeln(out, f"{ind}final within initial;")
                self._writeln(out)
            else:
                header = "final within initial" if tn.final_extends_initial else "final"
                self._writeln(out, f"{ind}{header} {{")
                self.indent_level += 1
                for con in tn.final_constraints:
                    self.print_tlcon(out, con)
                self.indent_level -= 1
                self._writeln(out, f"{ind}}}")
                self._writeln(out)

        # Tasks (definitions first, then instances/ranges)
        definitions = [t for t in tn.tasks if isinstance(t, Task) and t.kind == TaskKind.DEFINITION]
        others = [t for t in tn.tasks if isinstance(t, TaskRange) or (isinstance(t, Task) and t.kind != TaskKind.DEFINITION)]

        for task in definitions:
            self.print_task(out, task)
            self._writeln(out)

        for task in others:
            if isinstance(task, TaskRange):
                self.print_task_range(out, task)
            else:
                self.print_task(out, task)
            self._writeln(out)

        # Constraints
        if tn.constraints:
            self._writeln(out, f"{ind}constraints {{")
            self.indent_level += 1
            for prop in tn.constraints:
                formula_str = self.print_tl_formula(prop.formula)
                self._writeln(out, f"{self._indent()}prop {prop.name}: {formula_str};")
            self.indent_level -= 1
            self._writeln(out, f"{ind}}}")
            self._writeln(out)

        # Properties
        if tn.properties:
            self._writeln(out, f"{ind}properties {{")
            self.indent_level += 1
            for prop in tn.properties:
                formula_str = self.print_tl_formula(prop.formula)
                self._writeln(out, f"{self._indent()}prop {prop.name}: {formula_str};")
            self.indent_level -= 1
            self._writeln(out, f"{ind}}}")

        self.indent_level -= 1
        self._writeln(out, "}")


def print_tasknet_to_file(tn: TaskNet, output_path: str):
    """Write TaskNet AST to .tn file."""
    printer = TaskNetPrinter()
    with open(output_path, 'w') as f:
        printer.print_tasknet(f, tn)


def print_tasknet_to_string(tn: TaskNet) -> str:
    """Convert TaskNet AST to .tn string."""
    from io import StringIO
    printer = TaskNetPrinter()
    buf = StringIO()
    printer.print_tasknet(buf, tn)
    return buf.getvalue()
