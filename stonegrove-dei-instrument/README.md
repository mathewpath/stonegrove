# Stonegrove DEI Research Instrument

An interactive analytical instrument for exploring equality-of-outcome gaps across
the student lifecycle, built for the **Stonegrove Edge Project**. It reads a
synthetic institutional dataset of **35,001 students across seven academic years**
(55 programmes, 5 faculties, ~2.2m weekly engagement records) through five
demographic lenses — ancestry, gender, disability disclosure, first-in-family
status and socio-economic band — from first login to first salary.

**Live demo:** deploy `index.html` to any static host (Vercel, GitHub Pages, Netlify).

## What it shows

| View | Question it answers |
|---|---|
| **Overview** | Where are the biggest gaps? A 21-metric × 5-lens gap matrix, colour-scaled. |
| **Gap Explorer** | How does each group compare on every lifecycle metric? |
| **Trends** | Are the gaps stable, widening, or closing across seven academic years? |
| **Weekly Rhythm** | When does disengagement start? Attendance & VLE curves by teaching week. |
| **Faculty & Programmes** | Where is the gap concentrated? Faculty breakdowns + a sortable 55-programme league table with within-programme SEC gaps. |
| **Intersections** | How does disadvantage compound? Cross any two lenses on any of six metrics. |
| **Distributions** | Where in the mark distribution does the gap live? |

Three headline readings the instrument surfaces:

1. **Equal access, unequal quality.** Employment within 15 months barely moves
   across any group (≈2 pts), but professional-level employment spreads by up to
   12.7 pts and average salary band by nearly 2 full bands.
2. **Socio-economic band is the master lens.** Low-SEC students fail years at 6×
   the rate of high-SEC students (25.0% vs 4.2%) and reach good honours at a
   third of the rate (21.9% vs 68.0%).
3. **Belonging is not the problem.** The worst-served groups report peer
   belonging as high as — sometimes higher than — everyone else; the gaps track
   self-efficacy, attendance and resources instead.

## Repository structure

```
.
├── index.html                 # the entire instrument (data embedded, works offline)
├── data/
│   ├── dei_aggregates.json    # precomputed aggregates the instrument runs on
│   └── raw/                   # put the 18 Stonegrove CSVs here (gitignored)
├── scripts/
│   └── prepare_data.py        # rebuilds aggregates from raw CSVs + injects into index.html
├── .gitignore
└── README.md
```

`index.html` is fully self-contained — the aggregates are embedded inline, so it
works from `file://`, needs no server-side code, and never ships row-level data.

## Rebuilding from raw data

The raw CSVs are **not** committed (row-level student data does not belong in a
public repo, even synthetic). To rebuild:

1. Drop the 18 Stonegrove CSVs into `data/raw/`
   (`dim_*.csv`, `fact_*.csv`, `fact_weekly_engagement_*.csv`).
2. Install dependencies and run the pipeline:

   ```bash
   pip install pandas numpy
   python scripts/prepare_data.py
   ```

   This recomputes `data/dei_aggregates.json` and re-injects it into
   `index.html` between the `/* DATA:BEGIN */ ... /* DATA:END */` markers.

## Deploying

- **Vercel:** import the repo → framework preset "Other" → no build command →
  output directory `.` — done.
- **GitHub Pages:** Settings → Pages → deploy from branch → root.

## Method notes / disclosure control

- All figures are cohort averages joined on student ID across the enrolment
  survey, NSS responses, weekly VLE/attendance logs, progression outcomes,
  good-honours classifications and graduate outcomes.
- Subgroup cells with **n < 30** are suppressed throughout (n ≥ 20 per band for
  the within-programme SEC gap), mirroring standard institutional-research
  disclosure-control practice.
- Stonegrove is a synthetic dataset; ancestry (Dwarf/Elf) and clan act as
  anonymised demographic proxies. No real students are represented.

## Stack

Single-file HTML + [Chart.js 4](https://www.chartjs.org/) (CDN). Python
(pandas/numpy) for the offline aggregation pipeline. No framework, no build
step, no backend.
