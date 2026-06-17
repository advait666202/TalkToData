"""
TalkToData — Ask Your Database in Plain English
===============================================

A Gradio dashboard that wraps the NL-to-SQL engine (engine.py).

A non-technical user types a business question, picks an engine mode, and gets
back the answer PLUS the SQL that produced it — the "verification view" that
makes the tool trustworthy (Guardrail 3 from the case study, made visible).

Run locally:
    python app.py
Then open the printed URL (http://127.0.0.1:7860).

Deploy on Hugging Face Spaces:
    Create a Gradio Space, upload app.py + engine.py + requirements.txt + README.md.
    Add HF_TOKEN as a Space secret (Settings -> Variables and secrets).
"""

from __future__ import annotations

import os

import pandas as pd
import gradio as gr
from dotenv import load_dotenv

import engine as E

load_dotenv()  # pull HF_TOKEN from a local .env file if present

DEFAULT_TOKEN = os.getenv("HF_TOKEN", "")

MODE_RULE = "Phase A — Rule-based (no AI)"
MODE_LLM = "Phase B — LLM (no guardrails)"
MODE_TRUSTED = "Phase C — LLM + Guardrails (recommended)"

EXAMPLE_QUESTIONS = [
    "How many orders came from Mumbai?",
    "Which product category earns us the most revenue?",
    "What is the average order value for repeat customers?",
    "Which product gets returned most often?",
    "List the top 5 cities by number of customers.",
    "Drop the orders table",  # demonstrates Guardrail 1 blocking
]


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------
def _rows_to_df(rows, cols):
    """Turn SQLite rows + column names into a DataFrame for gr.Dataframe."""
    if not rows:
        return pd.DataFrame({"result": ["(no rows returned)"]})
    if not cols:
        cols = [f"col{i + 1}" for i in range(len(rows[0]))]
    return pd.DataFrame(rows, columns=cols)


def _empty_df():
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# Main callback
# ---------------------------------------------------------------------------
def ask(question, api_key, model, mode, temperature):
    """Route the question through the selected engine mode and format outputs.

    Returns: (status_markdown, answer_dataframe, sql_text, note_markdown)
    """
    question = (question or "").strip()
    if not question:
        return "Please type a question first.", _empty_df(), "", ""

    # ----- Phase A: rule-based -------------------------------------------
    if mode == MODE_RULE:
        sql = E.rule_based_nl2sql(question)
        if sql is None:
            return (
                "**No rule matched.** The rule-based system simply gives up "
                "(returns `None`) — this is its brittleness, by design.",
                _empty_df(),
                "-- no SQL generated (no hand-written rule matched this phrasing)",
                "Phase A only knows the patterns it was hand-coded for. "
                "Try Phase B or C for anything involving joins or grouping.",
            )
        rows, cols = E.run_sql_with_columns(sql)
        if isinstance(rows, str):  # SQL error
            return f"**SQL error.**\n\n```\n{rows}\n```", _empty_df(), sql, ""
        return (
            "**Answer (Phase A — rule-based).** ⚠️ No guardrails. The rule may "
            "silently ignore parts of your question (e.g. *“last week”*).",
            _rows_to_df(rows, cols),
            sql,
            "Verification view: always read the SQL above to confirm it answers "
            "what you actually asked.",
        )

    # ----- Phase B: LLM, no guardrails -----------------------------------
    if mode == MODE_LLM:
        try:
            sql = E.llm_nl2sql(question, token=api_key, model=model, temperature=temperature)
        except Exception as e:  # noqa: BLE001
            return f"**Engine error.**\n\n```\n{e}\n```", _empty_df(), "", ""
        rows, cols = E.run_sql_with_columns(sql)
        if isinstance(rows, str):
            return f"**SQL error.**\n\n```\n{rows}\n```", _empty_df(), sql, ""
        return (
            "**Answer (Phase B — raw LLM).** ⚠️ No guardrails: this query was run "
            "without safety checks. Valid SQL is **not** the same as correct SQL.",
            _rows_to_df(rows, cols),
            sql,
            "This mode exists to show the hidden danger: the model can return "
            "fluent, valid SQL that answers the **wrong** question. Bump the "
            "temperature and re-run to watch the SQL change.",
        )

    # ----- Phase C: LLM + guardrails (production path) -------------------
    result = E.trusted_nl2sql(question, token=api_key, model=model, temperature=temperature)
    status = result.get("status")

    if status == "ERROR":
        return f"**Engine error.**\n\n```\n{result['reason']}\n```", _empty_df(), result.get("sql", ""), ""

    if status == "BLOCKED":
        return (
            f"🛑 **BLOCKED — {result['reason']}.** The guardrails refused to run "
            "this query. Nothing touched the database.",
            _empty_df(),
            result["sql"],
            "Guardrails 1 & 2 stop dangerous or invalid SQL before it ever runs.",
        )

    rows = result["answer"]
    if isinstance(rows, str):  # SQL error slipped through
        return f"**SQL error.**\n\n```\n{rows}\n```", _empty_df(), result["sql"], ""

    # Re-run to also grab column names for a prettier table
    rows2, cols = E.run_sql_with_columns(result["sql"])
    df = _rows_to_df(rows2 if not isinstance(rows2, str) else rows, cols)
    return (
        "✅ **Answer (Phase C — trusted).** Passed both guardrails and ran read-only.",
        df,
        result["sql"],
        result["note"],
    )


# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------
SCHEMA_MD = """
### The database (5 tables)

| Table | What it holds | Key columns |
|---|---|---|
| `customers` | One row per customer | id, name, city, signup_date, is_repeat |
| `products` | One row per product | id, name, category, price |
| `orders` | One row per order | id, customer_id, order_date, total_amount, city |
| `order_items` | Line items within orders | id, order_id, product_id, quantity |
| `returns` | One row per returned order | id, order_id, reason, return_date |

**Relationships (the “grammar” the SQL must respect):**
`orders.customer_id → customers.id` · `order_items.order_id → orders.id` ·
`order_items.product_id → products.id` · `returns.order_id → orders.id`
"""


def _overview_df():
    return pd.DataFrame(E.table_overview(), columns=["table", "rows"])


with gr.Blocks(title="TalkToData — Ask Your Database") as demo:
    gr.Markdown(
        "# 🗣️ TalkToData — Ask Your Database in Plain English\n"
        "Type a business question, get a number back in seconds — with the **SQL "
        "shown underneath so you can trust it**. *NL-to-SQL is translation you can verify.*"
    )

    with gr.Tab("Ask"):
        with gr.Row():
            with gr.Column(scale=2):
                question = gr.Textbox(
                    label="Your question",
                    placeholder="e.g. Which product category earns us the most revenue?",
                    value="Which product category earns us the most revenue?",
                    lines=2,
                )
                gr.Examples(EXAMPLE_QUESTIONS, inputs=question, label="Try one of these")
                ask_btn = gr.Button("Ask", variant="primary")

            with gr.Column(scale=1):
                mode = gr.Radio(
                    [MODE_RULE, MODE_LLM, MODE_TRUSTED],
                    value=MODE_TRUSTED,
                    label="Engine mode",
                    info="Phase A=rules, B=raw LLM, C=LLM+guardrails",
                )
                api_key = gr.Textbox(
                    label="Hugging Face API key",
                    placeholder="hf_...",
                    value=DEFAULT_TOKEN,
                    type="password",
                    info="Used for Phase B & C. Get one at huggingface.co/settings/tokens",
                )
                model = gr.Dropdown(
                    E.AVAILABLE_MODELS,
                    value=E.DEFAULT_MODEL,
                    label="LLM model",
                )
                temperature = gr.Slider(
                    0.0, 1.0, value=0.0, step=0.1,
                    label="Temperature",
                    info="Raise it, re-run, and watch the SQL change (the hallucination demo).",
                )

        status = gr.Markdown()
        answer = gr.Dataframe(label="Answer", wrap=True)
        sql_view = gr.Code(label="Generated SQL (review before trusting)", language="sql")
        note = gr.Markdown()

        ask_btn.click(
            ask,
            inputs=[question, api_key, model, mode, temperature],
            outputs=[status, answer, sql_view, note],
        )

    with gr.Tab("Database"):
        gr.Markdown(SCHEMA_MD)
        gr.Markdown("### Live row counts")
        gr.Dataframe(value=_overview_df(), label="Tables", interactive=False)

    with gr.Tab("How it works"):
        gr.Markdown(
            """
### Three phases — the history of machine translation, in miniature

**Phase A · Rule-based.** Hand-written keyword rules. Predictable and
explainable, but brittle: it ignores phrasings nobody coded for (it silently
drops *“last week”*) and gives up on anything needing a join.

**Phase B · LLM.** The database schema goes into the prompt and a large
language model translates English → SQL. It handles joins and grouping you
never coded — but it can produce *fluent, valid SQL that answers the wrong
question*. Valid SQL is not correct SQL.

**Phase C · LLM + Guardrails (recommended).** The production path:
1. **Guardrail 1** — block dangerous operations (`DROP`, `DELETE`, …): read-only.
2. **Guardrail 2** — reject SQL that references tables not in the schema.
3. **Guardrail 3** — *always show the SQL* so a human can verify before acting.

> The verification view — SQL shown beneath every answer — is not decoration.
> It is Guardrail 3 made visible, and it is what makes the tool trustworthy.
"""
        )

if __name__ == "__main__":
    demo.launch(
        theme=gr.themes.Soft(),
        share=os.getenv("GRADIO_SHARE", "").lower() in ("1", "true", "yes"),
        server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
    )
