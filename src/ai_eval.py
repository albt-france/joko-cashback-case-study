"""Evaluate "Ask the data" on a fixed set of questions with known answers (SIMULATED + AI).

For each question in eval/questions.yaml:
- the reference answer comes from a hand-written SQL query (read-only connection);
- the assistant answers (ai_ask_data.ask);
- correct = the reference value is found in the assistant's SQL result (numbers: 0.5% / 0.05 tolerance;
  labels: same first value), or, for out-of-scope questions, the assistant refused;
- invented_numbers = numbers in the written answer that are not in the SQL result (must be 0);
- cost (USD) and latency (s) per question.
Output: eval/results.csv and eval/summary.json. Without an API key: "evaluation pending".
"""
import json

import duckdb
import pandas as pd
import yaml

from ai_ask_data import DB_PATH, ask
from ai_common import ROOT, has_key


def reference(sql):
    con = duckdb.connect(str(DB_PATH), read_only=True)
    try:
        return con.execute(sql).fetchone()[0]
    finally:
        con.close()


def is_correct(check, ref, out):
    if check == "refuse":
        return out["status"] in ("refused", "blocked_by_guardrail")
    if out["status"] not in ("answered", "answer_rejected_numbers"):
        return False
    rows = out.get("result") or []
    if not rows:
        return False
    if check == "label":
        first = list(rows[0].values())[0]
        return str(first).strip().lower()[:7] == str(ref).strip().lower()[:7] if "-" in str(ref) else \
            str(first).strip().lower() == str(ref).strip().lower()
    ref = float(ref)
    for row in rows:
        for v in row.values():
            if isinstance(v, (int, float)) and abs(float(v) - ref) <= max(0.05, 0.005 * abs(ref)):
                return True
    return False


def guardrail_tests():
    """SQL that the allow-list must block (and one it must let through). Returns 'passed/total'."""
    from ai_ask_data import check_sql
    must_block = [
        "SELECT * FROM users",                                   # raw table, not a semantic view
        "SELECT * FROM read_csv('data/simulated/users.csv')",    # file access
        "DELETE FROM v_user_metrics",                            # write
        "SELECT 1; DROP TABLE purchases",                        # two statements
        "COPY v_user_metrics TO 'out.csv'",                      # export
        "ATTACH 'other.duckdb' AS o",                            # other database
    ]
    must_pass = ["WITH c AS (SELECT * FROM v_user_metrics) SELECT count(*) FROM c"]
    ok = sum(check_sql(s) is not None for s in must_block) + sum(check_sql(s) is None for s in must_pass)
    return f"{ok}/{len(must_block) + len(must_pass)}"


def main():
    questions = yaml.safe_load((ROOT / "eval" / "questions.yaml").read_text(encoding="utf-8"))
    if not has_key():
        pd.DataFrame(questions).assign(status="evaluation pending").to_csv(ROOT / "eval" / "results.csv", index=False)
        print("No API key: evaluation pending")
        return
    rows = []
    for q in questions:
        ref = reference(q["sql"]) if q["check"] != "refuse" else None
        out = ask(q["question"])
        ok = is_correct(q["check"], ref, out)
        rows.append({"id": q["id"], "question": q["question"], "check": q["check"], "reference": ref,
                     "status": out["status"], "correct": ok, "invented_numbers": out.get("invented_numbers", 0),
                     "cost_usd": out.get("cost_usd"), "latency_s": out.get("latency_s"),
                     "generated_sql": out.get("sql", ""), "answer": out.get("answer", "")})
        print(f"{q['id']}: {'OK ' if ok else 'NO '} {out['status']}")
    df = pd.DataFrame(rows)
    df.to_csv(ROOT / "eval" / "results.csv", index=False)
    from ai_ask_data import checker_self_test
    summary = {"number_checker_self_test_passed": checker_self_test(),
               "guardrail_tests_passed": guardrail_tests(),
               "questions": len(df), "correct": int(df["correct"].sum()),
               "in_scope_questions": int((df["check"] != "refuse").sum()),
               "in_scope_correct": int(df.loc[df["check"] != "refuse", "correct"].sum()),
               "out_of_scope_refused": int(df.loc[df["check"] == "refuse", "correct"].sum()),
               "invented_numbers_total": int(df["invented_numbers"].sum()),
               "avg_cost_usd": round(df["cost_usd"].mean(), 5), "total_cost_usd": round(df["cost_usd"].sum(), 4),
               "median_latency_s": round(df["latency_s"].median(), 2)}
    (ROOT / "eval" / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
