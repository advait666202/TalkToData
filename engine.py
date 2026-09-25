"""
TalkToData — NL-to-SQL engine
=============================

The "brain" behind the dashboard. It re-lives the history of machine
translation in three phases, exactly as described in Case Study E:

    Phase A  -> Rule-based NL-to-SQL      (hand-written keyword rules)
    Phase B  -> LLM-based NL-to-SQL       (database schema in the prompt)
    Phase C  -> LLM + guardrails          (safety + always show the SQL)

Step 0 builds an in-memory SQLite database and seeds it with realistic
sample data for a direct-to-consumer Indian e-commerce brand.

This module is UI-agnostic: `app.py` (Gradio) imports from it, but it can
just as easily be driven from a notebook or a script.
"""

from __future__ import annotations

import os
import re
import random
import sqlite3
import threading

# ---------------------------------------------------------------------------
# Step 0 — Build the database (runs once, at import time)
# ---------------------------------------------------------------------------
# We seed the RNG so the numbers are reproducible across restarts. That makes
# the dashboard's answers stable and lets us write meaningful documentation.
random.seed(42)

# The database lives in memory. `check_same_thread=False` lets Gradio's worker
# threads reuse the one connection; every read is wrapped in `_DB_LOCK` so the
# single cursor is never touched by two threads at once.
_conn = sqlite3.connect(":memory:", check_same_thread=False)
_cur = _conn.cursor()
_DB_LOCK = threading.Lock()

CITIES = ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Kolkata", "Pune", "Hyderabad"]
CATEGORIES = ["Skincare", "Haircare", "Electronics", "Wellness", "Fragrance"]


def _build_database() -> None:
    """Create the five tables and fill them with sample data."""
    from datetime import date, timedelta

    _cur.executescript(
        """
        CREATE TABLE customers  (id INTEGER PRIMARY KEY, name TEXT, city TEXT,
                                 signup_date TEXT, is_repeat INTEGER);
        CREATE TABLE products   (id INTEGER PRIMARY KEY, name TEXT, category TEXT,
                                 price REAL);
        CREATE TABLE orders     (id INTEGER PRIMARY KEY, customer_id INTEGER,
                                 order_date TEXT, total_amount REAL, city TEXT);
        CREATE TABLE order_items(id INTEGER PRIMARY KEY, order_id INTEGER,
                                 product_id INTEGER, quantity INTEGER);
        CREATE TABLE returns    (id INTEGER PRIMARY KEY, order_id INTEGER,
                                 reason TEXT, return_date TEXT);
        """
    )

    # 60 customers
    for i in range(1, 61):
        _cur.execute(
            "INSERT INTO customers VALUES (?,?,?,?,?)",
            (
                i,
                f"Customer{i}",
                random.choice(CITIES),
                str(date(2025, 1, 1) + timedelta(days=random.randint(0, 400))),
                random.choice([0, 1]),
            ),
        )

    # 25 products
    for i in range(1, 26):
        _cur.execute(
            "INSERT INTO products VALUES (?,?,?,?)",
            (i, f"Product{i}", random.choice(CATEGORIES), round(random.uniform(199, 4999), 2)),
        )

    # 200 orders
    for i in range(1, 201):
        _cur.execute(
            "INSERT INTO orders VALUES (?,?,?,?,?)",
            (
                i,
                random.randint(1, 60),
                str(date(2026, 4, 1) + timedelta(days=random.randint(0, 70))),
                round(random.uniform(299, 9999), 2),
                random.choice(CITIES),
            ),
        )

    # 400 order items
    for i in range(1, 401):
        _cur.execute(
            "INSERT INTO order_items VALUES (?,?,?,?)",
            (i, random.randint(1, 200), random.randint(1, 25), random.randint(1, 3)),
        )

    # 40 returns
    for i in range(1, 41):
        _cur.execute(
            "INSERT INTO returns VALUES (?,?,?,?)",
            (
                i,
                random.randint(1, 200),
                random.choice(["Damaged", "Wrong item", "Late", "Quality"]),
                str(date(2026, 4, 15) + timedelta(days=random.randint(0, 55))),
            ),
        )

    _conn.commit()


