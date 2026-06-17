# Trust Memo — TalkToData

**To:** The CEO
**From:** Founding Engineer, TalkToData
**Re:** Can you trust the answers? (Part 5 — Deliverable 4)

---

**Would I let TalkToData answer questions fully unsupervised? No — I require
the human to see the SQL.** The system is genuinely good: it writes joins and
groupings on its own and answers in seconds. But "valid SQL" and "correct SQL"
are not the same thing. A query can run cleanly, return a tidy number, and still
answer a *different question* than the one you asked. The fix is cheap and it is
already built in: every answer ships with the SQL that produced it. A five-second
glance at that query is the difference between a decision and a guess. So:
**answers flow automatically; trust is granted by a human reading the query.**

**A concrete wrong-but-valid example from my own testing.**
I asked: *"How many orders came from Mumbai last week?"* The model returned:

```sql
SELECT COUNT(*) FROM orders
WHERE city = 'Mumbai'
  AND order_date >= date('now', '-7 days')
  AND order_date <= date('now')
```

It runs without error and returns a clean `1`. But "last week" has no fixed
meaning against our data — so the model silently anchored it to the **real
system clock** (`date('now')`). That answer is only meaningful by luck: it
happens that our seeded orders run up to mid-June 2026. Run the same question
next year and it would quietly return `0` — and no one would notice. Without the
SQL shown beneath it, the `1` looks authoritative. *With* the SQL shown, you
immediately see the hidden time assumption and can challenge it. (Worth
recording honestly: the textbook "repeat-customers" hallucination did **not**
reliably reproduce with today's coder-grade models — they consistently applied
the `is_repeat` filter. The danger has moved from obvious mistakes to subtle,
assumption-driven ones, which makes the verification view *more* important, not
less.)

**Two kinds of questions I would never let it answer without a human checking:**
1. **Anything with a relative time window** ("last week", "this quarter",
   "recently"). The model guesses an anchor date you can't see, and the number
   silently depends on that guess — exactly the failure above.
2. **Anything feeding an irreversible or high-stakes action** (restock budgets,
   refunds, payouts, board-deck revenue figures). When money or a public number
   rides on the answer, a fluent-but-wrong query is expensive, and the cost of a
   human glance is trivial by comparison.

**Did my understanding of "trust" change after building this?**
Yes. Before building, I thought "trust" meant *the answer is correct*. After
building, I understand trust means *the answer is **verifiable*** — that I can
see how it was produced and confirm it answered my real question. The guardrails
don't make the model perfect; they make its mistakes **catchable**. That is what
trust means in practice, and it is why the "show the SQL" view is the product,
not a decoration.

> *NL-to-SQL is translation you can verify. The machine writes the query;
> the human still decides whether to trust the answer.*
