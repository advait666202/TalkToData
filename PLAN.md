# TalkToData — Plan (Deliverables for Part 1 & Part 2)

*Written before any code, as the case study requires.*

---

## Part 1 — Understand the Problem (Comprehension Checkpoints)

**1. The actual bottleneck.**
It is not a lack of software — it is a *human gap*. The people with the business
questions (CEO, marketing head, category manager) are not the people who can
write SQL (the two-person data team). Every question must be relayed through
that team, who are 40 requests behind, so a 3-second answer becomes a 3-day wait.
NL-to-SQL removes the middle-man: anyone who can type a question gets an answer.

**2. Three ways to ask the same thing.**
- "How many orders came from Mumbai?"
- "What's our Mumbai order count?"
- "Number of purchases placed in Mumbai?"

A keyword-matching system is fragile because the *same meaning* arrives in
endlessly different words. The moment a user says "purchases" instead of
"orders", or "placed in" instead of "from", a hand-written rule misses it. You
would need a new rule for every phrasing — an infinite list.

**3. Source vs. target language.**
- **Source language:** English (the manager's question).
- **Target language:** SQL (SQLite dialect).
- **The "grammar" the translation must obey:** the database **schema** — the
  tables, their columns, and the foreign-key relationships between them. A query
  that ignores the schema is grammatically invalid in the target language.

**4. Why a wrong SQL query is easier to catch than a wrong French sentence.**
A wrong translation in human language just *sounds slightly off* — undetectable
automatically. A wrong SQL query reveals itself in **two** ways:
1. It **throws an error** (invalid syntax, a column that doesn't exist), or
2. It **returns visibly wrong numbers** (a count of zero where you expected
   thousands, or a total that's obviously too small).
The output is *verifiable*, so the mistake is catchable.

**5. What "trust" requires beyond a number.**
Trust requires being able to *see how the number was produced* — the SQL itself
— so a human can confirm it answered the question that was actually asked. It
also requires a guarantee that the system can only *read* data, never modify or
delete it. A bare number with no provenance and no safety rails is not
trustworthy, no matter how confident it looks.
*(This is the gate: it is exactly why Phase C guardrails and the "show the SQL"
view are the point, not extras.)*

---

## Part 2 — Plan the Solution

### Five-question mapping table

| # | Business question | Tables needed | Join? | Grouping | Date filter | Aggregate | Other |
|---|---|---|---|---|---|---|---|
| 1 | How many orders came from Mumbai **last week**? | `orders` | No | No | **Yes** (last week) | COUNT | city filter |
| 2 | Which product **category** earns the most revenue? | `products`, `order_items` | Yes | by category | No | SUM(quantity·price) | ORDER BY ↓, LIMIT 1 |
| 3 | Average order value for **repeat** customers? | `orders`, `customers` | Yes | No | No | AVG(total_amount) | WHERE is_repeat=1 |
| 4 | Which product gets **returned** most often? | `returns`, `order_items`, `products` | Yes (3 tables) | by product | No | COUNT | ORDER BY ↓, LIMIT 1 |
| 5 | Top **5 cities** by number of customers? | `customers` | No | by city | No | COUNT | ORDER BY ↓, LIMIT 5 |

**The key observation:** only **Q1** is answerable from a single table with a
simple filter. Q2–Q5 all need joins, grouping, or both. That is the whole story
— rule-based handling will collapse the moment it leaves Q1.

### Three predictions

| Phase | Prediction: which of the 5 will it handle? Where does it break? |
|---|---|
| **A — Rule-based** | Handles only **Q1's count** — and even then **silently ignores "last week"** (returns all Mumbai orders, not last week's). Returns `None` and gives up on Q2, Q3, Q4, Q5 because no rule covers joins/grouping. Brittle and unscalable. |
| **B — LLM (schema in prompt)** | Handles **all five structurally** — it writes the joins and grouping we never coded. **But** it is prone to **hallucination**: on Q3 it may average *all* orders and silently drop the `is_repeat` filter; on Q1 "last week" is ambiguous against static data. Fluent, valid, sometimes wrong — and non-deterministic. |
| **C — LLM + Guardrails** | Same translation power as B, **plus** it blocks dangerous SQL, rejects invented tables, and **always shows the SQL** for human review. It does not make the LLM perfect — it makes its mistakes *catchable*. |

### Which phase is production-trustworthy?

**Phase C.** It keeps the LLM's ability to answer real questions while making
every answer verifiable and every dangerous query impossible — which is the only
configuration a business can actually act on. *(Phase B is powerful but unsafe;
Phase A is safe but can't answer the questions that matter.)*
