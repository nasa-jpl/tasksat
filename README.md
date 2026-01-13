# TaskSAT 

TaskSAT is a domain-specific language and tool for modeling and verifying task scheduling problems with rich temporal and resource constraints. The system combines a declarative specification language with SMT-based automated reasoning using Z3. TaskSAT supports multiple types of state variables that model discrete states, Boolean flags, and continuous resources with complex dynamics. Tasks specify preconditions, invariants, postconditions, and resource impacts (assignments, deltas, rates) that occur at boundaries or during execution. The verifier encodes specifications into quantifier-free SMT formulas using zone-based time discretization, supporting both satisfiability checking and optimization. Users can express temporal properties using LTL-style operators (always, eventually, until, since) that are verified alongside scheduling constraints.

TaskSAT can be applied to scheduling problems in autonomous systems, such as spacecraft and rover operations, 

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

## Documentation

- **[Getting Started](doc/getting-started.md)** - Quick installation and your first TaskNet in minutes
- **[Tutorial](doc/tutorial.md)** - In-depth walkthrough of concepts, patterns, and best practices
- **[Language Reference](doc/language-reference.md)** - Complete DSL syntax reference
- **[Examples](doc/examples.md)** - Annotated examples and common patterns
- **[Performance & Scaling](doc/performance.md)** - Stress test results and complexity guidelines
- **[Architecture](doc/architecture.md)** - Implementation details and SMT encoding

