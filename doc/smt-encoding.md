# SMT Encoding of TaskNet Scheduling Problems

## 1. Introduction

We describe a formal encoding of TaskNet scheduling problems into Satisfiability Modulo Theories (SMT) using the theory of linear integer and real arithmetic. The encoding transforms a TaskNet specification—consisting of tasks with temporal constraints, timelines of various types, and task impacts on those timelines—into a quantifier-free formula suitable for solving with Z3.

## 2. Zone Abstraction

### 2.1 Time Discretization

Given a TaskNet with horizon $H \in \mathbb{N}$ and tasks $\mathcal{T} = \{t_1, \ldots, t_n\}$, we partition time into **zones** defined by task boundaries.

**Definition (Zone Boundaries):** Let $Z$ be the number of zones, where $Z = 2|\mathcal{T}| + 2$. We introduce zone boundary variables $z_0, z_1, \ldots, z_{Z-1}$ where:

$$z_0 = 0$$
$$z_{Z-1} = H$$
$$z_i < z_{i+1} \quad \text{for all } i \in \{0, \ldots, Z-2\}$$

**Definition (Zone):** Zone $i$ corresponds to the time interval $(z_i, z_{i+1}]$ for $i \in \{0, \ldots, Z-2\}$.

### 2.2 Task-Zone Correspondence

For each task $t \in \mathcal{T}$, let $s_t$ and $e_t$ denote its start and end time variables. We enforce a bijection between internal zone boundaries $\{z_1, \ldots, z_{Z-2}\}$ and task boundaries $\{s_t, e_t \mid t \in \mathcal{T}\}$:

$$\bigwedge_{t \in \mathcal{T}} \left( \bigvee_{j=1}^{Z-2} s_t = z_j \right) \land \left( \bigvee_{j=1}^{Z-2} e_t = z_j \right)$$

$$\bigwedge_{j=1}^{Z-2} \bigvee_{t \in \mathcal{T}} (s_t = z_j \lor e_t = z_j)$$

**Distinctness:** All task boundaries are pairwise distinct:

$$\bigwedge_{t_i, t_j \in \mathcal{T}, i \neq j} (s_{t_i} \neq s_{t_j}) \land (e_{t_i} \neq e_{t_j}) \land (s_{t_i} \neq e_{t_j}) \land (e_{t_i} \neq s_{t_j})$$

## 3. Timeline Encoding

### 3.1 Timeline Types

We consider five timeline types, each with distinct semantics:

**State Timelines:** Discrete enumerated values from a finite set $\Sigma$.
- Variables: $\sigma^{\ell}[j] \in \{0, \ldots, |\Sigma|-1\}$ for timeline $\ell$ at zone $j$

**Atomic Timelines:** Boolean values.
- Variables: $\alpha^{\ell}[j] \in \{\mathtt{true}, \mathtt{false}\}$ for timeline $\ell$ at zone $j$

**Numeric Timelines:** Real-valued timelines with range $[r_{\min}, r_{\max}]$ and bounds $[b_{\min}, b_{\max}]$.
- **Claimable:** Resources that can be claimed/released (delta impacts only during maintenance)
- **Cumulative:** Accumulators with delta impacts (no rate changes)
- **Rate:** Continuous resources with rate-of-change impacts

Variables: $\nu^{\ell}[j] \in \mathbb{R}$ for timeline $\ell$ at zone $j$

### 3.2 Initial State

For each timeline $\ell$ with initial value specification $v_0^{\ell}$:

$$\sigma^{\ell}[0] = \mathtt{encode}(v_0^{\ell}) \quad \text{(state)}$$
$$\alpha^{\ell}[0] = v_0^{\ell} \quad \text{(atomic)}$$
$$\nu^{\ell}[0] = v_0^{\ell} \quad \text{(numeric)}$$

where $\mathtt{encode}: \Sigma \to \{0, \ldots, |\Sigma|-1\}$ maps state values (strings) to integer indices for SMT encoding.

### 3.3 Range Constraints

For numeric timelines with range $[r_{\min}, r_{\max}]$:

$$\bigwedge_{j=0}^{Z-1} r_{\min} \leq \nu^{\ell}[j] \leq r_{\max}$$

For cumulative and rate timelines with bounds $[b_{\min}, b_{\max}]$:

$$b_{\min} \leq \nu^{\ell}[0] \leq b_{\max}$$

## 4. Task Encoding

### 4.1 Temporal Constraints

For each task $t \in \mathcal{T}$:

**Duration:** If task $t$ has duration range $[d_{\min}, d_{\max}]$:

$$d_{\min} \leq e_t - s_t \leq d_{\max}$$

**Start Range:** If task $t$ has start range $[s_{\min}, s_{\max}]$:

$$s_{\min} \leq s_t \leq s_{\max}$$

**End Range:** If task $t$ has end range $[e_{\min}, e_{\max}]$:

$$e_{\min} \leq e_t \leq e_{\max}$$

**Precedence:** If task $t$ must execute after task $t'$:

$$e_{t'} \leq s_t$$

**Containment:** If task $t$ must be contained in task $t'$:

$$s_{t'} \leq s_t \land e_t \leq e_{t'}$$

### 4.2 Task Conditions

**Preconditions:** For each zone $j$, if $z_j = s_t$ then preconditions $\mathtt{pre}_t$ hold at zone $j$:

$$\bigwedge_{j=0}^{Z-1} (z_j = s_t) \rightarrow \mathtt{eval}(\mathtt{pre}_t, j)$$

**Invariants:** For each zone $j$, if $s_t \leq z_j \leq e_t$ then invariants $\mathtt{inv}_t$ hold at zone $j$:

$$\bigwedge_{j=0}^{Z-1} (s_t \leq z_j \leq e_t) \rightarrow \mathtt{eval}(\mathtt{inv}_t, j)$$

**Postconditions:** For each zone $j$, if $z_j = e_t$ then postconditions $\mathtt{post}_t$ hold at zone $j$:

$$\bigwedge_{j=0}^{Z-1} (z_j = e_t) \rightarrow \mathtt{eval}(\mathtt{post}_t, j)$$

where $\mathtt{eval}(\mathcal{C}, j)$ evaluates condition set $\mathcal{C}$ at zone $j$ as:

$$\mathtt{eval}(\mathcal{C}, j) = \bigwedge_{\ell \in \mathcal{C}} \left( \bigvee_{c \in \mathcal{C}[\ell]} \mathtt{test}(\ell, c, j) \right)$$

Here, $\mathcal{C}$ is a set of **timeline conditions** (TlCon), where each condition specifies requirements for a timeline $\ell$. For each timeline $\ell$, we have a list of alternatives $\mathcal{C}[\ell]$ (a disjunction), and $\mathtt{test}(\ell, c, j)$ checks if timeline $\ell$ satisfies constraint $c$ at zone $j$ (e.g., $\nu^{\ell}[j] \in [a, b]$ or $\sigma^{\ell}[j] = v$). All timelines must satisfy their respective conditions (conjunction over timelines).

## 5. Impact Semantics

### 5.1 Impact Types

Tasks modify timelines through three impact mechanisms:

**Assignment ($=$):** Set timeline to a specific value
**Delta ($\pm$):** Instantaneous change by a fixed amount
**Rate ($\pm\!\!\sim$):** Continuous change at a fixed rate

### 5.2 State and Atomic Timelines

For state timeline $\ell$ and atomic timeline $\alpha$, only assignments are permitted at boundaries (no maint assignments).

**Important:** Timeline values are updated at zone boundaries, meaning that changes take effect at the **end** of zone $i$ (equivalently, at the start of zone $i+1$). This may be counterintuitive: an impact occurring "at" time $z_i$ affects the value starting from zone $i+1$, not within zone $i$ itself.

The transition from zone $i$ to zone $i+1$ is:

$$\sigma^{\ell}[i+1] = \begin{cases}
v & \text{if } \exists t : z_i = s_t \land (t, \ell, \mathtt{pre}, =v) \in \mathcal{I} \\
v & \text{if } \exists t : z_i = e_t \land (t, \ell, \mathtt{post}, =v) \in \mathcal{I} \\
\sigma^{\ell}[i] & \text{otherwise}
\end{cases}$$

where $\mathcal{I}$ denotes the set of all impacts. Multiple assignments to the same timeline at the same time are disallowed.

### 5.3 Numeric Timelines: Delta Accumulation

**Impact Notation:** We represent impacts as tuples $(t, \ell, w, \textit{op}, v)$ where:
- $t$ is the task performing the impact
- $\ell$ is the timeline identifier being modified
- $w \in \{\mathtt{pre}, \mathtt{maint}, \mathtt{post}\}$ indicates when the impact occurs
- $\textit{op}$ is the operation type ($=$, $\delta$, or $\sim$ for assignment, delta, or rate respectively)
- $v$ is the value (the amount for delta/rate, or the target value for assignment)

We use $\mathcal{I}_{\Delta}$ for the set of all delta impacts and $\mathcal{I}_R$ for all rate impacts.

For numeric timeline $\nu^{\ell}$ over zone $i$ spanning interval $(z_i, z_{i+1}]$, define the accumulated delta:

$$\Delta^{\ell}[i] = \sum_{(t,\ell,w,\delta,v) \in \mathcal{I}_{\Delta}} \mathtt{active}(t, w, i) \cdot v$$

where:

$$\mathtt{active}(t, \mathtt{pre}, i) = \begin{cases} 1 & \text{if } z_i = s_t \\ 0 & \text{otherwise} \end{cases}$$

$$\mathtt{active}(t, \mathtt{maint}, i) = \begin{cases}
+1 & \text{if } z_i = s_t \\
-1 & \text{if } z_i = e_t \\
0 & \text{otherwise}
\end{cases}$$

$$\mathtt{active}(t, \mathtt{post}, i) = \begin{cases} 1 & \text{if } z_i = e_t \\ 0 & \text{otherwise} \end{cases}$$

### 5.4 Numeric Timelines: Rate Integration

For rate timeline $\nu^{\ell}$ over zone $i$ with duration $\Delta t_i = z_{i+1} - z_i$, define the rate contribution:

$$R^{\ell}[i] = \sum_{(t,\ell,w,\sim,r) \in \mathcal{I}_R} \mathtt{rate\_active}(t, w, i) \cdot r \cdot \Delta t_i$$

where:

$$\mathtt{rate\_active}(t, \mathtt{pre}, i) = \begin{cases} 1 & \text{if } z_i \geq s_t \\ 0 & \text{otherwise} \end{cases}$$

$$\mathtt{rate\_active}(t, \mathtt{maint}, i) = \begin{cases} 1 & \text{if } s_t \leq z_i < e_t \\ 0 & \text{otherwise} \end{cases}$$

$$\mathtt{rate\_active}(t, \mathtt{post}, i) = \begin{cases} 1 & \text{if } z_i \geq e_t \\ 0 & \text{otherwise} \end{cases}$$

### 5.5 Zone Transition for Numeric Timelines

The value at zone boundary $i+1$ is computed as:

$$\nu^{\ell}_{\mathtt{raw}}[i+1] = \nu^{\ell}[i] + \Delta^{\ell}[i] + R^{\ell}[i]$$

If bounds $[b_{\min}, b_{\max}]$ are specified, apply clamping (i.e., constrain the value to lie within bounds):

$$\nu^{\ell}_{\mathtt{clamped}}[i+1] = \max(b_{\min}, \min(b_{\max}, \nu^{\ell}_{\mathtt{raw}}[i+1]))$$

Equivalently:

$$\nu^{\ell}_{\mathtt{clamped}}[i+1] = \begin{cases}
b_{\min} & \text{if } \nu^{\ell}_{\mathtt{raw}}[i+1] < b_{\min} \\
b_{\max} & \text{if } \nu^{\ell}_{\mathtt{raw}}[i+1] > b_{\max} \\
\nu^{\ell}_{\mathtt{raw}}[i+1] & \text{otherwise}
\end{cases}$$

Finally, assignments override the accumulated value:

$$\nu^{\ell}[i+1] = \begin{cases}
v & \text{if } \exists t : z_i = s_t \land (t, \ell, \mathtt{pre}, =v) \in \mathcal{I} \\
v & \text{if } \exists t : z_i = e_t \land (t, \ell, \mathtt{post}, =v) \in \mathcal{I} \\
\nu^{\ell}_{\mathtt{clamped}}[i+1] & \text{otherwise}
\end{cases}$$

## 6. Temporal Logic Encoding

### 6.1 LTL Operators over Zones

Temporal formulas are evaluated at zone positions. Let $\phi[j]$ denote the encoding of formula $\phi$ at zone index $j$.

**Atomic Propositions:**

$$(\ell \diamond v)[j] \equiv (\nu^{\ell}[j] \diamond v) \quad \text{where } \diamond \in \{<, \leq, =, \geq, >\}$$

**Boolean Connectives:**

$$(\phi_1 \land \phi_2)[j] \equiv \phi_1[j] \land \phi_2[j]$$
$$(\phi_1 \lor \phi_2)[j] \equiv \phi_1[j] \lor \phi_2[j]$$
$$(\neg \phi)[j] \equiv \neg (\phi[j])$$
$$(\phi_1 \rightarrow \phi_2)[j] \equiv \phi_1[j] \rightarrow \phi_2[j]$$

**Temporal Operators (Future):**

$$\mathtt{always}(\phi)[j] \equiv \bigwedge_{k=j}^{Z-1} \phi[k]$$

$$\mathtt{eventually}(\phi)[j] \equiv \bigvee_{k=j}^{Z-1} \phi[k]$$

$$(\phi_1 \mathbin{\mathtt{until}} \phi_2)[j] \equiv \bigvee_{k=j}^{Z-1} \left( \phi_2[k] \land \bigwedge_{m=j}^{k-1} \phi_1[m] \right)$$

**Temporal Operators (Past):**

$$\mathtt{sofar}(\phi)[j] \equiv \bigwedge_{k=0}^{j} \phi[k]$$

$$\mathtt{once}(\phi)[j] \equiv \bigvee_{k=0}^{j} \phi[k]$$

$$(\phi_1 \mathbin{\mathtt{since}} \phi_2)[j] \equiv \bigvee_{k=0}^{j} \left( \phi_2[k] \land \bigwedge_{m=k+1}^{j} \phi_1[m] \right)$$

### 6.2 Constraint and Property Checking

**Constraints:** Formulas in the `constraints` block must hold at position 0:

$$\bigwedge_{\phi \in \mathtt{constraints}} \phi[0]$$

**Property Verification:** To check if property $\psi$ holds universally, we search for a counterexample by solving:

$$\mathtt{SAT}\left( \Phi_{\mathtt{sched}} \land \Phi_{\mathtt{zones}} \land \Phi_{\mathtt{init}} \land \Phi_{\mathtt{impacts}} \land \bigwedge_{\phi \in \mathtt{constraints}} \phi[0] \land \neg \psi[0] \right)$$

where:
- $\Phi_{\mathtt{sched}}$ = task scheduling constraints (duration, precedence, containment, distinctness) from Section 4.1
- $\Phi_{\mathtt{zones}}$ = zone boundary constraints and task-zone correspondence from Section 2
- $\Phi_{\mathtt{init}}$ = initial state and bounds constraints from Section 3.2-3.3
- $\Phi_{\mathtt{impacts}}$ = zone transitions with impact semantics and task conditions from Section 4.2 and 5

If unsatisfiable, the property holds for all valid schedules.

## 7. Optional Tasks and Optimization

### 7.1 Optional Task Inclusion

For each optional task $t \in \mathcal{T}_{\mathtt{opt}}$, introduce a Boolean variable $\iota_t$ indicating inclusion. All constraints for task $t$ are guarded by $\iota_t$:

$$\iota_t \rightarrow (\text{task } t \text{ constraints})$$

### 7.2 Multi-Objective Optimization

The encoding supports lexicographic optimization with the following objective hierarchy:

**Primary Objective:** Minimize the number of included optional tasks:

$$\mathtt{minimize} \sum_{t \in \mathcal{T}_{\mathtt{opt}}} [\iota_t]$$

**Secondary Objective:** Minimize priority-weighted cost:

$$\mathtt{minimize} \sum_{t \in \mathcal{T}} \mathtt{priority}(t) \cdot [\iota_t \lor t \in \mathcal{T}_{\mathtt{req}}]$$

**Tertiary Objective:** Minimize deviation from preferred start times:

$$\mathtt{minimize} \sum_{t \in \mathcal{T} : \mathtt{start}_t^{\mathtt{pref}} \text{ specified}} |s_t - \mathtt{start}_t^{\mathtt{pref}}|$$

**Quaternary Objective:** Minimize deviation from preferred durations:

$$\mathtt{minimize} \sum_{t \in \mathcal{T} : \mathtt{dur}_t^{\mathtt{pref}} \text{ specified}} |(e_t - s_t) - \mathtt{dur}_t^{\mathtt{pref}}|$$

## 8. Soundness and Completeness

**Theorem (Soundness):** If the SMT encoding produces a satisfying model $\mathcal{M}$, then the extracted schedule and timeline trace satisfy all TaskNet constraints.

**Theorem (Completeness):** If there exists a valid schedule and timeline trace for a TaskNet, then the SMT encoding is satisfiable.

**Proof Sketch:** The zone abstraction is complete because it explicitly represents all task start and end times as zone boundaries. The bijection ensures no task boundaries are lost. Timeline semantics are preserved through direct encoding of impact accumulation and clamping. Temporal logic operators are bounded by the finite zone sequence, ensuring decidability.

## 9. Complexity

**Encoding Size:** For $n$ tasks and $m$ timelines:
- Zone variables: $O(n)$
- Timeline variables: $O(nm)$
- Task constraints: $O(n^2)$ (pairwise distinctness)
- Zone transition constraints: $O(nm)$
- Temporal formula: $O(|\phi| \cdot n)$ where $|\phi|$ is formula size

**Solving Complexity:** The problem is NP-complete (scheduling) combined with linear arithmetic (SMT). Z3 uses CDCL(T) with theory solvers for linear real/integer arithmetic.

## References

- de Moura, L., & Bjørner, N. (2008). Z3: An efficient SMT solver. *TACAS 2008*.
- Laborie, P., & Rogerie, J. (2008). Reasoning with conditional time-intervals. *FLAIRS 2008*.
- Cimatti, A., et al. (2016). Timed sequence alignment with SMT. *FMCAD 2016*.
