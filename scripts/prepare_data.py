#!/usr/bin/env python3
"""
Stonegrove DEI Research Instrument — data pipeline.

Reads the 18 raw Stonegrove CSVs from data/raw/, computes every aggregate
the instrument needs, writes data/dei_aggregates.json, and re-injects the
JSON into index.html between the /* DATA:BEGIN */ ... /* DATA:END */ markers.

Usage:
    pip install pandas numpy
    python scripts/prepare_data.py

Expected files in data/raw/:
    dim_students.csv, dim_programmes.csv, dim_modules.csv, dim_academic_years.csv,
    fact_assessment.csv, fact_enrollment.csv, fact_enrolment_survey.csv,
    fact_good_honours.csv, fact_graduate_outcomes.csv, fact_nss_responses.csv,
    fact_progression.csv, fact_weekly_engagement_*.csv
"""
import glob
import json
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "data", "raw")
OUT_JSON = os.path.join(ROOT, "data", "dei_aggregates.json")
INDEX_HTML = os.path.join(ROOT, "index.html")

MIN_N = 30          # disclosure control: suppress subgroup cells under this n
MIN_N_SEC_GAP = 20  # per-band minimum for the within-programme SEC gap

NSS_DIMS = [
    "teaching_quality", "learning_opportunities", "assessment_feedback",
    "academic_support", "organisation_management", "learning_resources",
    "student_voice", "overall_satisfaction",
]
SURVEY_DIMS = [
    "career_clarity", "career_confidence", "belonging_peers",
    "belonging_programme", "academic_self_efficacy", "support_satisfaction",
]


def rd(name: str) -> pd.DataFrame:
    return pd.read_csv(os.path.join(RAW, name))


def sec_band(rank: int) -> str:
    if rank <= 3:
        return "Low (SEC 1-3)"
    if rank <= 6:
        return "Mid (SEC 4-6)"
    return "High (SEC 7-8)"


