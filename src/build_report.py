"""Build the PDF report: HTML pages (16:9) with matplotlib charts -> PDF with headless Edge/Chrome.

Run after the data, SQL, notebook and AI steps. Output: docs/Joko_DataCaseStudy.pdf and
docs/img/page_XX.png (one screenshot per page, for the README).
Tags in the top-right corner say where the data of the page comes from:
PUBLIC DATA / SIMULATED / PUBLIC + AI / SIMULATED + AI.
"""
import html
import json
import shutil
import subprocess
from pathlib import Path

import matplotlib.dates as mdates
import numpy as np
import pandas as pd

import charts as C

ROOT = Path(__file__).resolve().parents[1]
PUB, OUT, SIM, EVAL = ROOT / "data/public", ROOT / "data/output", ROOT / "data/simulated", ROOT / "eval"
DOCS = ROOT / "docs"
FOOTER_BASE = "Independent case study based on public data · not affiliated with or endorsed by Joko"
AI_NOTE = ("AI-assisted workflow: I used Claude, mainly to write scripts faster. I drove the project: I defined "
           "the questions, chose and validated the data sources, made the analytical decisions and checked every result.")


def read_csv(path, **kw):
    return pd.read_csv(path, **kw) if Path(path).exists() else pd.DataFrame()


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8")) if Path(path).exists() else {}


def esc(s):
    return html.escape(str(s))


# =============================================================================================
# Page shell
# =============================================================================================
CSS = """
@page { size: 1600px 900px; margin: 0; }
* { box-sizing: border-box; }
body { margin: 0; font-family: 'Segoe UI', Arial, sans-serif; color: #0B0B0B; background: #F4F4F2; }
.page { width: 1600px; height: 900px; padding: 34px 44px 26px 44px; position: relative; overflow: hidden;
        background: #F4F4F2; page-break-after: always; display: flex; flex-direction: column; }
.head { display: flex; justify-content: space-between; align-items: flex-start; gap: 30px; }
h1 { font-size: 27px; font-weight: 700; margin: 0 0 6px 0; line-height: 1.18; max-width: 1280px; }
.sub { font-size: 14.5px; color: #52514E; margin: 0 0 16px 0; max-width: 1340px; line-height: 1.4; }
.tag { font-size: 12px; font-weight: 700; letter-spacing: .06em; color: #52514E; white-space: nowrap; padding-top: 8px; }
.grid { display: grid; gap: 14px; flex: 1; min-height: 0; }
.card { background: #FFFFFF; border: 1px solid #E1E0D9; border-radius: 8px; padding: 14px 16px; min-height: 0;
        display: flex; flex-direction: column; overflow: hidden; }
.card h3 { font-size: 13.5px; margin: 0 0 6px 0; font-weight: 600; }
.card .note { font-size: 11.5px; color: #898781; margin-top: 4px; line-height: 1.35; }
.card img { width: 100%; flex: 1; min-height: 0; object-fit: contain; }
.kpi .lab { font-size: 11px; font-weight: 700; color: #52514E; letter-spacing: .05em; }
.kpi .val { font-size: 40px; font-weight: 700; line-height: 1.1; margin: 6px 0 4px 0; }
.kpi .txt { font-size: 13px; color: #52514E; line-height: 1.35; }
.text { font-size: 13.5px; line-height: 1.5; color: #0B0B0B; }
.text p { margin: 0 0 8px 0; }
.text b.blue, .blue { color: #2A78D6; }
.muted { color: #898781; }
ul { margin: 4px 0 6px 18px; padding: 0; } li { margin: 0 0 5px 0; }
table { border-collapse: collapse; font-size: 12.5px; width: 100%; }
th { text-align: left; color: #52514E; font-weight: 600; border-bottom: 1.5px solid #0B0B0B; padding: 4px 6px; }
td { padding: 4px 6px; border-bottom: 1px solid #EEEDE8; vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
.foot { font-size: 10.5px; color: #898781; margin-top: 10px; }
code, pre { font-family: Consolas, monospace; font-size: 11.5px; }
pre { background: #F7F7F5; border: 1px solid #EEEDE8; border-radius: 6px; padding: 8px; margin: 4px 0; white-space: pre-wrap; }
.box { border: 1.5px solid #2A78D6; border-radius: 8px; padding: 8px 10px; font-size: 12.5px; text-align: center; background: #F3F8FE; }
.box.grey { border-color: #A3A099; background: #FAFAF8; }
.arrow { text-align: center; color: #898781; font-size: 20px; line-height: 1; }
.pill { display: inline-block; font-size: 11px; font-weight: 700; color: #52514E; border: 1px solid #E1E0D9;
        border-radius: 10px; padding: 1px 8px; margin-right: 4px; }
"""


def page(title, sub, tag, body, sources, grid_style):
    return f"""
<section class="page">
  <div class="head"><div><h1>{title}</h1><p class="sub">{sub}</p></div><div class="tag">{tag}</div></div>
  <div class="grid" style="{grid_style}">{body}</div>
  <div class="foot">{sources} &nbsp;·&nbsp; {FOOTER_BASE}</div>
</section>"""


def card(title, content, note="", style="", cls="card"):
    n = f'<div class="note">{note}</div>' if note else ""
    h = f"<h3>{title}</h3>" if title else ""
    return f'<div class="{cls}" style="{style}">{h}{content}{n}</div>'


def kpi(label, value, text, color="#0B0B0B", style=""):
    return (f'<div class="card kpi" style="{style}"><div class="lab">{label}</div>'
            f'<div class="val" style="color:{color}">{value}</div><div class="txt">{text}</div></div>')


# =============================================================================================
# Data loading (everything the pages need, computed once)
# =============================================================================================
def load():
    d = {}
    d["dm"] = read_csv(PUB / "dim_merchant.csv")
    d["fo"] = read_csv(PUB / "fct_cashback_offer.csv")
    d["apps"] = read_csv(PUB / "dim_app.csv")
    d["trends"] = read_csv(PUB / "fct_search_interest.csv", parse_dates=["date"])
    d["timeline"] = read_csv(PUB / "company_timeline.csv", parse_dates=["date"])
    d["rating_hist"] = read_csv(PUB / "fct_app_rating_history.csv", parse_dates=["snapshot"])
    d["claims"] = read_csv(PUB / "fct_joko_home_claims.csv", parse_dates=["snapshot"])
    d["versions"] = read_csv(PUB / "fct_joko_versions.csv", parse_dates=["release_date"])
    d["reviews"] = read_csv(PUB / "fct_app_reviews_themed.csv", parse_dates=["date"])
    d["cat"] = read_csv(OUT / "01_offer_by_category.csv")
    d["pairs"] = read_csv(OUT / "02_rate_comparison.csv")
    d["boost"] = read_csv(OUT / "03_boost_frequency.csv")
    d["wb"] = read_csv(OUT / "04_wayback_evolution.csv")
    d["delays"] = read_csv(OUT / "07_validation_delays.csv")
    d["m7"] = read_csv(OUT / "06_page7_metrics.csv", parse_dates=["signup_month"])
    d["gapcat"] = read_csv(OUT / "nb_rate_gap_by_category.csv")
    d["calib"] = read_csv(OUT / "nb_retention_calibration.csv")
    d["coef"] = read_csv(OUT / "nb_retention_coefficients.csv")
    d["nb"] = read_json(OUT / "nb_summary.json")
    d["assist"] = read_json(OUT / "nb_assistant_effect.json")
    d["eval"] = read_json(EVAL / "summary.json")
    d["eval_rows"] = read_csv(EVAL / "results.csv")
    d["val"] = read_json(EVAL / "review_validation_summary.json")
    import duckdb
    con = duckdb.connect(str(SIM / "joko_sim.duckdb"), read_only=True)
    d["kpis"] = con.execute("SELECT * FROM v_monthly_kpis ORDER BY month").fetchdf()
    d["users_overall"] = con.execute("""SELECT round(100*avg(activated::INT),1) act,
        round(100*avg(retained_d90::INT) FILTER (WHERE retained_d90 IS NOT NULL),1) ret,
        round(100*avg(retained_d90::INT) FILTER (WHERE activated AND retained_d90 IS NOT NULL),1) ret_act,
        round(100*avg(retained_d90::INT) FILTER (WHERE NOT activated AND retained_d90 IS NOT NULL),1) ret_not
        FROM v_user_metrics""").fetchdf().iloc[0].to_dict()
    con.close()
    return d


