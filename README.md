# TaskSAT 

TaskSAT is a domain-specific language and tool for modeling and verifying task scheduling problems with rich temporal and resource constraints. The system combines a declarative specification language with SMT-based automated reasoning using Z3. TaskSAT supports multiple types of state variables that model discrete states, Boolean flags, and continuous resources with complex dynamics. Tasks specify preconditions, invariants, postconditions, and resource impacts (assignments, deltas, rates) that occur at boundaries or during execution. The verifier encodes specifications into quantifier-free SMT formulas using zone-based time discretization, supporting both satisfiability checking and optimization. Users can express temporal properties using LTL-style operators (always, eventually, until, since) that are verified alongside scheduling constraints.

TaskSAT can be applied to scheduling problems in autonomous systems, such as spacecraft and rover operations, 

## System Architecture

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

## Running Examples in this Document

All examples in this document are organized in 

```
tests/tasknet_files/examples.
```

Users can run any example, say `rover1.py` in this documentation as folows:

```
python src/smt/tasknet_verifier.py tests/tasknet_files/examples/rover1.tn --mode satisfy
```

If `--mode ...` is left out it will run in the default `optimize` mode.

## The Role of MEXEC

TaskSAT was created in order to explore an alternative method for analysing and verifying tasknets, which form the inputs to JPL's  [MEXEC](https://ai.jpl.nasa.gov/public/projects/mexec/) scheduling system. The constructs of the TaskSAT language are designed as close as possible to the MEXEC tasknet "concepts", with a semantics as close as possible to the perceived semantics of MEXEC tasknets. However, it is not a precise match since (a) on occasions the exact semantics of MEXEC has not been clear to us, (b) we have added some new language features, most importantly temporal logic constraints, (c) the scheduling algorithm is different, based on constraint solving, (d) we have added a verification step, and finally (e) we defined a DSL (Domain-Specific Langauge) for defining tasknets.

## Documentation

- **[Getting Started](doc/getting-started.md)** - Quick installation and your first TaskNet in minutes
- **[Tutorial](doc/tutorial.md)** - In-depth walkthrough of concepts using an example
- **[Manual](doc/manual.md)** - A language reference 
- **[Theory](doc/smt-encoding.md)** - Theory behind SMT encoding

## License, Copyright, Permissions, Disclaimer

APACHE LICENSE, VERSION 2.0: https://www.apache.org/licenses/LICENSE-2.0.txt

Copyright 2026, by the California Institute of Technology. ALL RIGHTS RESERVED. United States Government Sponsorship acknowledged. Any commercial use must be negotiated with the Office of Technology Transfer at the California Institute of Technology.
 
This software may be subject to U.S. export control laws. By accepting this software, the user agrees to comply with all applicable U.S. export laws and regulations. User has the responsibility to obtain export licenses, or other export authority as may be required before exporting such information to foreign countries or providing access to foreign persons.

-  Redistributions of source code must retain the above copyright notice, this list of conditions and the following disclaimer. 
- Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following disclaimer in the documentation and/or other materials provided with the distribution. 
- Neither the name of Caltech nor its operating division, the Jet Propulsion Laboratory, nor the names of its contributors may be used to endorse or promote products derived from this software without specific prior written permission. 

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE. 

## Contribution

- Klaus Havelund <klaus.havelund@jpl.nasa.gov>
- Alessandro Pinto <alessandro.pinto@jpl.nasa.gov>
