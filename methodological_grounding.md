# Methodological Grounding in Prior Research (Concise Rationale)

Our methodology is not an ad-hoc design, but a deliberate synthesis of consensus patterns repeatedly observed across three mature research threads: ensemble learning, Byzantine fault tolerance, and multi-agent deliberation with LLMs. Each selected component corresponds to a distinct coordination mechanism that prior work has shown to fail in qualitatively different ways.

## 1. Why These Consensus Families

**Vote-based aggregation** reflects the dominant paradigm in ensemble learning and self-consistency prompting, where correctness is inferred from agreement counts. Prior work shows this regime is highly effective under independence assumptions but fragile under correlation and conformity—precisely the failure mode we aim to test.

**Weighted BFT-style consensus** directly mirrors classical Byzantine fault-tolerant systems and modern validator-based blockchains, where agenda-setting (leader nomination) is separated from final authority (quorum approval). This structure is well-studied for safety and liveness guarantees and provides a principled way to study trust amplification and veto power in LLM collectives.

**Persistence-based finalization** is grounded in deliberative and self-refinement literature, where stability across iterations is treated as a proxy for correctness. Prior work repeatedly shows that transient agreement is easy to manipulate, while sustained convergence is significantly harder—making this family a natural testbed for long-horizon attacks.

Each family isolates a different axis of coordination (numerical agreement, trusted authority, temporal stability). Prior literature treats these axes separately; our contribution is evaluating them under a shared experimental substrate.

## 2. Why These Interaction Topologies

Prior multi-agent and MAS research consistently demonstrates that:

- **Centralized (hub-based) coordination** maximizes efficiency but introduces single-point-of-failure risks.
- **Fully connected interaction** maximizes information exposure and conformity pressure.
- **Intermediate topologies** (rings, lattices, expanding neighborhoods) have been shown to interpolate smoothly between these extremes without introducing fundamentally new dynamics.

Therefore, selecting only the two extremes is a standard experimental reduction technique used to capture the full behavioral envelope while avoiding parameter explosion.

## 3. Why These Design Constraints

Several choices are intentionally constrained to align with prior methodological best practices:

- **Fixed leader per task** avoids feedback loops that classical BFT work explicitly warns against (e.g., leader capture via reputation manipulation).
- **Deterministic system modules** are used wherever subjective judgment is unnecessary (e.g., vote counting), reflecting standard separation-of-concerns in distributed systems.
- **Single equivalence mechanism** in persistence-based consensus avoids confounds that prior work identifies when multiple semantic judges are mixed.

These constraints follow a common pattern in consensus research: hold mechanics fixed, vary attack surface.

## 4. Overall Positioning

In short, the methodology:

- adopts well-established consensus primitives rather than inventing new ones,
- selects representative extremes rather than exhaustive variants,
- and unifies them under a single experimental framework to enable controlled, interpretable comparisons.
