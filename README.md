---
title: TalkToData NL2SQL
emoji: 🗣️
colorFrom: indigo
colorTo: purple
sdk: gradio
sdk_version: 6.18.0
app_file: app.py
pinned: false
license: mit
---

# 🗣️ TalkToData — Ask Your Database in Plain English

**An NL-to-SQL case study (Case Study E).** Type a business question in plain
English, get the answer back in seconds — with the **generated SQL shown
underneath so you can verify it before you trust it**.

> *NL-to-SQL is translation you can verify. The machine writes the query;
> the human still decides whether to trust the answer.*

This project re-lives the history of machine translation in three phases and
ships it as a Gradio dashboard, deployable on Hugging Face Spaces.

---

## The problem (Part 1 — Understand)

A fast-growing direct-to-consumer Indian brand makes dozens of decisions a day,
and every one needs a number. The marketing head wants the top city; the CEO
wants yesterday's revenue before her 9 AM call. **None of them write SQL**, so
every question becomes a ticket in a two-person data team's 40-deep queue.
Decisions that should take minutes take days.

The bottleneck isn't software — it's the **human gap** between the people who
have the questions and the people who can query the database. NL-to-SQL closes
that gap: anyone who can type a question gets an answer. And because a wrong SQL
query either errors out or returns visibly wrong numbers, the translation is
**verifiable** — which is exactly why the CEO can be taught to *trust* it.

## The three phases (Part 3 — Build)

| Phase | Approach | Strength | Failure mode |
|---|---|---|---|
| **A** | Rule-based keyword rules | Predictable, explainable | Brittle — ignores unforeseen phrasings (drops *"last week"*), gives up (`None`) on joins |
| **B** | LLM with schema in the prompt | Handles joins/grouping you never coded | **Hallucination** — fluent, valid SQL that answers the *wrong* question |
| **C** | LLM + Guardrails *(production)* | Catchable mistakes; trust by design | Still not perfect — but every mistake is reviewable |

**Phase C guardrails:**
1. **Block dangerous operations** — read-only; `DROP`/`DELETE`/`UPDATE`/… are refused.
2. **Validate tables** — reject SQL that references tables not in the schema.
3. **Always show the SQL** — the verification view; a human can catch the
   *"repeat customers"* kind of error before acting.

## The dashboard (Part 4 — Ship)

A Gradio app where a non-technical user can:

- Type a question and click **Ask**.
- Choose the **engine mode** (Phase A / B / C) to *feel* the difference.
- Paste their **Hugging Face API key** (used for the LLM phases).
- See the **answer as a table** and the **generated SQL beneath it** — always.
- Raise the **temperature** and re-run to watch the SQL change (the
  hallucination / non-determinism demo).

---

## Run it locally

```bash
# 1. install dependencies
pip install -r requirements.txt

# 2. provide your Hugging Face token (read access is enough)
cp .env.example .env        # then edit .env and paste your hf_... token
#   ...or just paste the token into the dashboard's "API key" box at runtime.

# 3. launch
python app.py
```

Open the printed URL (default `http://127.0.0.1:7860`).
For a temporary public link, set `GRADIO_SHARE=true` in `.env`.

### Get a Hugging Face token
Create a **read** token at <https://huggingface.co/settings/tokens> and either
put it in `.env` as `HF_TOKEN=...` or paste it into the dashboard's API-key box.

## Deploy on Hugging Face Spaces

1. Create a new **Gradio** Space.
2. Upload `app.py`, `engine.py`, `requirements.txt`, and this `README.md`
   (its YAML header configures the Space).
3. In **Settings → Variables and secrets**, add a secret `HF_TOKEN` with your
   token — or let each user paste their own key into the dashboard.
4. The Space builds and serves the app automatically.

---

## Project structure

```
TalkToData/
├── app.py            # Gradio dashboard (UI + the API-key input)
├── engine.py         # NL-to-SQL engine: DB seed + Phase A/B/C + guardrails
├── requirements.txt  # dependencies
├── README.md         # this file (+ HF Spaces config header)
├── PLAN.md           # Part 2 deliverable: 5-question mapping + predictions
├── TRUST_MEMO.md     # Part 5 deliverable: the half-page memo to the CEO
├── .env.example      # template for your HF token
└── .gitignore
```

## How the database works

The engine builds an **in-memory SQLite** database on startup and seeds it with
realistic sample data (60 customers, 25 products, 200 orders, 400 order items,
40 returns). The RNG is seeded (`random.seed(42)`) so answers are reproducible.
Nothing to install or download — SQLite ships with Python.

| Table | Rows | Key columns |
|---|---|---|
| `customers` | 60 | id, name, city, signup_date, is_repeat |
| `products` | 25 | id, name, category, price |
| `orders` | 200 | id, customer_id, order_date, total_amount, city |
| `order_items` | 400 | id, order_id, product_id, quantity |
| `returns` | 40 | id, order_id, reason, return_date |

## Security note

Your Hugging Face token is a secret. The dashboard's API-key box is a password
field, and `.env` is git-ignored. **Never commit a real token** to a public
repo or Space — use Space secrets instead.

---

*Built for Case Study E — MAIB · Natural Language Processing · Machine
Translation & NL-to-SQL.*