def main() -> None:
    # ---------- shared setup ----------
    students = rd("dim_students.csv")
    students["has_disability"] = students["disabilities"].apply(
        lambda x: "Disability disclosed" if x != "no_known_disabilities" else "No known disability"
    )
    students["first_gen_label"] = students["first_gen"].apply(
        lambda x: "First-in-family" if x else "Continuing-ed family"
    )
    students["sec_band"] = students["socio_economic_rank"].apply(sec_band)
    students["gender_label"] = students["gender"].str.capitalize()

    lenses = {
        "species": ("Ancestry", ["Dwarf", "Elf"]),
        "gender_label": ("Gender", ["Male", "Female", "Neuter"]),
        "has_disability": ("Disability", ["No known disability", "Disability disclosed"]),
        "first_gen_label": ("First-in-family", ["Continuing-ed family", "First-in-family"]),
        "sec_band": ("Socio-economic band", ["Low (SEC 1-3)", "Mid (SEC 4-6)", "High (SEC 7-8)"]),
    }
    lens_keys = list(lenses.keys())

    honours = rd("fact_good_honours.csv").merge(students, on="student_id")
    honours["good_honours"] = honours["degree_classification"].isin(["First", "2:1"])
    honours["first"] = honours["degree_classification"] == "First"

    prog = rd("fact_progression.csv").merge(students, on="student_id")
    prog["withdrawn"] = prog["status"] == "withdrawn"
    prog["failed_year"] = prog["year_outcome"] == "fail"
    prog["repeating"] = prog["status"] == "repeating"

    nss = rd("fact_nss_responses.csv").merge(students, on="student_id")
    survey = rd("fact_enrolment_survey.csv").merge(students, on="student_id")

    eng_files = sorted(glob.glob(os.path.join(RAW, "fact_weekly_engagement_*.csv")))
    if not eng_files:
        sys.exit("No fact_weekly_engagement_*.csv files found in data/raw/")
    eng = pd.concat([pd.read_csv(f) for f in eng_files], ignore_index=True)
    eng["attendance_rate"] = eng["attended_sessions"] / eng["total_sessions"]

    go = rd("fact_graduate_outcomes.csv").merge(students, on="student_id")
    go["employed_any"] = go["outcome_type"] == "employed"
    go["employed_prof"] = (go["outcome_type"] == "employed") & (go["professional_level"] == "professional")
    go["further_study"] = go["outcome_type"] == "further_study"

    enrol = rd("fact_enrollment.csv")
    programmes = rd("dim_programmes.csv")

    # each student's latest programme & faculty
    stu_prog = enrol.sort_values("academic_year").groupby("student_id")["programme_code"].last().reset_index()
    stu_prog = stu_prog.merge(programmes, on="programme_code")

    out = {}

    # ---------- 1. lens metrics (Overview / Gap Explorer) ----------
    eng_l = eng.merge(students[["student_id"] + lens_keys], on="student_id")
    lens_metrics = {}
    for lk, (label, order) in lenses.items():
        groups = []
        for grp in order:
            h = honours[honours[lk] == grp]
            p = prog[prog[lk] == grp]
            n = nss[nss[lk] == grp]
            s = survey[survey[lk] == grp]
            g = go[go[lk] == grp]
            e = eng_l[eng_l[lk] == grp]
            row = {
                "name": grp,
                "n_students": int((students[lk] == grp).sum()),
                "good_honours": round(h["good_honours"].mean() * 100, 1),
                "first_class": round(h["first"].mean() * 100, 1),
                "avg_degree_mark": round(h["degree_weighted_avg"].mean(), 1),
                "failed_year": round(p["failed_year"].mean() * 100, 1),
                "withdrawn": round(p["withdrawn"].mean() * 100, 1),
                "repeating": round(p["repeating"].mean() * 100, 1),
                "avg_mark": round(p["avg_mark"].mean(), 1),
                "attendance_rate": round(e["attendance_rate"].mean() * 100, 1),
                "vle_logins": round(e["vle_logins"].mean(), 2),
                "vle_resource_views": round(e["vle_resource_views"].mean(), 2),
                "vle_forum_posts": round(e["vle_forum_posts"].mean(), 2),
                "employed_any": round(g["employed_any"].mean() * 100, 1),
                "employed_prof": round(g["employed_prof"].mean() * 100, 1),
                "further_study": round(g["further_study"].mean() * 100, 1),
                "salary_band": round(g["salary_band"].mean(), 2),
                "time_to_outcome": round(g["time_to_outcome_months"].mean(), 1),
            }
            for d in NSS_DIMS:
                row[d] = round(n[d].mean(), 2)
            for d in SURVEY_DIMS:
                row[d] = round(s[d].mean(), 2)
            groups.append(row)
        lens_metrics[lk] = {"label": label, "groups": groups}
    out["lens_metrics"] = lens_metrics

    # ---------- 2. trends over academic years ----------
    years = sorted(prog["academic_year"].unique())
    grad_years = sorted(honours["academic_year_graduated"].unique())
    trends = {}
    for lk, (label, order) in lenses.items():
        tl = {"label": label, "years": years, "grad_years": grad_years, "groups": {}}
        for grp in order:
            p = prog[prog[lk] == grp]
            h = honours[honours[lk] == grp]
            n = nss[nss[lk] == grp]
            series = {
                "failed_year": p.groupby("academic_year")["failed_year"].mean().reindex(years) * 100,
                "withdrawn": p.groupby("academic_year")["withdrawn"].mean().reindex(years) * 100,
                "avg_mark": p.groupby("academic_year")["avg_mark"].mean().reindex(years),
                "good_honours": h.groupby("academic_year_graduated")["good_honours"].mean().reindex(grad_years) * 100,
                "overall_satisfaction": n.groupby("academic_year")["overall_satisfaction"].mean().reindex(years),
            }
            tl["groups"][grp] = {
                k: [round(x, 2 if k == "overall_satisfaction" else 1) if pd.notna(x) else None for x in v]
                for k, v in series.items()
            }
        trends[lk] = tl
    out["trends"] = trends

    # ---------- 3. weekly engagement curves ----------
    weekly = {}
    weeks = list(range(1, 13))
    for lk, (label, order) in lenses.items():
        wl = {"label": label, "weeks": weeks, "groups": {}}
        for grp in order:
            e = eng_l[eng_l[lk] == grp]
            att = e.groupby("week_number")["attendance_rate"].mean().reindex(weeks) * 100
            vle = e.groupby("week_number")["vle_logins"].mean().reindex(weeks)
            wl["groups"][grp] = {
                "attendance": [round(x, 1) for x in att],
                "vle_logins": [round(x, 2) for x in vle],
            }
        weekly[lk] = wl
    out["weekly"] = weekly

    # ---------- 4. faculty drill-down ----------
    hon_f = honours.merge(stu_prog[["student_id", "faculty"]], on="student_id", how="left")
    prog_f = prog.merge(stu_prog[["student_id", "faculty"]], on="student_id", how="left")
    faculties = sorted(programmes["faculty"].unique())
    faculty_data = {}
    for lk, (label, order) in lenses.items():
        fd = {"label": label, "faculties": faculties, "groups": {}}
        for grp in order:
            gh_vals, fy_vals = [], []
            for fac in faculties:
                h = hon_f[(hon_f[lk] == grp) & (hon_f["faculty"] == fac)]
                p = prog_f[(prog_f[lk] == grp) & (prog_f["faculty"] == fac)]
                gh_vals.append(round(h["good_honours"].mean() * 100, 1) if len(h) >= MIN_N else None)
                fy_vals.append(round(p["failed_year"].mean() * 100, 1) if len(p) >= MIN_N else None)
            fd["groups"][grp] = {"good_honours": gh_vals, "failed_year": fy_vals}
        faculty_data[lk] = fd
    out["faculty"] = faculty_data

    # ---------- 5. programme league table ----------
    pc_map = stu_prog[["student_id", "programme_code"]].rename(columns={"programme_code": "pc"})
    hon_p = honours.merge(pc_map, on="student_id", how="left")
    nss_p = nss.merge(pc_map, on="student_id", how="left")
    prog_p = prog.merge(pc_map, on="student_id", how="left")
    prog_table = []
    for _, r in programmes.iterrows():
        pc = r["programme_code"]
        h = hon_p[hon_p["pc"] == pc]
        n = nss_p[nss_p["pc"] == pc]
        p = prog_p[prog_p["pc"] == pc]
        h_low = h[h["sec_band"] == "Low (SEC 1-3)"]
        h_high = h[h["sec_band"] == "High (SEC 7-8)"]
        sec_gap = None
        if len(h_low) >= MIN_N_SEC_GAP and len(h_high) >= MIN_N_SEC_GAP:
            sec_gap = round((h_high["good_honours"].mean() - h_low["good_honours"].mean()) * 100, 1)
        prog_table.append({
            "code": pc,
            "name": r["programme_name"],
            "faculty": r["faculty"],
            "n": int((stu_prog["programme_code"] == pc).sum()),
            "good_honours": round(h["good_honours"].mean() * 100, 1) if len(h) >= MIN_N else None,
            "failed_year": round(p["failed_year"].mean() * 100, 1) if len(p) >= MIN_N else None,
            "withdrawn": round(p["withdrawn"].mean() * 100, 1) if len(p) >= MIN_N else None,
            "satisfaction": round(n["overall_satisfaction"].mean(), 2) if len(n) >= MIN_N else None,
            "sec_gap": sec_gap,
        })
    out["programmes"] = prog_table

    # ---------- 6. intersections ----------
    inter_metrics = {
        "good_honours": ("Achieved First/2:1 (%)", honours, "good_honours", "pct"),
        "failed_year": ("Failed a year (%)", prog, "failed_year", "pct"),
        "withdrawn": ("Withdrew (%)", prog, "withdrawn", "pct"),
        "overall_satisfaction": ("NSS overall satisfaction (/5)", nss, "overall_satisfaction", "mean"),
        "academic_self_efficacy": ("Academic self-efficacy (/5)", survey, "academic_self_efficacy", "mean"),
        "employed_prof": ("Professional employment (%)", go, "employed_prof", "pct"),
    }
    inters = {}
    for i, lk1 in enumerate(lens_keys):
        for lk2 in lens_keys[i + 1:]:
            entry = {
                "rows": lenses[lk1][1], "cols": lenses[lk2][1],
                "row_label": lenses[lk1][0], "col_label": lenses[lk2][0],
                "metrics": {},
            }
            for mk, (mlabel, df, col, kind) in inter_metrics.items():
                mat, nmat = [], []
                for r1 in lenses[lk1][1]:
                    row, nrow = [], []
                    for c2 in lenses[lk2][1]:
                        sub = df[(df[lk1] == r1) & (df[lk2] == c2)]
                        nrow.append(int(len(sub)))
                        if len(sub) < MIN_N:
                            row.append(None)
                        else:
                            v = sub[col].mean()
                            row.append(round(v * 100, 1) if kind == "pct" else round(v, 2))
                    mat.append(row)
                    nmat.append(nrow)
                entry["metrics"][mk] = {"label": mlabel, "values": mat, "n": nmat}
            inters[f"{lk1}|{lk2}"] = entry
    out["intersections"] = inters

    # ---------- 7. mark distributions ----------
    bins = list(range(0, 105, 5))
    dist = {}
    for lk, (label, order) in lenses.items():
        dl = {"label": label, "bins": bins[:-1], "groups": {}}
        for grp in order:
            marks = prog[prog[lk] == grp]["avg_mark"].dropna()
            hist, _ = np.histogram(marks, bins=bins)
            dl["groups"][grp] = list((hist / hist.sum() * 100).round(2))
        dist[lk] = dl
    out["distributions"] = dist

    # ---------- headline stats ----------
    out["headline"] = {
        "n_students": int(len(students)),
        "n_programmes": int(len(programmes)),
        "n_faculties": len(faculties),
        "years_covered": f"{years[0]} \u2013 {years[-1]}",
        "n_grads": int(len(honours)),
        "n_engagement_rows": int(len(eng)),
    }

    # ---------- write JSON ----------
    payload = json.dumps(out, separators=(",", ":"))
    with open(OUT_JSON, "w") as f:
        f.write(payload)
    print(f"wrote {OUT_JSON} ({len(payload)//1024} KB)")

    # ---------- inject into index.html ----------
    html = open(INDEX_HTML).read()
    pattern = re.compile(r"/\* DATA:BEGIN \*/.*?/\* DATA:END \*/", re.S)
    if not pattern.search(html):
        sys.exit("DATA:BEGIN / DATA:END markers not found in index.html")
    replacement = f"/* DATA:BEGIN */\nconst D = {payload};\n/* DATA:END */"
    html = pattern.sub(lambda _: replacement, html)
    open(INDEX_HTML, "w").write(html)
    print(f"injected data into {INDEX_HTML}")


if __name__ == "__main__":
    main()
