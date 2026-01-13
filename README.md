# TaskSAT 

TaskSAT is a domain-specific language and tool for modeling and verifying task scheduling problems with rich temporal and resource constraints. The system combines a declarative specification language with SMT-based automated reasoning using Z3. TaskSAT supports multiple types of state variables that model discrete states, Boolean flags, and continuous resources with complex dynamics. Tasks specify preconditions, invariants, postconditions, and resource impacts (assignments, deltas, rates) that occur at boundaries or during execution. The verifier encodes specifications into quantifier-free SMT formulas using zone-based time discretization, supporting both satisfiability checking and optimization. Users can express temporal properties using LTL-style operators (always, eventually, until, since) that are verified alongside scheduling constraints.

TaskSAT can be applied to scheduling problems in autonomous systems, such as spacecraft and rover operations, 

TaskSAT allows you to:

- **Model** complex scheduling problems using an expressive DSL
- **Specify** temporal constraints, resource requirements, and task dependencies
- **Verify** that schedules satisfy all constraints using formal methods
- **Optimize** schedules to minimize optional tasks or other objectives
- **Analyze** scheduling problems for feasibility and performance

### Key Features

- **Multiple Timeline Types**: Model discrete states, boolean flags, and continuous resources
- **Rich Constraint Language**: Express preconditions, invariants, postconditions, and impacts
- **Temporal Logic**: Verify properties using LTL-style operators (always, eventually, until, since)
- **Automated Reasoning**: Leverage Z3's SMT solver for constraint satisfaction
- **Two Solver Modes**: Satisfy mode for quick feasibility checks, optimize mode for finding best schedules
- **Performance Insights**: Understand scaling characteristics through comprehensive stress testing

### System Architecture

```
┌─────────────────┐
│  TaskNet (.tn)  │  User writes specification in DSL
│   Specification │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Parser (PLY)   │  Lexer + Parser using Python Lex-Yacc
└────────┬────────┘
         │
         v
┌─────────────────┐
│   AST + Type    │  Abstract syntax tree with wellformedness checking
│     Checking    │
└────────┬────────┘
         │
         v
┌─────────────────┐
│  SMT Encoding   │  Zone-based time discretization + quantifier-free formulas
└────────┬────────┘
         │
         v
┌─────────────────┐
│  Z3 Solver      │  SMT solving (satisfy or optimize mode)
└────────┬────────┘
         │
         v
┌─────────────────┐
│ Schedule/UNSAT  │  Valid schedule or proof of infeasibility
└─────────────────┘
```

## Documentation Structure

This documentation is organized into the following sections:

### [Getting Started](doc/getting-started.md)
Quick installation and your first TaskNet in minutes.

### [Tutorial](doc/tutorial.md)
In-depth walkthrough of concepts, patterns, and best practices.

### [Language Reference](doc/language-reference.md)
Complete DSL syntax including timeline types, task definitions, constraints, and temporal operators.

### [Examples](doc/examples.md)
Annotated examples demonstrating common patterns and real-world applications.

### [Performance & Scaling](doc/performance.md)
Stress test results, scaling characteristics, and guidelines for problem complexity.

### [Architecture](doc/architecture.md)
Implementation details: SMT encoding, zone-based discretization, and extending the system.

## Getting Help

- Start with [doc/getting-started.md](doc/getting-started.md) for quick setup
- Read [doc/tutorial.md](doc/tutorial.md) for detailed concept explanations
- Reference [doc/language-reference.md](doc/language-reference.md) for complete syntax
- Browse [doc/examples.md](doc/examples.md) for pattern examples
- Report issues at: https://github.com/[your-repo]/taskvet/issues