_build_database()

# Lock the database once it is seeded. On a shared deployment every visitor
# queries this one connection, so a Phase B "DROP TABLE" must not be able to
# break the app for everyone else. SQLite refuses the write and the UI shows
# the error — the dangerous SQL is still visible, it just can't run.
_cur.execute("PRAGMA query_only = ON")


# ---------------------------------------------------------------------------
# Schema — the "grammar" of the target language (handed to the LLM)
# ---------------------------------------------------------------------------
SCHEMA = """Tables:
customers(id, name, city, signup_date, is_repeat)
products(id, name, category, price)
orders(id, customer_id, order_date, total_amount, city)
order_items(id, order_id, product_id, quantity)
returns(id, order_id, reason, return_date)

Relationships:
orders.customer_id  -> customers.id
order_items.order_id -> orders.id
order_items.product_id -> products.id
returns.order_id -> orders.id

Notes: is_repeat is 1 for repeat customers, 0 otherwise.
Dates are stored as TEXT in YYYY-MM-DD format."""

VALID_TABLES = {"customers", "products", "orders", "order_items", "returns"}

# Default LLM. Qwen2.5-Coder returns clean SQL (no markdown fences) and is
# available on the free Hugging Face Inference API.
DEFAULT_MODEL = "Qwen/Qwen2.5-Coder-32B-Instruct"
AVAILABLE_MODELS = [
    "Qwen/Qwen2.5-Coder-32B-Instruct",
    "meta-llama/Llama-3.1-8B-Instruct",
    "Qwen/Qwen2.5-7B-Instruct",
]


# ---------------------------------------------------------------------------
# Running SQL against the database
# ---------------------------------------------------------------------------
def run_sql(sql: str):
    """Execute a query and return rows, or an error string. Thread-safe."""
    try:
        with _DB_LOCK:
            _cur.execute(sql)
            return _cur.fetchall()
    except Exception as e:  # noqa: BLE001 — surface any SQL error to the caller
        return f"SQL ERROR: {e}"


def run_sql_with_columns(sql: str):
    """Execute a query and return (rows, column_names). Used by the UI table."""
    try:
        with _DB_LOCK:
            _cur.execute(sql)
            rows = _cur.fetchall()
            cols = [d[0] for d in _cur.description] if _cur.description else []
        return rows, cols
    except Exception as e:  # noqa: BLE001
        return f"SQL ERROR: {e}", []


def table_overview():
    """Return [(table, row_count)] for the 'Database' tab in the dashboard."""
    overview = []
    for t in sorted(VALID_TABLES):
        count = run_sql(f"SELECT COUNT(*) FROM {t}")
        overview.append((t, count[0][0] if isinstance(count, list) else count))
    return overview


# ===========================================================================
# Phase A — Rule-based NL-to-SQL
# ===========================================================================
def rule_based_nl2sql(question: str):
    """Spot keywords and stitch SQL together. Predictable, but brittle."""
    q = question.lower()

    # Rule 1: counting orders, optionally by city
    if "how many orders" in q:
        for city in ["mumbai", "delhi", "bengaluru", "chennai", "kolkata", "pune", "hyderabad"]:
            if city in q:
                return f"SELECT COUNT(*) FROM orders WHERE LOWER(city)='{city}'"
        return "SELECT COUNT(*) FROM orders"

    # Rule 2: total revenue
    # (parentheses added vs. the case-study draft so the intent is explicit)
    if "total revenue" in q or ("how much" in q and "sold" in q):
        return "SELECT SUM(total_amount) FROM orders"

    # Rule 3: number of customers
    if "how many customers" in q:
        return "SELECT COUNT(*) FROM customers"

    return None  # no rule matched


