# Project standard: football realism

The purpose of this game is to behave plausibly like real football, across every system: game simulation, coaching, roster construction, contracts, scouting, progression, and the interface that explains them.

For each proposed fix, ask whether it makes the affected behavior more or less realistic. Model the decision and its consequences, including what teams and players know, want, can afford, and can actually do. A team may make an imperfect choice; do not force every team toward a perfect roster or identical strategy.

Use tests and register checks to verify rules, outcomes, and regressions. Do not change football behavior merely to satisfy an assertion or aggregate target. If a metric improves while the underlying decisions become less plausible, investigate the cause instead of accepting the metric.

When reporting a change, distinguish what was observed in a saved game, what a controlled test proves, and what remains a balance question. Preserve the user's explicit game-design choices when they differ from current league practice.

## Required review for decision-making changes

Before coding, explain the football motivation, the reasons against the move, and how different GM personalities could reasonably disagree. Realism is an acceptance requirement, not an aspiration or an aggregate target.

Trace the complete decision and its alternatives: keeping the current roster, the incoming player's role, whom he displaces, established performance, age and public development information, contract control and costs, future flexibility, and value surrendered by releasing rather than retaining or trading the incumbent. A legal, affordable move or a higher immediate roster score does not alone justify a transaction. Do not invent trade offers or use hidden potential to justify it.

Test action and restraint. Include worthwhile upgrades, marginal replacements that should be declined, injury/coverage needs, contract consequences, and differing GM preferences. Review individual player-level outcomes before integration; passing tests and improved totals do not establish plausible behavior.

Keep a permanent Campbell-Darrisaw regression scenario: a productive young starting tackle considered for release for a slightly better older veteran. Assert that the complete tradeoff is evaluated, not a player-name exception or a universal ban on replacing young players. A materially better offer or different roster situation must still be able to change the decision.

Before integration, report observed outcomes, what controlled tests establish, and remaining uncertainty. Do not describe a change as fully verified if a relevant realism check is unresolved.
