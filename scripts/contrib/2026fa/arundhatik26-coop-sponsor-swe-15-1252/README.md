# arundhatik26 — co-op sponsor check for software roles

## Executive summary

This is a small working prototype. For each co-op role a student is considering, it checks whether the employer has a recorded history of sponsoring software jobs. It also checks whether the posting is live and whether the co-op fits before graduation, then hands the result to the existing role scorer. It runs on a fictional persona and on the data that ships with the repository. Where there is no record, it says "unknown" instead of guessing. When a typed brand name ("Robinhood", "Chime", "SoFi") is not the legal name the data uses, it lists the likely legal names for a person to choose; it never picks one itself.

## Run it (from the repo root)

```bash
python3 scripts/contrib/2026fa/arundhatik26-coop-sponsor-swe-15-1252/coop_sponsor_check.py
```

It needs Python 3 (standard library only) and Node 20+ for the scorer. It makes no network calls. Output goes to `course/2026fa/submissions/arundhatik26/runs/sample/`:

| File | Reader |
|---|---|
| `report.md` | the person |
| `run-log.json` | the agent; every value labeled `record` / `your-input`, with its CSV line |
| `grad-dec-2027/`, `grad-apr-2028/` → `roles.json`, `role-scores.json`, `role-scores.md` | the scorer's input and its audit, one per graduation scenario |

Options: `--input <persona.json>` and `--out-dir <dir>`.

## Test (offline, from fixtures)

```bash
python3 -m unittest discover -s scripts/contrib/2026fa/arundhatik26-coop-sponsor-swe-15-1252/tests -v
```

26 tests. They cover the six named failure cases (F1–F6 in the change brief), the "MELLON"-style substring trap, the Goldman "AND CO" legal form, brand names (Robinhood, Chime, SoFi — exact dataset rows in `tests/fixtures/brands-fixture.csv`), unknown SOC, bad input, and a full pipeline run through the **real** `scripts/score/role-scorer.mjs`. Python socket connects are blocked during the run.

## Files

| Path | What |
|---|---|
| `coop_sponsor_check.py` | the prototype |
| `inputs/sample-persona.json` | fictional persona (Ananya Rao, `@example.com`); every value is `your-input` |
| `inputs/brand-aliases.json` | your-input: brand → legal name, only where no word of the brand is in the legal name (SoFi → Social Finance). Every alias hit goes to a human. |
| `inputs/liveness-2026-10-02.txt` | real `npm run ats:liveness` output for the two URLs in the sample, captured 2026-10-02 |
| `tests/test_coop_sponsor_check.py` | offline tests |
| `tests/fixtures/` | made-up CSV / BLS / liveness / persona fixtures, one row per failure case; `brands-fixture.csv` = seven real dataset rows (tool columns only) plus one invented decoy |

## Data it reads

- `data/80-days-to-stay/80-days-csv/mapped_student_employment_targets_v3.csv`
- `data/bls/compact/soc_occupation_compact.csv`
- the liveness record named in the input file

Recipe: `recipes/cases/2026fa/arundhatik26-coop-sponsor-swe-15-1252.md` (agent) and `.card.md` (human).

## Name matching (changed 2026-11-23)

- **Exact name** (legal-form words such as INC, LLC, CO removed) → matched, as before.
- **First whole word(s)**: "Chime" also lists CHIME FINANCIAL INC; "Chime" never lists ARCHIMEDES. These are candidates.
- **Alias list** (`inputs/brand-aliases.json`, your input): "SoFi" lists SOCIAL FINANCE INC.
- Any candidate that is not an exact name makes the result `ambiguous`: **HUMAN CHECK (G2)**. Each candidate row says how it was found (`found_by`).

On the 25-company evaluation this removed all three brand-name misses and the wrong automatic Chime answer; 6 of 25 now go to a human check. Behaviour change: typing only a first word (e.g. "ACME") now lists candidates instead of returning `not-in-dataset`.
