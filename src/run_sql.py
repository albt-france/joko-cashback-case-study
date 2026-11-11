"""Load the CSV tables into DuckDB and run every query of sql/ -> data/output/<query>.csv

- data/public/*.csv     -> data/public/joko_public.duckdb      (PUBLIC DATA)
- data/simulated/*.csv  -> data/simulated/joko_sim.duckdb      (SIMULATED), + semantic layer views
Queries 01-05 and 07 run on the public database, 06 on the simulated one.
Each .sql file ends with ONE final SELECT whose result is exported.
"""
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "output"


def load(db_path, folder, tables):
    db_path.unlink(missing_ok=True)
    con = duckdb.connect(str(db_path))
    for t, f in tables.items():
        path = (folder / f).as_posix()
        if (folder / f).exists():
            con.execute(f"CREATE TABLE {t} AS SELECT * FROM read_csv_auto('{path}', header=true)")
    return con


def run_file(con, sql_path):
    """Run all statements of a file; export the result of the last SELECT."""
    statements = [s.strip() for s in sql_path.read_text(encoding="utf-8").split(";") if s.strip()]
    statements = [s for s in statements if any(not ln.strip().startswith("--") for ln in s.splitlines())]
    *setup, final = statements
    for s in setup:
        con.execute(s)
    df = con.execute(final).fetchdf()
    df.to_csv(OUT / f"{sql_path.stem}.csv", index=False)
    print(f"  {sql_path.stem}: {len(df)} rows")
    return df


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    pub = load(ROOT / "data" / "public" / "joko_public.duckdb", ROOT / "data" / "public", {
        "dim_merchant": "dim_merchant.csv", "fct_cashback_offer": "fct_cashback_offer.csv",
        "dim_app": "dim_app.csv", "fct_joko_versions": "fct_joko_versions.csv",
        "fct_app_rating_history": "fct_app_rating_history.csv",
        "fct_app_reviews": "fct_app_reviews_themed.csv" if (ROOT / "data/public/fct_app_reviews_themed.csv").exists() else "fct_app_reviews.csv",
        "fct_search_interest": "fct_search_interest.csv", "fct_joko_home_claims": "fct_joko_home_claims.csv"})
    sim = load(ROOT / "data" / "simulated" / "joko_sim.duckdb", ROOT / "data" / "simulated", {
        "users": "users.csv", "events": "events.csv.gz", "purchases": "purchases.csv",
        "payouts": "payouts.csv", "merchants": "merchants_used.csv"})
    sim.execute((ROOT / "sql" / "00_semantic_layer.sql").read_text(encoding="utf-8"))
    print("PUBLIC queries")
    for f in sorted((ROOT / "sql").glob("0[1-57]_*.sql")):
        try:
            run_file(pub, f)
        except duckdb.Error as exc:
            print(f"  {f.stem}: skipped ({str(exc).splitlines()[0][:120]})")
    print("SIMULATED queries")
    for f in sorted((ROOT / "sql").glob("06_*.sql")):
        run_file(sim, f)
    pub.close()
    sim.close()


if __name__ == "__main__":
    main()