# ===========================================================================
# Phase B — LLM-based NL-to-SQL (schema in the prompt)
# ===========================================================================
_CLIENTS: dict[str, object] = {}  # cache InferenceClient per token


def _resolve_token(token: str | None) -> str:
    """Prefer an explicit token (from the dashboard), else the HF_TOKEN env."""
    return (token or os.getenv("HF_TOKEN") or "").strip()


def _get_client(token: str):
    """Return a cached Hugging Face InferenceClient for this token."""
    from huggingface_hub import InferenceClient

    if token not in _CLIENTS:
        _CLIENTS[token] = InferenceClient(api_key=token)
    return _CLIENTS[token]


def _clean_sql(text: str) -> str:
    """Strip markdown fences, 'SQL:' labels and trailing statements."""
    s = (text or "").strip()

    # Pull SQL out of a ```sql ... ``` fence if the model added one
    fenced = re.search(r"```(?:sql)?\s*(.*?)```", s, re.DOTALL | re.IGNORECASE)
    if fenced:
        s = fenced.group(1)

    s = re.sub(r"^\s*SQL\s*:\s*", "", s, flags=re.IGNORECASE)
    s = s.strip().strip("`").strip()

    # Keep only the first statement so a stray second query can't run
    if ";" in s:
        s = s.split(";")[0].strip()
    return s


def build_prompt(question: str, schema: str = SCHEMA) -> str:
    return f"""You are a translator from English to SQLite SQL.
Given this database schema:
{schema}

Translate this question into ONE valid SQLite query.
Return ONLY the SQL, no explanation, no markdown fences.

Question: {question}
SQL:"""


def llm_nl2sql(
    question: str,
    token: str | None = None,
    model: str = DEFAULT_MODEL,
    schema: str = SCHEMA,
    temperature: float = 0.0,
) -> str:
    """Translate an English question into SQL using a Hugging Face LLM."""
    token = _resolve_token(token)
    if not token:
        raise ValueError(
            "No Hugging Face API token provided. Paste your token into the "
            "dashboard's API-key box, or set the HF_TOKEN environment variable."
        )

    client = _get_client(token)
    response = client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": build_prompt(question, schema)}],
        max_tokens=256,
        temperature=temperature,
    )
    return _clean_sql(response.choices[0].message.content)


# ===========================================================================
# Phase C — Guardrails (trust by design)
# ===========================================================================
FORBIDDEN = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE", "REPLACE"]


def is_safe(sql: str) -> bool:
    """Guardrail 1 — read-only. Reject anything that could modify data."""
    upper = (sql or "").upper()
    return not any(word in upper for word in FORBIDDEN)


def references_only_real_tables(sql: str):
    """Guardrail 2 — every FROM/JOIN target must be a real table."""
    referenced = re.findall(r"FROM\s+(\w+)|JOIN\s+(\w+)", sql or "", re.IGNORECASE)
    tables = {t for pair in referenced for t in pair if t}
    unknown = tables - VALID_TABLES
    return (len(unknown) == 0, unknown)


def trusted_nl2sql(
    question: str,
    token: str | None = None,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.0,
) -> dict:
    """The production path: translate, screen, run — and ALWAYS return the SQL."""
    try:
        sql = llm_nl2sql(question, token=token, model=model, temperature=temperature)
    except Exception as e:  # noqa: BLE001 — show config/model errors to the user
        return {"status": "ERROR", "reason": str(e), "sql": ""}

    # Guardrail 1 — block dangerous operations
    if not is_safe(sql):
        return {"status": "BLOCKED", "reason": "Dangerous operation", "sql": sql}

    # Guardrail 2 — validate tables exist
    ok, unknown = references_only_real_tables(sql)
    if not ok:
        return {"status": "BLOCKED", "reason": f"Unknown table(s): {unknown}", "sql": sql}

    # Guardrail 3 — run, but always hand back the SQL for human review
    result = run_sql(sql)
    return {
        "status": "OK",
        "sql": sql,
        "answer": result,
        "note": "Review the SQL above before trusting this number.",
    }
