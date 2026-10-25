# Personal AI Career Platform — v1.0 (open source, MIT)

**Posture: draft & approve only. This code never submits a job application.**
**Local-first: profiles, jobs, CVs and applications live in local SQLite. Ollama runs on localhost; cloud is opt-in only.**

## v1.0: the whole core loop, from the command line or the local dashboard

```bash
python3 tests.py
python3 app.py demo
python3 app.py serve --port 8000   # http://127.0.0.1:8000/ , local only, read + approve
python3 app.py cv-tailor --profile-id 1 --demo-job 0
python3 app.py cv-rewrite --profile-id 1 --demo-job 0
python3 app.py scholarships-match --profile-id 1 --country Germany --country UK --country Australia
python3 app.py masters-match --field "computer science" --country Germany
python3 app.py project-suggest --profile-id 1 --target-skills "Kubernetes, LLM Ops"
python3 app.py plan-learn --profile-id 1 --gaps "Kubernetes"
python3 app.py jobs-greenhouse <board-slug>
python3 app.py jobs-usajobs "engineer"    # needs USAJOBS_API_KEY locally
python3 app.py jobs-adzuna "engineer"    # needs ADZUNA_APP_ID + ADZUNA_APP_KEY locally
```

- **Project Forge v1:** live GitHub Search (last 30 days, by stars) + Hacker News velocity (points/hour), with a labelled curated-seed fallback if either source fails offline or is rate-limited. Set `GITHUB_TOKEN` locally to raise the GitHub rate limit.
- **Masters Atlas v1:** search starters for Germany, UK and Australia by field/level/country — explicitly labelled as search starters, not verified programme offers. Verify on the official database / university page before applying.
- **Dashboard v1:** localhost-only HTML view of profiles, CVs (with an Approve button for the exact hash) and tracked applications. It never submits anything and must not be exposed publicly.
- **Full design:** see `docs/blueprint.md`.

## v0.2: Ollama local-first rewrite mode (same approval gate)

```bash
python3 app.py ollama-status
python3 app.py cv-rewrite --profile-id 1 --demo-job 0
python3 app.py cv-list
python3 app.py cv-approve --cv-id 1   # approves ONLY that exact hash, submits nothing
```

- Local first: Ollama at `http://localhost:11434` (override with `OLLAMA_URL`, model with `OLLAMA_MODEL`, default `llama3.1` — you must have pulled a model yourself).
- If Ollama is not running, `cv-rewrite` safely falls back to the reorder-only CV and sends nothing anywhere. This workspace does **not** have Ollama installed, so that fallback is what you will see here until you install it on your own machine: install Ollama, run `ollama serve`, then `ollama pull llama3.1`, and retry.
- Fact-check (heuristic, not proof): rejects rewrites with new years, new numbers/percentages, new employers or new skills, and returns the reorder-only CV instead. A clean rewrite still stays **unapproved** until you run `cv-approve` on its exact hash.
- Cloud is a double gate, never a default: `--allow-cloud` on the command line AND `CAREER_ALLOW_CLOUD=1` AND `CAREER_CLOUD_BASE_URL` + `CAREER_CLOUD_API_KEY` in the environment. Without all of them, the cloud call is blocked before anything is sent, and the egress destination is printed when it is allowed.

## Quickstart (Python 3.10+, stdlib only — no packages to install)

```bash
cd mvp
python3 tests.py        # unit tests
python3 app.py demo     # 5-profession end-to-end demo, writes career.db + applications.csv
python3 app.py jobs-demo
python3 app.py jobs-greenhouse <board-slug>   # e.g. a real Greenhouse board slug
python3 app.py jobs-lever <company-slug>
```

## What v0.1 does

- Master profiles for 5 professions (student, teacher, finance, doctor, engineer) in local SQLite, with tone / depth / working-style settings.
- Job Radar: public Greenhouse + Lever feeds, USAJOBS and Adzuna adapters (the last two need keys in local env vars `USAJOBS_API_KEY`, `ADZUNA_APP_ID`, `ADZUNA_APP_KEY` — never committed), plus explainable 1–5 job scoring and labelled demo jobs.
- CV Studio: **reorder-only** tailoring — no fact can be invented, because nothing is rewritten. Diff + ATS-safe single-column text + SHA-256 hash.
- Application Desk: tracker tied to the exact approved CV hash, with CSV export. Approved means "ready for you to submit", not submitted.
- Scholarship & Masters Atlas v0: curated seed dataset for Germany, UK, Australia (+ Erasmus Mundus), with per-gate pass / fail / unknown and fix-it notes. **Re-check every official page before applying — last-verified dates are in the data file.**
- Project Forge v0 + Learning Compass v0: gap-based project suggestion (curated trend seed) and a weekly plan with profession-specific CPD units.

## What v0.1 does NOT do (honest limits)

- No live GitHub / Hacker News / arXiv trend fusion yet — trend topics are a curated seed, labelled as such in code.
- No Ollama / cloud LLM tailoring yet — reorder-only is deliberate for v0.1, so hallucination is impossible by design. LLM rewrite + fact-check is the next step, behind the same approval gate.
- No web UI yet — CLI only. A localhost dashboard is next after the core loop is proven.
- No masters-application workflow, no cloud sync, no multi-user mode.

## Next steps (in blueprint order)

1. ~~LLM rewrite mode (Ollama local-first, cloud opt-in) + fact-check pass, still diff + approval gated.~~ Done in v0.2 (logic + tests; actual Ollama runtime is on the user's machine).
2. Live trend fusion for Project Forge.
3. Localhost dashboard.
4. Private-MVP verification against the 5-profile test set, then the open-source checklist (licence, CONTRIBUTING, secret scan) before opening the repo.
