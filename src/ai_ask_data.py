"""'Ask the data': a business user asks a question in English or French, the model writes SQL on a
documented semantic layer, the SQL runs read-only, and the answer is checked against the result.
(SIMULATED data + AI)

Guardrails, in the order they apply:
1. Scope: the model must answer {"in_scope": false} for questions the semantic layer cannot answer
   (e.g. data about real Joko users, other companies, personal data, predictions of the future).
2. Allow-list: the SQL may only read the three semantic views (v_monthly_kpis, v_user_metrics,
   v_purchases_enriched). Any other table, file function or write keyword is rejected before execution.
3. Read-only engine: DuckDB is opened with read_only=True and external access disabled.
4. Row limit: results are capped at 200 rows (an outer LIMIT is added).
5. Transparency: the generated SQL is always returned and shown to the user.
6. Number check: every number in the written answer must appear in the SQL result (after rounding);
   if not, the answer is rejected and the raw table is shown instead. This counts "invented numbers".

Usage:  python src/ai_ask_data.py "How many users were activated in March 2026 in France?"
"""
import json
import re
import sys

import duckdb

from ai_common import ROOT, call_json, has_key

DB_PATH = ROOT / "data" / "simulated" / "joko_sim.duckdb"
ALLOWED = {"v_monthly_kpis", "v_user_metrics", "v_purchases_enriched"}
FORBIDDEN = re.compile(
    r"\b(insert|update|delete|create|drop|alter|attach|detach|copy|export|import|pragma|install|load|"
    r"call|set|read_csv|read_parquet|read_json|read_text|glob|httpfs|system)\b", re.I)
MAX_ROWS = 200

SEMANTIC_DOC = """
Data: SIMULATED cashback-app data, 2025-05-01 to 2026-10-31, countries FR and US. Amounts in EUR.

VIEW v_monthly_kpis  -- one row per (month, country)
  month DATE (first day of month), country VARCHAR ('FR','US'),
  new_users INT (sign-ups in the month), mau INT (users with >=1 session in the month),
  purchases INT (tracked purchases in the month), gmv_eur DOUBLE (purchase amount),
  validated_cashback_eur DOUBLE (cashback of purchases validated in the month),
  cashback_cost_per_mau_eur DOUBLE (= validated_cashback_eur / mau),
  median_validation_days DOUBLE (median purchase-to-validation delay of purchases validated in the month)

VIEW v_user_metrics  -- one row per user
  user_id INT, signup_date DATE, signup_month DATE, country, acquisition_channel
  ('organic','referral','paid_social','app_store_search','influencer'), platform ('ios','android','extension'),
  activated BOOLEAN (>=1 non-cancelled purchase within 30 days of signup),
  retained_d90 BOOLEAN (>=1 session between day 61 and 90 after signup; NULL if signup < 90 days before data end),
  first_validation_days INT (delay of the user's first validated purchase), purchases INT, gmv_eur DOUBLE,
  validated_cashback_eur DOUBLE

VIEW v_purchases_enriched  -- one row per tracked purchase
  purchase_id, user_id, purchase_date DATE, purchase_month DATE, merchant VARCHAR, category VARCHAR,
  country, acquisition_channel, platform, amount_eur DOUBLE, cashback_rate_pct DOUBLE, cashback_eur DOUBLE,
  status ('pending','validated','cancelled'), validation_days INT, validated_date DATE

Rules: rates/percentages as 0-100 rounded to 1 decimal; amounts rounded to 2 decimals.
Activation rate = avg(activated::INT)*100. D90 retention rate = avg(retained_d90::INT)*100 over users where retained_d90 IS NOT NULL.
"""

SQL_SYSTEM = (
    "You translate business questions (English or French) into ONE DuckDB SELECT query over the documented views. "
    "Use only these views and columns. If the question cannot be answered from them (other companies, real users, "
    "personal data, forecasts, opinions), set in_scope=false, sql='' and explain briefly in reason. "
    "Never invent columns. Return short, readable SQL with clear aliases.\n" + SEMANTIC_DOC)
SQL_SCHEMA = {
    "type": "object",
    "properties": {"in_scope": {"type": "boolean"}, "sql": {"type": "string"}, "reason": {"type": "string"}},
    "required": ["in_scope", "sql", "reason"], "additionalProperties": False}

ANSWER_SYSTEM = (
    "You write a one- or two-sentence answer to a business question using ONLY the SQL result given. "
    "Copy numbers exactly as they appear in the result (you may round to fewer decimals). "
    "Do not compute new numbers, do not add context numbers. Answer in the language of the question.")
ANSWER_SCHEMA = {"type": "object", "properties": {"answer": {"type": "string"}},
                 "required": ["answer"], "additionalProperties": False}


