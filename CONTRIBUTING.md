# Contributing

Welcome — and please read the guardrails first, they are the point of this project.

## Non-negotiable rules

1. **Draft & approve only.** This project must never submit a job application, scholarship application or any other outward action by itself. Every outward artefact needs a human approving its exact hash.
2. **Never invent profile facts.** CV code may reorder and reword existing facts only. Any rewrite path must go through the fact-check in `llm_rewrite.py` and still require approval.
3. **Legal-by-default sources.** Public ATS feeds and documented APIs only. No LinkedIn / Indeed scraping, no account-based scraping.
4. **No secrets, no real personal data in the repo.** API keys live in local environment variables only. Test fixtures must be synthetic demo data, clearly labelled.
5. **Label live vs seed data.** Scholarship and masters data must carry an official URL and a last-verified date. Trend data must say whether it came from a live API or the curated seed.

## Good first issues

- A new public ATS adapter (same shape as Greenhouse / Lever in `app.py`)
- A new profession template in `data/profession_templates.json`
- A new scholarship entry in `data/scholarships.json` — with official URL, gates and last-verified date
- A new masters search starter in `data/masters.json`

## Running it

```bash
python3 tests.py
python3 app.py demo
python3 app.py serve --port 8000   # http://127.0.0.1:8000/ , local only
```

All tests must pass before a pull request. If a test needs a network call, it must also pass offline via the labelled fallback path.
