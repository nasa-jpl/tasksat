# TaskSAT 

TaskSAT is a domain-specific language and tool for modeling and verifying task scheduling problems with rich temporal and resource constraints. The system combines a declarative specification language with SMT-based automated reasoning using Z3. TaskSAT supports multiple types of state variables that model discrete states, Boolean flags, and continuous resources with complex dynamics. Tasks specify preconditions, invariants, postconditions, and resource impacts (assignments, deltas, rates) that occur at boundaries or during execution. The verifier encodes specifications into quantifier-free SMT formulas using zone-based time discretization, supporting both satisfiability checking and optimization. Users can express temporal properties using LTL-style operators (always, eventually, until, since) that are verified alongside scheduling constraints.

TaskSAT can be applied to scheduling problems in autonomous systems, such as spacecraft and rover operations, 

### System Architecture

```
  ┌─────────────────────┐
  │   TaskNet (.tn)     │  User-written specification
  │    Specification    │
  └──────────┬──────────┘
             │
             v
  ╔═════════════════════╗
  ║   Parser (PLY)      ║  Lexer + Parser (Python Lex-Yacc)
  ╚══════════┬══════════╝
             │
             v
  ┌─────────────────────┐
  │        AST          │  Abstract Syntax Tree
  └──────────┬──────────┘
             │
             v
  ╔═════════════════════╗
  ║  Wellformedness     ║  Semantic validation
  ║     Checker         ║  (type checking, constraint validation)
  ╚══════════┬══════════╝
             │
             v
  ┌─────────────────────┐
  │   Validated AST     │  Semantically valid AST
  └──────────┬──────────┘
             │
             v
  ╔═════════════════════╗
  ║   SMT Encoder       ║  Zone-based time discretization
  ║                     ║  Converts to quantifier-free formulas
  ╚══════════┬══════════╝
             │
             v
  ┌─────────────────────┐
  │   Z3 Formula        │  SMT constraints (Real + Int + Bool)
  └──────────┬──────────┘
             │
             v
  ╔═════════════════════╗
  ║    Z3 Solver        ║  SMT solving (satisfy or optimize mode)
  ╚══════════┬══════════╝
             │
             v
  ┌─────────────────────┐
  │  Schedule / UNSAT   │  Valid schedule or proof of infeasibility
  └─────────────────────┘
```

## Documentation

- **[Getting Started](doc/getting-started.md)** - Quick installation and your first TaskNet in minutes
- **[Tutorial](doc/tutorial.md)** - In-depth walkthrough of concepts, patterns, and best practices
- **[Manual](doc/manual.md)** - Complete DSL syntax reference
- **[Architecture](doc/architecture.md)** - Implementation details and SMT encoding

## Running Examples in this Document

All examples in this document are organized in 

```
tests/tasknet_files/examples.
```

Users can run any example, say `my_robot.py` in this documentation as folows:

```
python src/smt/tasknet_verifier.py tests/tasknet_files/examples/my_robot.tn --mode satisfy
```

If `--mode ...` is left out it will run in the default `optimize` mode.