# =============================================================================================
# Pages
# =============================================================================================
def p1_public(d):
    tl = d["timeline"]
    # (a) milestones
    f, ax = C.fig(7.4, 2.5)
    ms = tl.drop_duplicates("event").copy()
    keep = ms[ms["event"].str.contains("founded|first released|EUR 10M|US App Store|Official US launch|Job posting: B Corp", regex=True)]
    labels = {"founded": "Founded in Paris", "first released": "iOS app (France)", "EUR 10M": "EUR 10M round\n500k users",
              "US App Store": "App on US\nApp Store", "Official US launch": "US launch +\nAI assistant Juno",
              "Job posting: B Corp": "7M+ users, B Corp,\nprofitable core market"}
    ax.axhline(0, color=C.GRID, lw=2)
    for i, r in enumerate(keep.sort_values("date").itertuples()):
        lab = next(v for k, v in labels.items() if k in r.event)
        up = 1 if i % 2 == 0 else -1
        ax.plot([r.date, r.date], [0, 0.55 * up], color=C.GREY, lw=1)
        ax.scatter([r.date], [0], s=46, color=C.BLUE, zorder=3)
        when = f"{r.date:%Y}" if r.date_precision == "year" else f"{r.date:%b %Y}"
        ax.text(r.date, 0.62 * up, f"{when}\n{lab}", ha="center", va="bottom" if up > 0 else "top", fontsize=8.2, color=C.INK2)
    ax.set_ylim(-1.6, 1.6)
    ax.set_yticks([])
    ax.grid(False)
    ax.spines["bottom"].set_visible(False)
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    timeline_img = C.to_img(f)

    # (b) users claimed in public sources
    u = tl[tl["metric"] == "users"].sort_values("date")
    f, ax = C.fig(3.6, 2.6)
    ax.plot(u["date"], u["value"] / 1e6, color=C.BLUE, lw=1, ls=":", marker="o", ms=7)  # only 3 published points
    for r in u.itertuples():
        ax.annotate(f"{r.value / 1e6:.1f}M", (r.date, r.value / 1e6), textcoords="offset points", xytext=(-4, 7),
                    ha="right", fontsize=9, color=C.INK2)
    ax.set_ylabel("users (millions, as stated)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    users_img = C.to_img(f)

    # (c) search interest France
    tr = d["trends"]
    trends_img, tr_note = "", ""
    if len(tr):
        fr = tr[tr["geo"] == "FR"].copy()
        fr["q"] = fr["date"].dt.to_period("Q").dt.start_time
        q = fr.groupby(["q", "term"])["interest"].mean().reset_index()
        f, ax = C.fig(5.2, 2.6)
        for term, g in q.groupby("term"):
            isj = term == "Joko"
            ax.plot(g["q"], g["interest"], color=C.BLUE if isj else C.GREY, lw=2.2 if isj else 1.2,
                    alpha=1 if isj else .9)
            ax.text(g["q"].iloc[-1], g["interest"].iloc[-1], f" {term}", fontsize=8.5, va="center",
                    color=C.BLUE if isj else C.INK2)
        ax.set_ylabel("search interest (0-100)")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
        trends_img = C.to_img(f)
        last = fr[fr["date"] >= fr["date"].max() - pd.Timedelta(days=365)].groupby("term")["interest"].mean()
        lead = last.sort_values(ascending=False)
        tr_note = (f"Last 12 months, France, average interest: " +
                   ", ".join(f"{k} {v:.0f}" for k, v in lead.items()) + ". Quarterly averages of weekly values.")
    fr_app = d["apps"][(d["apps"]["country"] == "fr")]
    joko_fr = fr_app[fr_app["app_name"].str.contains("Joko")].iloc[0]
    rivals = fr_app[~fr_app["app_name"].str.contains("Joko")]
    ratio = joko_fr["rating_count"] / rivals["rating_count"].max()
    fr_tr = tr[tr["geo"] == "FR"] if len(tr) else tr

    def yr_mean(term, year):
        s = fr_tr[(fr_tr["term"] == term) & (fr_tr["date"].dt.year == year)]["interest"]
        return s.mean() if len(s) else np.nan
    j_mult = yr_mean("Joko", 2026) / yr_mean("Joko", 2022)
    title = (f"Joko grew from 500k users (2020) to 7M+ (2026): the largest App Store base among French cashback apps, "
             f"with search interest up {j_mult:.0f}x since 2022")
    sub = (f"Company milestones from primary sources, the user numbers Joko itself published, and Google search interest. "
           f"On the App Store, Joko has {joko_fr['rating_count']:,.0f} ratings in France, {ratio:.1f}x the next French cashback app.")
    body = (card("Milestones (primary sources)", timeline_img, style="grid-column: 1 / 3;") +
            kpi("PUBLIC · JOB POSTING 2026", "7M+", "users and 10,000+ merchants; B Corp; 120+ people in Paris, Barcelona, New York") +
            card("Users, as published by Joko", users_img, "500k (Oct 2020 funding release) → 6M (Sept 2026 US launch release) → 7M+ (Nov 2026 job posting).") +
            card("Google search interest, France, 5 years", trends_img, tr_note) +
            kpi("PUBLIC · APP STORE FRANCE", f"{joko_fr['rating_count'] / 1000:.0f}k",
                f"ratings, average {joko_fr['avg_rating']:.2f}/5 — {ratio:.1f}x the next French cashback app "
                f"({rivals.sort_values('rating_count').iloc[-1]['app_name'].split(':')[0].split('-')[0].strip()})", color=C.BLUE))
    return page(title, sub, "PUBLIC DATA", body,
                "Sources: Partech release (Oct 2020), PR Newswire (Sept 2026), Joko job posting & homepage (Nov 2026), iTunes Search API, Google Trends; collected 2026-11-11",
                "grid-template-columns: 1.15fr 1.35fr 0.8fr; grid-template-rows: 1fr 1.05fr;")


def p2_offer(d):
    cat = d["cat"].dropna(subset=["median_rate_pct"]).sort_values("median_rate_pct", ascending=False)
    fo, dm = d["fo"], d["dm"]
    overall_med = fo.loc[fo["rate_type"] == "percent", "rate_value"].median()
    f, ax = C.fig(5.0, 5.4)
    colors = [C.BLUE if v >= cat["median_rate_pct"].quantile(0.8) else C.GREY for v in cat["median_rate_pct"]]
    C.hbar(ax, cat["category"], cat["median_rate_pct"], colors, fmt="{:.1f}%", xlabel="median cashback rate (%), both platforms")
    ax.axvline(overall_med, color=C.INK2, ls="--", lw=1)
    ax.text(overall_med, -0.9, f" all merchants: {overall_med:.1f}%", fontsize=8.5, color=C.INK2)
    cat_img = C.to_img(f)

    b = d["boost"]
    plat = b[b["category"].isna() & b["platform"].notna()]
    allb = b[b["category"].isna() & b["platform"].isna()].iloc[0]
    bc = (d["fo"].merge(d["dm"][["merchant_id", "category"]], on="merchant_id").groupby("category")["is_boosted"]
          .agg(["mean", "size"]).query("size >= 20").sort_values("mean", ascending=False).head(8))
    f, ax = C.fig(4.4, 2.9)
    C.hbar(ax, list(bc.index), (bc["mean"] * 100).to_numpy(), [C.GREY] * len(bc), fmt="{:.0f}%",
           xlabel="% of offers boosted today (both platforms)")
    ax.axvline(allb["share_boosted_pct"], color=C.INK2, ls="--", lw=1)
    boost_img = C.to_img(f)

    dl = d["delays"]
    widilo = fo[(fo["platform"] == "Widilo") & fo["validation_days_announced"].notna()]
    share60 = (widilo["validation_days_announced"] > 60).mean() * 100
    med_delay = widilo["validation_days_announced"].median()
    fixed_share = (fo["rate_type"] == "fixed").mean() * 100
    top = cat.iloc[0]
    title = (f"The French market pays a median {overall_med:.1f}% cashback (up to {top['median_rate_pct']:.0f}% in {top['category'].lower()}); "
             f"1 offer in {round(100 / allb['share_boosted_pct'])} is boosted and confirmation takes ~2 months")
    sub = (f"Market benchmark from {len(dm)} merchants listed on Widilo and iGraal (France, snapshot of 11 Nov 2026). Joko's own rates "
           f"are only visible inside its app, so this page describes the market Joko competes in, not Joko's offer.")
    body = (card("Median cashback rate by category (percentage offers)", cat_img,
                 f"Blue = top fifth of categories. Dashed = median of all percentage offers. {fixed_share:.0f}% of offers are a fixed amount (EUR), mostly subscriptions, energy and finance.",
                 style="grid-row: 1 / 3;") +
            kpi("PUBLIC · WIDILO + IGRAAL", f"{allb['share_boosted_pct']:.0f}%",
                f"of offers carry a temporary boost; the median boost multiplies the usual rate by {allb['median_boost_multiplier']:.1f}") +
            kpi("PUBLIC · WIDILO", f"{med_delay / 30.4:.0f} months", f"median announced delay before cashback is confirmed; {share60:.0f}% of merchants announce more than 60 days",
                color=C.RED) +
            card("Boosted offers by category (8 most boosted, 20+ offers)", boost_img,
                 "Dashed = all offers. By platform: " + ", ".join(f"{r.platform} {r.share_boosted_pct:.0f}%" for r in plat.itertuples()) +
                 ". A boost is flagged by the platform itself (au lieu de X%).") +
            card("What it means for a cashback app", f"""<div class="text">
                <p><b>{top['category']}</b> and other high-rate categories carry the largest commissions, but also the longest and most uncertain confirmations.</p>
                <p>Boosts are a standard acquisition tool: about one offer in {round(100 / allb['share_boosted_pct'])} is boosted on any given day.</p>
                <p>The ~2-month wait is structural (merchants' return periods). It is not the main complaint in the reviews visible today (page 5),
                but it is the obvious hypothesis for early churn: page 7 shows how to measure it.</p></div>"""))
    return page(title, sub, "PUBLIC DATA", body,
                "Sources: widilo.fr category pages (93), fr.igraal.com merchant pages (411); collected 2026-11-11; see data/SOURCES.md",
                "grid-template-columns: 1.1fr 1fr 1fr; grid-template-rows: 0.5fr 1fr;")


def outcome_bar(nb):
    """A 100% bar (HTML) showing Widilo higher / tie / iGraal higher, with labels."""
    a, t, c = nb.get("share_widilo_higher", 0), nb.get("share_tie", 0), nb.get("share_igraal_higher", 0)

    def seg(w, col, lab):
        return (f"<div style='width:{w * 100:.1f}%;background:{col};color:white;font-size:11px;"
                f"padding:6px 4px;white-space:nowrap;overflow:hidden'>{lab}</div>")
    return ("<div style='display:flex;gap:2px;margin-top:14px;border-radius:4px;overflow:hidden'>" +
            seg(a, C.GREY, f"Widilo higher {a * 100:.0f}%") + seg(t, C.GREY_LIGHT, "") +
            seg(c, C.INK2, f"iGraal {c * 100:.0f}%") + "</div>")


def p3_competition(d):
    pairs, nb = d["pairs"], d["nb"].get("rates", {})
    gap = pairs["gap_widilo_minus_igraal_pts"]
    f, ax = C.fig(4.8, 2.9)
    bins = np.arange(-6, 6.5, 0.5)
    ax.hist(gap.clip(-6, 6), bins=bins, color=C.GREY, edgecolor=C.CARD)
    ax.axvline(0, color=C.INK2, ls="--", lw=1)
    ax.axvline(gap.median(), color=C.BLUE, lw=2)
    ax.text(gap.median(), ax.get_ylim()[1] * 0.92, f"  median +{gap.median():.1f} pt", color=C.BLUE, fontsize=9)
    ax.set_xlabel("Widilo rate minus iGraal rate, same merchant (points, clipped at ±6)")
    ax.set_ylabel("merchants")
    hist_img = C.to_img(f)

    gc = d["gapcat"].sort_values("median_gap_pts")
    f, ax = C.fig(4.4, 4.6)
    y = np.arange(len(gc))
    ax.errorbar(gc["median_gap_pts"], y, xerr=[gc["median_gap_pts"] - gc["ci_low"], gc["ci_high"] - gc["median_gap_pts"]],
                fmt="o", color=C.GREY, ecolor=C.GREY_LIGHT, elinewidth=3, ms=6)
    ax.axvline(0, color=C.INK2, ls="--", lw=1)
    ax.set_yticks(y, [f"{c} (n={n})" for c, n in zip(gc["category"], gc["n"])])
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("median gap, points (95% bootstrap CI)")
    cat_img = C.to_img(f)

    apps = d["apps"][d["apps"]["country"] == "fr"].sort_values("rating_count", ascending=False)
    f, ax = C.fig(4.4, 2.3)
    names = [a.split(":")[0].split("-")[0].split("|")[0].strip().split(" ")[0] for a in apps["app_name"]]
    C.hbar(ax, names, apps["rating_count"] / 1000, [C.BLUE if "Joko" in n else C.GREY for n in names], fmt="{:.0f}k")
    for i, r in enumerate(apps.itertuples()):
        big = r.rating_count > apps["rating_count"].max() * 0.25
        ax.text(r.rating_count / 1000 / 2 if big else r.rating_count / 1000 + apps["rating_count"].max() / 1000 * 0.09, i,
                f"avg {r.avg_rating:.2f}", va="center", ha="center" if big else "left", fontsize=8,
                color="white" if big else C.INK2)
    ax.set_xlabel("App Store ratings, France (thousands)")
    app_img = C.to_img(f)
    lo, hi = nb.get("median_gap_ci95", [np.nan, np.nan])
    title = (f"For the same merchant, two French platforms pay rates ~{abs(gap.median()):.0f} point apart: the rate is a thin edge, "
             f"while Joko leads on scale")
    sub = (f"{len(pairs)} merchants with a percentage rate on both Widilo and iGraal the same day. Median gap +{gap.median():.1f} pt "
           f"(95% CI {lo:.2f} to {hi:.2f}; Wilcoxon p < 0.001), i.e. a relative gap of about {nb.get('median_relative_gap_pct', 0):.0f}%. "
           f"Joko is not in the rate comparison (its rates are not public); its public footprint is shown on the right.")
    body = (card("Distribution of the rate gap", hist_img,
                 "Widilo's category pages showcase its most promoted merchants, so its premium is an upper bound.") +
            kpi(f"PUBLIC · {len(pairs)} MERCHANTS", f"{nb.get('share_widilo_higher', 0) * 100:.0f}%",
                f"of shared merchants pay more on the challenger (Widilo); {nb.get('share_tie', 0) * 100:.0f}% tie; "
                f"{nb.get('share_igraal_higher', 0) * 100:.0f}% pay more on the incumbent (iGraal)" + outcome_bar(nb)) +
            card("Gap by category (categories with 15+ merchants)", cat_img, style="grid-row: 1 / 3; grid-column: 3;") +
            card("Public footprint: App Store ratings, France", app_img,
                 "Ratings count = a proxy for installed base and engagement, not market share. avg = average rating out of 5.") +
            card("Reading for Joko", """<div class="text">
                <p>Rates are a thin edge: on most shared merchants one platform pays about a point more than the other,
                and boosts move rates from week to week (page 6). Competing on rate alone is costly.</p>
                <p>Joko's public advantages are elsewhere: by far the largest rated user base, automatic cashback through
                card-linked offers, automatic coupons and an AI assistant. <b class="blue">The data question is which of these
                drives retention</b> (pages 7-8).</p></div>"""))
    return page(title, sub, "PUBLIC DATA", body,
                "Sources: widilo.fr and fr.igraal.com public pages, iTunes Search API; collected 2026-11-11. Test: notebooks/analysis.ipynb",
                "grid-template-columns: 1.15fr 1fr 1.05fr; grid-template-rows: 1fr 1fr;")


def p4_us(d):
    us = d["apps"][d["apps"]["country"] == "us"].sort_values("rating_count", ascending=False)
    us = us[~us["app_name"].str.contains("Honey")]
    names = [a.split(":")[0].split("|")[0].strip() for a in us["app_name"]]
    f, ax = C.fig(4.8, 3.0)
    vals = us["rating_count"].to_numpy()
    ax.barh(range(len(vals)), vals, color=[C.BLUE if "Joko" in n else C.GREY for n in names], height=0.6)
    ax.set_xscale("log")
    ax.set_yticks(range(len(vals)), names)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    for i, v in enumerate(vals):
        ax.text(v * 1.15, i, f"{v / 1e6:.1f}M" if v >= 1e6 else (f"{v / 1e3:.0f}k" if v >= 1e3 else f"{v:,.0f}"),
                va="center", fontsize=8.5, color=C.INK2)
    ax.set_xlabel("App Store ratings, US (log scale)")
    us_img = C.to_img(f)
    joko_us = us[us["app_name"].str.contains("Joko")].iloc[0]
    rak = us[us["app_name"].str.contains("Rakuten")].iloc[0]

    rh = d["rating_hist"]
    hist_img, hist_note = "", "Archived App Store pages (Wayback Machine) not available."
    if len(rh) and (rh["storefront"] == "us").sum() >= 3:
        f, ax = C.fig(4.6, 2.6)
        for sf, g in rh.groupby("storefront"):
            g = g.sort_values("snapshot")
            ax.plot(g["snapshot"], g["rating_count"], marker="o", ms=3.5, lw=1.8,
                    color=C.BLUE if sf == "us" else C.GREY, label="US" if sf == "us" else "France")
        ax.set_yscale("log")
        ax.axvline(pd.Timestamp("2026-09-21"), color=C.INK2, ls="--", lw=1)
        ax.text(pd.Timestamp("2026-09-21"), ax.get_ylim()[0] * 1.3, " US launch\n Sept 2026", fontsize=8, color=C.INK2)
        ax.legend(loc="upper left")
        ax.set_ylabel("Joko App Store ratings (log)")
        hist_img = C.to_img(f)
        hist_note = "Each point = one archived copy of Joko's App Store page (Wayback Machine) or today's page."

    tr = d["trends"]
    tr_img = ""
    if len(tr):
        u = tr[tr["geo"] == "US"].copy()
        u["q"] = u["date"].dt.to_period("Q").dt.start_time
        q = u.groupby(["q", "term"])["interest"].mean().reset_index()
        f, ax = C.fig(4.6, 2.6)
        for term, g in q.groupby("term"):
            isj = term == "Joko"
            ax.plot(g["q"], g["interest"], color=C.BLUE if isj else C.GREY, lw=2.2 if isj else 1.1)
            ax.text(g["q"].iloc[-1], g["interest"].iloc[-1], f" {term}", fontsize=8, va="center", color=C.BLUE if isj else C.INK2)
        ax.set_ylabel("search interest (0-100)")
        tr_img = C.to_img(f)
    gap = rak["rating_count"] / joko_us["rating_count"]
    rh_us = d["rating_hist"][d["rating_hist"]["storefront"] == "us"].sort_values("snapshot")
    mid25 = rh_us[rh_us["snapshot"] <= "2025-07-31"].iloc[-1] if len(rh_us) else None
    growth = (joko_us["rating_count"] / mid25["rating_count"]) if mid25 is not None else np.nan
    title = (f"Joko's US App Store base grew ~{growth:.0f}x since mid-2025 but is still {100 / gap:.1f}% of Rakuten's: "
             f"the US push needs a wedge, not a rate war")
    sub = (f"Joko has been on the US App Store since May 2022 and launched officially in Sept 2026 with Juno. Today: "
           f"{joko_us['rating_count']:,.0f} US ratings (avg {joko_us['avg_rating']:.2f}) vs {rak['rating_count'] / 1000:.0f}k for Rakuten and "
           f"millions for Ibotta, Fetch and Capital One Shopping. US competitors' terms forbid automated collection of their rates, so no rate comparison is made.")
    body = (card("US App Store ratings: Joko vs established apps", us_img, "Blue = Joko. Ratings count is a footprint proxy, not users.",
                 style="grid-row: 1 / 3;") +
            card("Joko's App Store ratings over time", hist_img, hist_note) +
            card("Google search interest, US, 5 years", tr_img,
                 "\"Joko\" is also a common word/name: the US series is an upper bound for the app.") +
            card("Fact-based recommendations for the US push", f"""<div class="text"><ul>
                <li><b>Measure the wedge, not the rate.</b> US incumbents already pay high, well-known rates; Joko's
                differentiator is the AI assistant + automatic cashback. Track Juno-assisted purchases as a first-class metric.</li>
                <li><b>Instrument the first 30 days.</b> With a small base, every early user counts: report activation and
                time-to-first-validated-cashback by acquisition channel weekly (metrics on page 7).</li>
                <li><b>Protect the payout moment.</b> The worst US reviews are about withdrawals blocked for "suspicious activity"
                (page 5): track the share of first withdrawals put on hold and the time to resolve them.</li>
                <li><b>Ratings as an early signal.</b> Watch the US rating count and 1-star share monthly against the French
                trajectory (same app, same metric).</li></ul></div>""", style="grid-column: 2 / 4;"))
    return page(title, sub, "PUBLIC DATA", body,
                "Sources: iTunes Search API, Wayback Machine (apps.apple.com), Google Trends, PR Newswire (21 Sept 2026); collected 2026-11-11",
                "grid-template-columns: 1.1fr 1fr 1fr; grid-template-rows: 1fr 0.95fr;")


def p5_reviews(d):
    rv, val = d["reviews"], d["val"]
    if rv.empty or "primary_theme" not in rv:
        return page("What users say (review themes pending)", "Run src/ai_review_themes.py first.", "PUBLIC + AI", "", "", "")
    rv = rv[rv["primary_theme"].notna()].copy()
    n = len(rv)
    order = rv["primary_theme"].value_counts()
    f, ax = C.fig(4.6, 4.4)
    neg = rv.groupby("primary_theme")["rating"].apply(lambda s: (s <= 2).mean())
    C.hbar(ax, [t.replace("_", " ") for t in order.index], (order / n * 100).to_numpy(),
           [C.RED if neg.get(t, 0) >= 0.5 else C.GREY for t in order.index], fmt="{:.0f}%", xlabel="share of reviews (primary theme)")
    theme_img = C.to_img(f)

    g = rv.groupby("primary_theme").agg(n=("rating", "size"), avg=("rating", "mean")).sort_values("avg")
    g = g[g["n"] >= 3]
    f, ax = C.fig(4.6, 4.4)
    overall = rv["rating"].mean()
    C.hbar(ax, [f"{t.replace('_', ' ')} (n={k})" for t, k in zip(g.index, g["n"])], g["avg"].to_numpy(),
           [C.RED if v < 3 else (C.BLUE if v >= 4.5 else C.GREY) for v in g["avg"]], fmt="{:.1f}", xlabel="average rating (stars)")
    ax.axvline(overall, color=C.INK2, ls="--", lw=1)
    ax.set_xlim(0, 5.9)
    rating_img = C.to_img(f)

    yr = rv.assign(year=rv["date"].dt.year).groupby("year").agg(n=("rating", "size"), avg=("rating", "mean")).reset_index()
    f, ax = C.fig(3.8, 2.2)
    ok = yr["n"] >= 10
    ax.bar(yr["year"], yr["avg"], color=[C.GREY if o else C.GREY_LIGHT for o in ok], width=0.6)
    for r in yr.itertuples():
        ax.text(r.year, r.avg + 0.08, f"{r.avg:.1f}\nn={r.n}", ha="center", fontsize=7.5, color=C.INK2)
    ax.set_ylim(0, 5.8)
    ax.set_ylabel("avg rating")
    ax.grid(axis="x", visible=False)
    year_img = C.to_img(f)

    if val:
        prec_rows = "".join(f"<tr><td>{esc(t.replace('_', ' '))}</td><td class='num'>{v['n']}</td><td class='num'>{v['precision'] * 100:.0f}%</td></tr>"
                            for t, v in sorted(val.get("by_theme", {}).items(), key=lambda x: -x[1]["n"]) if v["n"] >= 3)
        val_html = (f"<div class='kpi'><div class='val' style='font-size:34px'>{val['accuracy'] * 100:.0f}%</div>"
                    f"<div class='txt'>of {val['n']} reviews: AI primary theme = human label "
                    f"(keyword baseline: {val.get('keyword_accuracy', 0) * 100:.0f}%)</div></div>"
                    f"<table><tr><th>theme (n ≥ 3)</th><th class='num'>n</th><th class='num'>precision</th></tr>{prec_rows}</table>")
        val_note = val.get("note", "")
    else:
        val_html, val_note = "<div class='text'>Human validation pending.</div>", ""
    pain_themes = ["payout", "bank_card_linking", "app_ux_bugs", "customer_support", "missing_cashback_tracking",
                   "cashback_validation_delay"]
    pain = rv[rv["primary_theme"].isin(pain_themes)]
    ref_share = (rv["primary_theme"] == "referral_code").mean() * 100
    title = (f"Reviews praise effortless savings; the 1-2 star ones are about getting connected and getting paid, "
             f"and {ref_share:.0f}% of visible reviews are referral-code posts")
    sub = (f"{n} public reviews (App Store France/US incl. archived pages 2019-2026, Firefox add-on), classified by an AI model into a closed list "
           f"of themes and checked by hand on 100. Connection, payout, bug and support reviews average {pain['rating'].mean():.1f} stars vs "
           f"{rv.loc[~rv.index.isin(pain.index), 'rating'].mean():.1f} for the rest. The expected 'cashback validation delay' complaint barely appears. "
           f"Small, non-random sample: read as themes, not as rates.")
    body = (card("What reviews talk about", theme_img,
                 "Red = themes where most reviews are 1-2 stars. Referral-code posts are almost all 5 stars: incentivised reviews lift the visible average.",
                 style="grid-row: 1 / 3;") +
            card("Average rating by theme (themes with 3+ reviews)", rating_img, f"Dashed = all reviews ({overall:.2f} stars). Red below 3, blue 4.5 and above.", style="grid-row: 1 / 3;") +
            card("Rating by year (with number of reviews)", year_img, "Pale bars: fewer than 10 reviews, not interpreted.") +
            card("Classification quality (human check)", val_html, val_note))
    return page(title, sub, "PUBLIC + AI", body,
                "Sources: apps.apple.com (live + Wayback Machine), addons.mozilla.org API; reviewer names never collected, referral codes masked. Model: low-cost LLM via API, closed theme list, JSON schema",
                "grid-template-columns: 1fr 1fr 0.95fr; grid-template-rows: 1fr 1.1fr;")


def p6_dynamics(d):
    # (a) iOS release cadence
    v = d["versions"].sort_values("release_date")
    gaps = v["release_date"].diff().dt.days
    q = v.groupby(v["release_date"].dt.to_period("Q")).size()
    f, ax = C.fig(4.6, 2.8)
    labels = [str(p).replace("Q", " Q") for p in q.index]
    ax.bar(labels, q.to_numpy(), color=C.BLUE, width=0.6)
    for i, n in enumerate(q.to_numpy()):
        ax.text(i, n + 0.3, str(n), ha="center", fontsize=8.5, color=C.INK2)
    ax.set_ylabel("iOS versions released")
    ax.grid(axis="x", visible=False)
    ax.tick_params(axis="x", labelsize=8)
    cadence_img = C.to_img(f)

    # (b) French ratings added per year (Wayback + today)
    wb = d["wb"]
    fr = wb[(wb["storefront"] == "fr") & wb["ratings_added"].notna()]
    f, ax = C.fig(4.6, 2.8)
    ax.bar(fr["year"].astype(str), fr["ratings_added"] / 1000, color=C.GREY, width=0.6)
    for i, r in enumerate(fr.itertuples()):
        ax.text(i, r.ratings_added / 1000 + 0.4, f"+{r.ratings_added / 1000:.1f}k", ha="center", fontsize=8.5, color=C.INK2)
    ax.set_ylabel("ratings added (thousands)")
    ax.grid(axis="x", visible=False)
    ratings_img = C.to_img(f)

    # (c) boost multipliers today
    fo = d["fo"]
    b = fo[fo["is_boosted"] & (fo["rate_before_boost"] > 0)]
    mult = (b["rate_value"] / b["rate_before_boost"]).clip(upper=6)
    f, ax = C.fig(4.6, 2.8)
    ax.hist(mult, bins=np.arange(1, 6.25, 0.25), color=C.GREY, edgecolor=C.CARD)
    ax.axvline(mult.median(), color=C.INK2, ls="--", lw=1)
    ax.text(mult.median(), ax.get_ylim()[1] * 0.9, f"  median x{mult.median():.2f}", fontsize=8.5, color=C.INK2)
    ax.set_xlabel("boosted rate / usual rate (clipped at 6)")
    ax.set_ylabel("offers")
    boost_img = C.to_img(f)

    claims = d["claims"]
    claims_html = "<div class='text muted'>No archived homepage available.</div>"
    if len(claims):
        rows = []
        for lang, lab in (("fr", "French homepage"), ("en", "English homepage")):
            c = claims[(claims["lang"] == lang) & claims["brands_claimed"].notna()].sort_values("snapshot")
            if len(c):
                rows.append(f"<tr><td>{lab}: brands shown</td><td class='num'><b>{c['brands_claimed'].iloc[-1]:,.0f}</b></td>"
                            f"<td>first seen {c['snapshot'].iloc[0]:%b %Y}</td></tr>")
        juno = claims[claims["mentions_juno"].fillna(False).astype(bool)] if "mentions_juno" in claims else pd.DataFrame()
        if len(juno):
            rows.append(f"<tr><td>Juno / AI assistant on the homepage</td><td class='num'><b>yes</b></td>"
                        f"<td>first seen {juno['snapshot'].min():%b %Y}</td></tr>")
        claims_html = (f"<table><tr><th>Public claim (archived homepage)</th><th class='num'>Value</th><th>When</th></tr>{''.join(rows)}</table>"
                       f"<div class='note'>{len(claims)} archived homepages checked (max 1 per quarter, 2022-2026). Before 2026 the homepage is "
                       f"rendered by JavaScript and its archived copies contain no readable text. The 2026 press release and job posting mention "
                       f"10,000+ merchants: definitions differ (brands shown vs all partners).</div>")
    last_year = fr.iloc[-1] if len(fr) else None
    title = (f"Joko ships an iOS update every {gaps.median():.0f} days and keeps adding ~{last_year['ratings_added'] / 1000:.0f}k French ratings a year; "
             f"rival offers move through short boosts of x{mult.median():.1f}")
    sub = (f"{len(v)} iOS versions released between {v['release_date'].min():%b %Y} and {v['release_date'].max():%b %Y} (App Store version history, "
           f"incl. archived copies). Ratings growth from archived App Store pages. Boosts from today's Widilo and iGraal snapshot "
           f"({len(b)} boosted offers with a published usual rate). A planned history of competitor rates was stopped when archive.org rate-limited the collection.")
    body = (card("Joko iOS releases per quarter", cadence_img,
                 f"Median gap between two releases: {gaps.median():.0f} days. The current quarter is not complete.") +
            card("French App Store ratings added per year", ratings_img,
                 "Difference between the last archived counts of two years (snapshots are irregular). The 2023-2024 jump is the largest.") +
            card("How big are boosts? (France, today)", boost_img,
                 "A boost usually doubles the rate for a few days: a strong lever for a cashback app's acquisition calendar.") +
            card("What Joko's homepage said, over time", claims_html) +
            card("What a data team would monitor", """<div class="text"><ul>
                <li><b>Release impact</b>: with a weekly release, tie every release to rating, crash and conversion changes (before/after with a control period).</li>
                <li><b>Boost calendar</b>: competitors' boosts on the same merchants (sales, Black Friday) vs Joko's clicks and conversions.</li>
                <li><b>Catalogue coverage</b>: share of users' spend that lands on merchants with an active offer.</li></ul></div>""",
                 style="grid-column: 2 / 4;"))
    return page(title, sub, "PUBLIC DATA", body,
                "Sources: App Store version history (apps.apple.com, incl. Wayback Machine copies), Widilo and iGraal pages, Joko homepages (Wayback); collected 2026-11-11",
                "grid-template-columns: 1fr 1fr 1fr; grid-template-rows: 1fr 0.8fr;")


def p7_metrics(d):
    k = d["kpis"]
    fr = k[k["country"] == "FR"].sort_values("month")
    nb, uo = d["nb"], d["users_overall"]
    # dashboard mock-up: 4 tiles + 2 small charts
    last = fr.iloc[-1]
    f, ax = C.fig(3.4, 1.7)
    ax.plot(fr["month"], fr["mau"] / 1000, color=C.BLUE, lw=2)
    ax.set_title("MAU, France (k)", fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.tick_params(labelsize=7)
    mau_img = C.to_img(f)
    f, ax = C.fig(3.4, 1.7)
    ax.plot(fr["month"], fr["median_validation_days"], color=C.GREY, lw=2)
    ax.axhline(45, color=C.RED, ls="--", lw=1)
    ax.text(fr["month"].iloc[0], 46, "alert > 45 days", fontsize=7, color=C.RED)
    ax.set_title("Median time-to-validation (days)", fontsize=9)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %y"))
    ax.tick_params(labelsize=7)
    val_img = C.to_img(f)
    tiles = "".join(f"<div style='flex:1;border:1px solid #E1E0D9;border-radius:6px;padding:6px 8px'><div class='lab' style='font-size:10px;color:#52514E;font-weight:700'>{a}</div><div style='font-size:21px;font-weight:700'>{b}</div></div>"
                    for a, b in [("MAU (Oct)", f"{last['mau']:,.0f}"), ("Activation", f"{uo['act']:.0f}%"),
                                 ("D90 retention", f"{uo['ret']:.0f}%"), ("Cashback / MAU", f"€{last['cashback_cost_per_mau_eur']:.2f}")])
    dash = (f"<div style='display:flex;gap:6px;margin-bottom:6px'>{tiles}</div>"
            f"<div style='display:flex;gap:6px;flex:1;min-height:0'><div style='flex:1;display:flex'>{mau_img}</div><div style='flex:1;display:flex'>{val_img}</div></div>"
            "<div class='note'>Filters in one row: country · channel · platform · signup month. Built on the semantic views (sql/00_semantic_layer.sql) so every team reads the same definitions.</div>")
    defs = """<table>
      <tr><th>Metric</th><th>Definition (METRICS.md)</th></tr>
      <tr><td><b>Activated user</b></td><td>≥ 1 non-cancelled tracked purchase within 30 days of signup</td></tr>
      <tr><td><b>Validated cashback</b></td><td>cashback of purchases confirmed by the merchant (excludes pending, cancelled)</td></tr>
      <tr><td><b>Time-to-validation</b></td><td>days from purchase to merchant confirmation; median per month</td></tr>
      <tr><td><b>D90 retention</b></td><td>≥ 1 session between day 61 and day 90 after signup</td></tr>
      <tr><td><b>Cashback cost / active user</b></td><td>validated cashback of the month / MAU</td></tr></table>"""
    cal = d["calib"]
    f, ax = C.fig(3.3, 2.6)
    ax.plot([0, 1], [0, 1], color=C.INK2, ls="--", lw=1)
    ax.plot(cal["predicted"], cal["observed"], color=C.BLUE, marker="o", ms=5, lw=1.8)
    ax.set_xlabel("predicted D90 retention")
    ax.set_ylabel("observed")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    cal_img = C.to_img(f)
    cf = d["coef"].copy()
    cf = cf.reindex(cf["coef_std"].abs().sort_values(ascending=False).index).head(6)
    f, ax = C.fig(3.3, 2.6)
    labs = [x.replace("_14d", " (14d)").replace("_", " ").replace("acquisition channel ", "channel: ") for x in cf["feature"]]
    ax.barh(range(len(cf)), cf["odds_ratio_per_sd"], color=[C.BLUE if v > 1 else C.GREY for v in cf["odds_ratio_per_sd"]], height=0.6)
    ax.axvline(1, color=C.INK2, ls="--", lw=1)
    ax.set_yticks(range(len(cf)), labs)
    ax.invert_yaxis()
    ax.grid(axis="y", visible=False)
    ax.set_xlabel("odds ratio (per 1 SD)")
    coef_img = C.to_img(f)
    rb = nb.get("retention_by_first_purchase_14d", {})
    title = (f"Activation is the lever: activated users retain {uo['ret_act']:.0f}% at day 90 vs {uo['ret_not']:.0f}%, "
             f"and 14 days of behaviour predict who stays (AUC {nb.get('auc', 0):.2f})")
    sub = (f"SIMULATED data (30,000 users, 18 months, seed 42) built on the real merchants and public rates. A 14-day logistic model predicts "
           f"D90 retention on later sign-ups with AUC {nb.get('auc', 0):.2f} (time hold-out, {nb.get('test_users', 0):,} users) and is well calibrated.")
    body = (card("Proposed metric definitions", defs, "One definition per metric, written once in SQL and reused everywhere.") +
            card("Self-service dashboard (mock-up on simulated data)", dash, style="grid-column: 2 / 4;") +
            kpi("SIMULATED · HOLD-OUT", f"AUC {nb.get('auc', 0):.2f}",
                f"14-day behaviour → D90 retention. Base rate {nb.get('base_rate', 0) * 100:.0f}%. Users with a purchase in 14 days: "
                f"{rb.get('1', 0) * 100:.0f}% retained vs {rb.get('0', 0) * 100:.0f}%.", color=C.BLUE) +
            card("Calibration on the hold-out (10 groups)", cal_img, "On the dashed line = predicted probabilities can be read as rates.") +
            card("Strongest signals (odds ratio per SD)", coef_img, "Associations, not causes: use the score to target onboarding, then A/B test the action."))
    return page(title, sub, "SIMULATED", body,
                "SIMULATED data: src/simulate.py (assumptions in data/ASSUMPTIONS.md). Model: notebooks/analysis.ipynb. Not Joko data",
                "grid-template-columns: 1.1fr 1fr 1fr; grid-template-rows: 1.05fr 1fr;")


def p8_ai(d):
    ev, rows, a = d["eval"], d["eval_rows"], d["assist"]
    arch = """
    <div style="display:grid;grid-template-columns:1fr 26px 1fr 26px 1fr;align-items:center;gap:4px">
      <div class="box grey">Business question<br><span class="muted">EN or FR</span></div><div class="arrow">→</div>
      <div class="box">LLM writes SQL<br><span class="muted">on documented views only</span></div><div class="arrow">→</div>
      <div class="box grey">Guardrails<br><span class="muted">allow-list · read-only · 200 rows</span></div>
      <div></div><div></div><div></div><div></div><div class="arrow">↓</div>
      <div class="box grey">Answer + SQL shown<br><span class="muted">or raw table</span></div><div class="arrow">←</div>
      <div class="box">Number check<br><span class="muted">every figure must be in the result</span></div><div class="arrow">←</div>
      <div class="box grey">DuckDB<br><span class="muted">semantic layer</span></div>
    </div>"""
    guards = """<ul class="text" style="font-size:12.5px">
      <li><b>Scope</b>: refuses questions the views cannot answer (real Joko users, competitors, personal data, writes).</li>
      <li><b>Allow-list</b>: only the 3 semantic views; file functions, writes, multiple statements are blocked.</li>
      <li><b>Read-only</b> DuckDB connection, external access disabled; outer LIMIT 200.</li>
      <li><b>Transparency</b>: the SQL is always displayed next to the answer.</li>
      <li><b>No invented numbers</b>: a figure absent from the SQL result rejects the answer.</li>
      <li><b>Structured outputs</b>: JSON schema; calls logged (tokens, cost, latency), no personal data.</li></ul>"""
    ex = rows[rows["id"].isin(["q05", "q14", "q26"])] if len(rows) else pd.DataFrame()
    ex_html = ""
    for r in ex.itertuples():
        sql = esc(r.generated_sql) if isinstance(r.generated_sql, str) and r.generated_sql else "— (refused, no SQL run)"
        ex_html += f"<p style='margin:4px 0 2px 0;font-size:12.5px'><b>Q:</b> {esc(r.question)}</p><pre>{sql}</pre><p style='margin:0 0 6px 0;font-size:12px' class='muted'>A: {esc(str(r.answer)[:170])}</p>"
    if ev:
        table = f"""<table>
          <tr><th>Evaluation (fixed set, known answers)</th><th class="num">Result</th></tr>
          <tr><td>Correct answers, in scope</td><td class="num"><b>{ev['in_scope_correct']}/{ev['in_scope_questions']}</b></td></tr>
          <tr><td>Out-of-scope questions refused</td><td class="num"><b>{ev['out_of_scope_refused']}/{ev['questions'] - ev['in_scope_questions']}</b></td></tr>
          <tr><td>Invented numbers in answers</td><td class="num"><b>{ev['invented_numbers_total']}</b></td></tr>
          <tr><td>Guardrail unit tests (SQL that must be blocked)</td><td class="num">{ev.get('guardrail_tests_passed', '-')}</td></tr>
          <tr><td>Average cost per question</td><td class="num">${ev['avg_cost_usd']:.5f}</td></tr>
          <tr><td>Median latency</td><td class="num">{ev['median_latency_s']:.1f} s</td></tr>
          </table>"""
        headline = f"{ev['correct']}/{ev['questions']}"
    else:
        table, headline = "<div class='text'>evaluation pending</div>", "pending"
    title = (f"\"Ask the data\": {headline} questions answered or refused correctly, 0 invented numbers, for "
             f"${ev.get('avg_cost_usd', 0):.4f} per question")
    sub = ("A read-only assistant that lets non-technical teams query the metrics of page 7 in plain English or French. The model only sees "
           "a documented semantic layer; every number it writes is checked against the SQL result. SIMULATED data, so the evaluation measures the method.")
    body = (card("How it works", arch, style="grid-column: 1 / 3;") +
            card("Results", table, "Questions written with their SQL answer before running the model (eval/questions.yaml); one run; easy-to-medium questions.",
                 style="grid-row: 1 / 3; grid-column: 3;") +
            card("Guardrails", guards) +
            card("Examples (generated SQL shown to the user)", ex_html))
    return page(title, sub, "SIMULATED + AI", body,
                "Code: src/ai_ask_data.py, src/ai_eval.py; results: eval/results.csv. Model: low-cost LLM via API (id in src/ai_common.py). SIMULATED data, not Joko data",
                "grid-template-columns: 1fr 1.15fr 0.85fr; grid-template-rows: 0.55fr 1.3fr;")


def p9_methods(d):
    a = d["assist"]
    body = (card("Data & sources", """<div class="text"><p><b>PUBLIC DATA</b> (dated snapshots, 11 Nov 2026): Widilo and iGraal merchant pages
        (rates, boosts, announced validation delays); Apple iTunes Search API and public App Store pages (ratings, reviews);
        addons.mozilla.org API (extension reviews); Wayback Machine (archived pages, max one per month/quarter); Google Trends;
        press releases and Joko's job posting. Every figure is listed with its URL and date in <code>data/SOURCES.md</code>.</p>
        <p><b>Not used</b>: Joko's in-app catalogue (login required; automated extraction excluded by its terms), Poulpeo,
        TopCashback, Capital One Shopping and Rakuten rates (terms or robots.txt), Chrome Web Store reviews (robots.txt).</p>
        <p><b>SIMULATED</b>: users, events, purchases, payouts (<code>src/simulate.py</code>, seed 42, assumptions in
        <code>data/ASSUMPTIONS.md</code>). Used only on pages 7-8. Never presented as Joko data.</p></div>""") +
            card("Methods", f"""<div class="text"><ul>
        <li><b>Merchant matching</b>: normalised names, then fuzzy matching (score ≥ 88) with a manual decision for each doubtful pair (7 reviewed, 4 accepted).</li>
        <li><b>Rate comparison</b>: paired gaps, 10,000-resample bootstrap CI for the median, Wilcoxon signed-rank test.</li>
        <li><b>Retention model</b>: logistic regression on 14-day behaviour, time hold-out, AUC and calibration.</li>
        <li><b>Selection bias</b>: assistant users buy {a.get('naive_uplift_pct', 0):.0f}% more (naive); adjusting for prior engagement gives +{a.get('adjusted_uplift_pct', 0):.0f}%;
            the true simulated effect is +10%. Only an A/B test answers this on real data.</li>
        <li><b>AI</b>: closed-list classification with JSON schema + human check; text-to-SQL with guardrails and a fixed evaluation set.</li></ul></div>""") +
            card("Limits", """<div class="text"><ul>
        <li>Joko's own rates are not public: the rate analysis describes the market, not Joko's position.</li>
        <li>One-day snapshot; Widilo category pages show its most visible (often boosted) merchants.</li>
        <li>Reviews are a small, non-random sample (pages show a few reviews; archives are sparse).</li>
        <li>Ratings counts are footprint proxies, not active users or market share.</li>
        <li>archive.org rate-limited the collection after ~100 archived pages: no history of competitor rates.</li>
        <li>Simulated data demonstrates methods; the numbers on pages 7-8 say nothing about Joko.</li></ul></div>""") +
            card("Reproduce & AI note", f"""<div class="text"><pre>python -m venv .venv &amp;&amp; .venv\\Scripts\\pip install -r requirements.txt
python src/collect_*.py            # public data (polite, dated snapshots)
python src/build_public_tables.py  # clean tables
python src/simulate.py ; python src/run_sql.py
jupyter nbconvert --execute --inplace notebooks/analysis.ipynb
python src/ai_review_themes.py ; python src/ai_eval.py   # needs an API key in .env
python src/build_report.py</pre>
        <p style="margin-top:8px"><i>{AI_NOTE}</i></p></div>"""))
    return page("Methods, limits and how to reproduce", "Everything on the previous pages can be rebuilt from the repository; collection scripts respect robots.txt and terms of use, with ≥ 2 s between requests.",
                "METHODS", body, "Repository: README.md, data/SOURCES.md, data/ASSUMPTIONS.md, METRICS.md",
                "grid-template-columns: 1fr 1fr; grid-template-rows: 1fr 1fr;")


def p0_overview(d, pages_titles):
    nb, ev, uo, apps = d["nb"], d["eval"], d["users_overall"], d["apps"]
    joko_fr = apps[(apps["country"] == "fr") & apps["app_name"].str.contains("Joko")].iloc[0]
    rivals = apps[(apps["country"] == "fr") & ~apps["app_name"].str.contains("Joko")]
    us = apps[apps["country"] == "us"]
    rak = us[us["app_name"].str.contains("Rakuten")].iloc[0]["rating_count"]
    joko_us = us[us["app_name"].str.contains("Joko")].iloc[0]["rating_count"]
    rates = nb.get("rates", {})
    kp = (kpi("PUBLIC · PAGES 1, 3", f"{joko_fr['rating_count'] / rivals['rating_count'].max():.1f}x",
              "more App Store ratings in France than the next cashback app: Joko is the largest public footprint", color=C.BLUE) +
          kpi("PUBLIC · PAGE 3", f"+{rates.get('median_gap_pts', 1):.1f} pt",
              f"median rate gap for the same merchant between two French platforms ({rates.get('merchants_compared', 0)} merchants): rates are not a moat") +
          kpi("PUBLIC · PAGE 4", f"{100 * joko_us / rak:.1f}%",
              "Joko's US App Store ratings as a share of Rakuten's: the US push starts from a small, fast-growing base") +
          kpi("SIMULATED + AI · PAGE 8", f"{ev.get('correct', 0)}/{ev.get('questions', 0)}",
              f"questions answered or refused correctly by the read-only data assistant, {ev.get('invented_numbers_total', 0)} invented numbers"))
    qs = """<div class="text" style="font-size:14.5px;line-height:1.75">
      <div><b class="blue">1 · Company</b> &nbsp;Where does Joko stand today, in public data?</div>
      <div><b class="blue">2-3 · Offer</b> &nbsp;What does the French cashback market pay, and how different are platforms?</div>
      <div><b class="blue">4 · US</b> &nbsp;What does the US push start from?</div>
      <div><b class="blue">5-6 · Users & dynamics</b> &nbsp;What do users praise and complain about? How do offers move?</div>
      <div><b class="blue">7-8 · The job</b> &nbsp;Which metrics, which model, and how can teams ask the data safely with AI?</div>
      <p style="margin-top:8px"><b>Recommendations:</b> make <i>time-to-first-validated-cashback</i> a top-level metric next to activation;
      protect the moments users complain about (connecting a bank or the extension, first withdrawal);
      compete on automation and the assistant rather than on rates; measure Juno with a randomised rollout, not with adopter vs non-adopter comparisons;
      give teams one semantic layer and an AI assistant that shows its SQL and cannot invent numbers.</p></div>"""
    dm = """<div class="text" style="font-size:13.5px;line-height:1.6">
      <p><b>PUBLIC DATA</b> &nbsp;Widilo & iGraal rates (674 merchants, 316 compared), App Store & Firefox reviews and ratings, Wayback archives, Google Trends, press releases. Joko's in-app rates are not public and were not collected.</p>
      <p><b>SIMULATED</b> &nbsp;30,000 users on real merchants and public rates (seed 42), for metrics, model and AI demo only.</p>
      <p><b>SQL</b> DuckDB, semantic layer + 7 queries · <b>Python</b> bootstrap, Wilcoxon, logistic regression with time hold-out ·
      <b>AI</b> low-cost LLM via API: review themes (human-checked) and guarded text-to-SQL with an evaluation set.</p></div>"""
    howto = """<div class="text" style="font-size:13px"><b>Titles</b> state the conclusion &nbsp;·&nbsp; <b>Tags</b> PUBLIC DATA / SIMULATED / + AI say where the data comes from
      &nbsp;·&nbsp; <b>Blue</b> = Joko or the focus, <b>grey</b> = comparison, <b>red</b> = alert, <b>dashed</b> = threshold or reference
      &nbsp;·&nbsp; <b>Code</b>: SQL, notebook and AI scripts in the repository.</div>"""
    body = (kp + card("Business questions", qs, style="grid-column: 1 / 3;") + card("Data & methods", dm, style="grid-column: 3 / 5;") +
            card("How to read this report", howto, style="grid-column: 1 / 5;"))
    return page("Joko: where the cashback offer wins, and what it means for the US push",
                "Public-data analysis of Joko's merchant offer, competitive position and user feedback, with an AI layer that lets non-technical teams ask the data directly.",
                "OVERVIEW", body, "Data sources listed in data/SOURCES.md",
                "grid-template-columns: repeat(4, 1fr); grid-template-rows: 0.5fr 1.25fr 0.27fr;")


# =============================================================================================
def find_browser():
    for p in [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"]:
        if Path(p).exists():
            return p
    return shutil.which("msedge") or shutil.which("chrome")


def main():
    d = load()
    pages = [p1_public(d), p2_offer(d), p3_competition(d), p4_us(d), p5_reviews(d), p6_dynamics(d),
             p7_metrics(d), p8_ai(d), p9_methods(d)]
    pages = [p0_overview(d, None)] + pages
    head = f"<!doctype html><html><head><meta charset='utf-8'><title>Joko data case study</title><style>{CSS}</style></head><body>"
    tmp = ROOT / "docs" / "_build"
    tmp.mkdir(parents=True, exist_ok=True)
    (tmp / "report.html").write_text(head + "".join(pages) + "</body></html>", encoding="utf-8")
    browser = find_browser()
    pdf = DOCS / "Joko_DataCaseStudy.pdf"
    subprocess.run([browser, "--headless=new", "--disable-gpu", "--no-pdf-header-footer",
                    f"--print-to-pdf={pdf}", (tmp / "report.html").as_uri()], check=True, capture_output=True, timeout=180)
    # one PNG per page for the README
    img = DOCS / "img"
    img.mkdir(exist_ok=True)
    for i, p in enumerate(pages):
        f = tmp / f"page_{i:02d}.html"
        f.write_text(head.replace("@page", "@page_unused") + p + "</body></html>", encoding="utf-8")
        subprocess.run([browser, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--window-size=1600,900", f"--screenshot={img / f'page_{i:02d}.png'}", f.as_uri()],
                       check=True, capture_output=True, timeout=120)
    shutil.rmtree(tmp)
    # empty PDF metadata (no author)
    try:
        from pypdf import PdfReader, PdfWriter
        r = PdfReader(str(pdf))
        w = PdfWriter()
        for pg in r.pages:
            w.add_page(pg)
        w.add_metadata({"/Title": "Joko data case study", "/Author": "", "/Creator": "", "/Producer": ""})
        with open(pdf, "wb") as fh:
            w.write(fh)
    except ImportError:
        pass
    print(f"wrote {pdf} and {len(pages)} page images")


if __name__ == "__main__":
    main()