# ---------- guardrails ----------------------------------------------------------------------
def check_sql(sql):
    """Return None if the SQL passes the allow-list, otherwise the reason it was rejected."""
    s = sql.strip().rstrip(";")
    if ";" in s:
        return "more than one statement"
    if not re.match(r"^\s*(with|select)\b", s, re.I):
        return "only SELECT queries are allowed"
    if FORBIDDEN.search(s):
        return "forbidden keyword"
    # names read after FROM / JOIN must be allowed views or CTE names defined in the query
    ctes = {m.lower() for m in re.findall(r"(\w+)\s+as\s*\(", s, re.I)}
    sources = {m.lower() for m in re.findall(r"\b(?:from|join)\s+([a-zA-Z_][\w.]*)", s, re.I)}
    bad = sources - ALLOWED - ctes
    if bad:
        return f"table not allowed: {', '.join(sorted(bad))}"
    return None


def run_readonly(sql):
    con = duckdb.connect(str(DB_PATH), read_only=True, config={"enable_external_access": False})
    try:
        limited = f"SELECT * FROM ({sql.strip().rstrip(';')}) AS q LIMIT {MAX_ROWS}"
        return con.execute(limited).fetchdf()
    finally:
        con.close()


def numbers_in(text):
    """All numbers written in a text, as floats ('1 234,5' and '1,234.5' both -> 1234.5)."""
    t = text.replace(" ", " ").replace("\xa0", " ")
    t = re.sub(r"(?<=\d)[ ,](?=\d{3}\b)", "", t)      # thousands separators
    t = re.sub(r"(?<=\d),(?=\d)", ".", t)              # decimal comma
    t = re.sub(r"\b(19|20)\d{2}-\d{2}(-\d{2})?\b", " ", t)  # ISO dates are not "figures"
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", t)]


def unsupported_numbers(answer, df, question=""):
    """Numbers in the answer that cannot be traced to the SQL result (or to the question itself)."""
    import numbers
    allowed = set()
    for v in df.to_numpy().ravel():
        # numbers.Number also covers numpy integers/floats (DuckDB returns numpy types)
        if isinstance(v, numbers.Number) and not isinstance(v, bool) and v == v:
            for nd in range(0, 4):
                allowed.add(round(float(v), nd))
        elif hasattr(v, "year"):
            allowed.update({v.year, v.month, v.day})
    allowed.update(numbers_in(question))
    allowed.update({float(y) for y in range(2020, 2031)})
    # a number is "supported" if it equals a result value up to rounding (0.5% relative, or 0.05 absolute)
    bad = []
    for n in numbers_in(answer):
        if not any(abs(n - a) <= max(0.05, 0.005 * abs(a)) for a in allowed):
            bad.append(n)
    return bad


def checker_self_test():
    """The number check must accept a faithful answer and catch a fabricated one."""
    import pandas as pd
    df = pd.DataFrame({"pending_purchases": [7845], "rate_pct": [38.04]})
    faithful = "There are 7,845 pending purchases and the rate is 38.0%."
    fabricated = "There are 7,845 pending purchases, up 12% on last month."
    return unsupported_numbers(faithful, df) == [] and unsupported_numbers(fabricated, df) == [12.0]


def ask(question):
    if not has_key():
        return {"question": question, "status": "no_api_key", "sql": "", "answer": "evaluation pending (no API key)"}
    out, m1 = call_json(SQL_SYSTEM, question, SQL_SCHEMA, max_tokens=1500, task="ask_sql")
    cost, latency = m1["cost_usd"], m1["latency_s"]
    if not out["in_scope"]:
        return {"question": question, "status": "refused", "sql": "", "answer": out["reason"],
                "cost_usd": cost, "latency_s": latency, "invented_numbers": 0}
    sql = out["sql"]
    reason = check_sql(sql)
    if reason:
        return {"question": question, "status": "blocked_by_guardrail", "sql": sql, "answer": reason,
                "cost_usd": cost, "latency_s": latency, "invented_numbers": 0}
    try:
        df = run_readonly(sql)
    except Exception as exc:
        return {"question": question, "status": "sql_error", "sql": sql, "answer": str(exc)[:300],
                "cost_usd": cost, "latency_s": latency, "invented_numbers": 0}
    result_text = df.head(50).to_csv(index=False)
    ans, m2 = call_json(ANSWER_SYSTEM, f"Question: {question}\n\nSQL result (CSV):\n{result_text}",
                        ANSWER_SCHEMA, max_tokens=600, task="ask_answer")
    bad = unsupported_numbers(ans["answer"], df, question)
    return {"question": question, "status": "answered" if not bad else "answer_rejected_numbers",
            "sql": sql, "answer": ans["answer"] if not bad else f"[rejected: unsupported numbers {bad}] raw table shown",
            "result": json.loads(df.head(20).to_json(orient="records", date_format="iso")),
            "invented_numbers": len(bad), "cost_usd": round(cost + m2["cost_usd"], 6),
            "latency_s": round(latency + m2["latency_s"], 2)}


if __name__ == "__main__":
    q = " ".join(sys.argv[1:]) or "What was the D90 retention rate of users who signed up in January 2026?"
    print(json.dumps(ask(q), indent=1, ensure_ascii=False, default=str))
