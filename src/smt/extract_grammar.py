#!/usr/bin/env python3
"""
Extracts PLY grammar docstrings from parse.py and writes to grammar.txt.
"""

from __future__ import annotations
import re
import textwrap
from pathlib import Path
from collections import OrderedDict

def extract_productions(src: str):
    pattern = re.compile(
        r'def\s+(p_[A-Za-z0-9_]+)\s*\([^)]*\):\s*\n'
        r'[ \t]*[rR]?(?P<q>"""|\'\'\'|"|\')'  # opening quote
        r'(?P<doc>.*?)(?P=q)',                # body + matching closing
        re.DOTALL,
    )

    prods = []
    for m in pattern.finditer(src):
        fname = m.group(1)
        doc = m.group("doc")
        start = m.start()
        lineno = src.count("\n", 0, start) + 1
        prods.append((lineno, fname, textwrap.dedent(doc).strip("\n")))
    prods.sort(key=lambda x: x[0])
    return prods

def collect_grammar_lines(prods):
    grouped = OrderedDict()
    line_re = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.+)$')

    for lineno, _fname, doc in prods:
        for raw in doc.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = line_re.match(line)
            if not m:
                continue
            nt, rhs = m.group(1), m.group(2).strip()
            if nt not in grouped:
                grouped[nt] = (lineno, [rhs])
            else:
                rhs_list = grouped[nt][1]
                if rhs not in rhs_list:
                    rhs_list.append(rhs)

    return grouped

def main():
    here = Path(__file__).resolve().parent
    parse_path = here / "tasknet_parser.py"
    out_path = here / "grammar.txt"

    src = parse_path.read_text(encoding="utf-8")

    prods = extract_productions(src)
    if not prods:
        print("No grammar productions found in parse.py.")
        return

    grouped = collect_grammar_lines(prods)

    # Sort non-terminals by first appearance in parse.py
    sorted_nts = sorted(grouped.items(), key=lambda kv: kv[1][0])

    header = (
        "# TaskNet Grammar\n"
        "# Auto-generated from tasknet_parser.py by extract_grammar.py -- do not edit by hand.\n"
        "# Note: IMPLIES is the '->' token, IMPLIES_KW is the 'implies' keyword (both are equivalent)\n"
        "\n"
    )

    with out_path.open("w", encoding="utf-8") as f:
        f.write(header)
        for nt, (_lineno, rhs_list) in sorted_nts:
            if not rhs_list:
                continue

            f.write(f"{nt} :\n")

            f.write(f"   {rhs_list[0]}\n")
            for rhs in rhs_list[1:]:
                f.write(f" | {rhs}\n")

            f.write("\n")

    print(f"Wrote grammar for {len(sorted_nts)} non-terminals to grammar.txt")


if __name__ == "__main__":
    main()
