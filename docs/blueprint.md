# Personal AI Career Platform — Blueprint (decisions applied, 2026-10-25)

## 1. Decisions this blueprint is built on

User decisions, 2026-10-25:

1. **First audience: all professions from day one** — students, teachers, finance people, doctors, engineers and others. No engineer-only MVP.
2. **Scholarship countries: Germany, UK, plus Australia as the third.** (Germany = DAAD, UK = Chevening / Commonwealth / Gates Cambridge, Australia = Australia Awards and university awards.)
3. **Job sources: public ATS feeds + USAJOBS + Adzuna.** No LinkedIn / Indeed scraping.
4. **Model strategy: local-first (Ollama), cloud opt-in.** Data stays local by default.
5. **Auto-apply posture: never — draft & approve only.** The platform never submits an application by itself.
6. **Repository & licence: private until the MVP works, then open.** Open licence not yet chosen.

Everything below follows from those six. If any of them changes, the MVP scope changes with it — especially #1 and #5.

## 2. Vision in one paragraph

One user-owned master profile drives everything: jobs worth applying for, a CV tailored to each job without inventing facts, applications tracked to the exact CV version sent, portfolio projects built from real trending problems, scholarships and masters programmes matched by explicit eligibility rules, and a weekly learning plan that closes the skill gaps those jobs and projects reveal. The user approves every outward action. The platform is a preparation and evidence machine, not a spray-and-pray auto-applier.

## 3. Non-negotiable principles

- **Approval by default.** Nothing leaves the machine without the user approving the exact artefact — the exact CV PDF, the exact cover letter, the exact application draft. Approval is tied to a hash of that artefact, so an edited draft needs a fresh approval.
- **Never invent.** CV tailoring may reorder, reword and emphasise existing profile facts. It may not add a title, employer, date, qualification or metric that is not in the master profile. A "Changes made" diff is shown for every tailored version, and any claim the system cannot ground is flagged, not smoothed over.
- **Local-first, egress-labelled.** Master profile, jobs, CVs, applications and learning data live in local storage. Ollama runs locally. Any cloud call is opt-in, per feature, and labelled with what leaves the machine. No telemetry in the MVP.
- **Legal-by-default discovery.** Public ATS feeds first (Greenhouse, Lever, Ashby and similar public job-board endpoints), then USAJOBS (free API key) and Adzuna (free key, with limits). No LinkedIn / Indeed search scraping, no account-based scraping.
- **Explain, don't just score.** Every job score, scholarship verdict and learning recommendation shows its reasons. A single opaque percentage is not acceptable for any of these.
- **Portable profile.** Tone, research depth, working style, verbosity, format and profession template are a versioned settings profile the user owns and can export — not hidden prompt state.

## 4. The master profile (the centre of the platform)

One profile, six modules reading from it. Generic core fields, plus a profession extension — this is how "all professions from day one" stays buildable:

- **Core:** identity and contact, education, experience (role, organisation, dates, quantified outcomes), skills with evidence links, languages, location and work preferences, salary / deal-breakers, target roles and countries.
- **Profession extension (template, not hard-coded):** e.g. doctor → registration, speciality, CME/CPD hours; teacher → subjects, certifications, CPD workshops; finance → licences, CPE credits, specialisms; student → degree, expected graduation, internships; engineer → stack, repos, certifications. Templates ship for at least five professions in the MVP and are data files, so adding a profession does not require code changes.
- **Settings profile:** tone (e.g. professional / friendly / direct), research depth (quick / standard / deep), working style (guided / autonomous / reviewer / sprint), verbosity and format preferences, evidence strictness, risk posture.
- **Evidence store:** every profile fact can link to evidence — a project repo, a certificate, a publication, a performance note. Project Forge output feeds back here, so a finished project becomes CV evidence.

## 5. Modules

### 5.1 Job Radar (discovery + scoring)
- Sources: public ATS feeds for a user-chosen company list, USAJOBS, Adzuna.
- Politeness: max 1 request/second per host, backoff on 429/5xx honouring `Retry-After`, descriptive User-Agent, public feeds only.
- Scoring: 1–5 with an explainable breakdown (skills, experience, salary, location, role alignment). Ghost-job hygiene: re-check the source posting before showing it as live, and flag postings that disappear or age without change.
- Output: a ranked, filterable list — never an auto-submission queue.

### 5.2 CV Studio (grounded tailoring)
- Input: master profile + one job description.
- Output: tailored CV (single-column, plain-text-safe for ATS parsing) + cover letter, with a diff vs the master CV, an ATS parse check, and a fact-check pass against the profile.
- Modes: reorder-only (rule-based, zero rewriting — the safest mode) and assisted rewrite (local LLM, still diff-checked and fact-checked).
- Every version is stored with its job, its diff and its hash.

### 5.3 Application Desk (tracking + approval gate)
- Kanban / table tracker: job → CV version sent → diff → status → follow-up date → interview outcome.
- The key metric is outcome linked to CV version (which version got interviews), not application count.
- Approval flow: draft → user reviews exact PDF → approve (hash recorded) → user submits on the employer's site, or exports the prepared draft. The platform itself never submits.
- Export: CSV export of the full tracker, local-first.

### 5.4 Project Forge (trend → scoped project → CV evidence)
- Signals fused, never one hype source alone: GitHub star velocity + open "help wanted" / "good first issue" issues, Hacker News velocity (points/hour, not raw score), arXiv / academic activity for research-led professions, and skill frequency in Job Radar job descriptions.
- Each idea is scoped to the user's level and to a named skill gap, with a repo scaffold, README, milestones and a "what I learned" artefact.
- On completion, the project is offered as evidence in the master profile and as a CV bullet — closing the loop back into CV Studio.
- MVP scope: signal fusion + scoping + scaffold. No auto-generated portfolio code presented as the user's own work without review.

### 5.5 Scholarship & Masters Atlas (rule engine, not a percentage)
- Countries in MVP: Germany, UK, Australia.
- Data reality: there is no general public scholarship API. The platform curates a dated dataset — one record per award with official URL, last-verified date, deadline cycle and source. Stale or 404 records are flagged, never silently listed.
- Flagships to seed: Germany — DAAD Study Scholarships / EPOS / Helmut-Schmidt, DAAD International Programmes, Hochschulkompass; UK — Chevening, Commonwealth, Gates Cambridge; Australia — Australia Awards, Destination Australia, university awards; plus Erasmus Mundus as an EU-wide route.
- Eligibility as a rule engine: hard gates (nationality, level, field, prior degree, work experience, language) each return pass / fail / unknown. "Unknown" triggers a checklist, not a rejection. The course × award join matters (e.g. which courses are eligible for which award) and two-stage routes (apply to university first, then be nominated) are modelled explicitly.
- Masters search is separate from funding: programme search (DAAD International Programmes, Hochschulkompass, Studyportals / Mastersportal, university sites) joined to funding eligibility where the data allows.
- Caution carried from research: Netherlands OKP status was conflicting across sources — do not add the Netherlands until Study in Holland is checked at build time. The same check-before-listing rule applies to every award.

### 5.6 Learning Compass (skill planning + CPD)
- Input: skill gaps from Job Radar (skills in target jobs the profile lacks) + Project Forge gaps + the user's own goals.
- Output: a weekly plan — sequenced skills, deadlines, assessment checkpoints, varied resources, and flexibility to re-plan. Spaced repetition (Anki-style, FSRS) for retention where it fits.
- Profession-aware: CPD/CPE conventions differ — doctors (CME cases), teachers (workshops), finance (CPE credits, where 50 minutes can equal 1 credit vs 1 hour = 1 CPD hour), engineers (roadmaps + certification expiry). The profession template carries the unit, so the plan counts the right thing.
- MVP scope: weekly plan + gap tracking + checkpoint reviews. Full adaptive modelling (IRT / knowledge tracing) is post-MVP.

## 6. Architecture (MVP)

Local-first, API-first, boring where it counts:

- **Backend:** Python, FastAPI, SQLite (local file, migratable to PostgreSQL later). This mirrors the JobFlow pattern (FastAPI + SQLite) and keeps a single local deployable.
- **Frontend (MVP):** server-rendered web UI on localhost (127.0.0.1 only) — FastAPI + htmx style, or a minimal Next.js front end if the user prefers the AgentOps stack. API-first either way, so the UI can be replaced later without touching the core.
- **LLM layer:** provider-independent adapter. Default: Ollama locally (model configurable, e.g. a small local model for tailoring + review). Cloud adapter: opt-in only, per feature, with an egress label showing what is sent. A deterministic / rule-based fallback (reorder-only tailoring, rule-based scoring) must work with no model at all.
- **Storage:** local SQLite + local files (`data/` for profile/jobs/applications, `artefacts/` for CV PDFs and diffs). No cloud sync in the MVP.
- **Services (internal boundaries):** Profile service, Job source adapters (one per source type), Scoring service, Tailoring service (reorder + LLM rewrite + fact-check), Tracker service, Scholarship dataset + rule engine, Trend signal service, Planner service, Settings service.
- **Security:** bind to localhost, no auth needed locally in MVP (documented limitation); add auth before any hosted deployment. Secrets (USAJOBS / Adzuna keys) in a local env file, never in the repo — enforced by a pre-commit / CI check before the repo goes public.

Why not start with a full Next.js + PostgreSQL + LangGraph stack? It is the right shape for a hosted product, but it slows the private MVP and adds hosting surface before the core loop (profile → job → tailored CV → approved draft → tracked outcome) is proven. Build the core locally first; the API boundary makes the hosted version a later, clean step.

## 7. MVP scope — what "works" means

MVP is done when one user can, locally, with no cloud call:

1. Create a master profile using any of five profession templates, with settings (tone, depth, working style).
2. Import / fetch jobs from at least one ATS feed, USAJOBS and Adzuna, see explainable scores, and save shortlisted jobs.
3. Generate a tailored CV + cover letter for a saved job, review the diff and ATS check, and approve the exact PDF (hash recorded).
4. Track that application to outcome, linked to the CV version sent, with CSV export.
5. See scholarship matches for Germany, UK and Australia with per-gate pass / fail / unknown and a fix-it checklist for failed gates.
6. Get one scoped project idea from fused trend signals, scaffolded, tied to a skill gap.
7. Get a weekly learning plan from that gap, with checkpoints.

Out of MVP scope (explicitly): auto-apply / auto-submit, LinkedIn / Indeed scraping, cloud sync, multi-user / hosted deployment, adaptive learning engine, full masters-application workflow, payment / premium features.

Test set for "works": five end-to-end test profiles — one student, one teacher, one finance professional, one doctor, one engineer — each completing steps 1–7 with their own template, without engineer-specific fields leaking into the others.

## 8. Repo plan — private now, open later

- **Now (private):** single private repo, `main` protected, no secrets, demo data clearly marked as synthetic, README describing the vision and the six decisions.
- **Before opening (checklist):** choose a licence (recommendation: MIT for maximum adoption, Apache 2.0 if patent protection matters — decision still open), remove any real personal data from test fixtures, add CONTRIBUTING, CODE_OF_CONDUCT, SECURITY, issue templates, a runnable local quickstart (Ollama + one command), CI (lint, tests, secret scan), and a "what this tool will never do" section stating the draft-and-approve-only posture.
- **After opening:** good-first-issue labels tied to real, scoped work (new ATS adapter, new profession template, new scholarship dataset entries with sources), so contributors extend data and templates without touching the approval core.

## 9. Risks and how this blueprint answers them

- **Hallucinated CV facts** → reorder-only mode, fact-check vs profile, diff, approval of exact PDF.
- **ATS parsing loss** → single-column, plain-text-safe output, ATS parse check before approval.
- **Ghost / stale jobs and scholarships** → re-check source postings, last-verified dates, stale flagging.
- **Scraping / ToS risk** → public feeds + documented APIs only, politeness limits.
- **All-professions scope creep** → profession templates as data files, five-template test set, MVP scope in §7 is the fence.
- **Local model quality** → rule-based fallback always works; cloud is opt-in, never required for the core loop.
- **Privacy** → local-first storage, no telemetry, egress labels, secrets out of the repo.

## 10. Suggested build order

1. Master profile + settings + five profession templates + SQLite schema.
2. CV Studio (reorder-only first, then LLM rewrite + fact-check) + Application Desk tracker + approval hash.
3. Job Radar adapters (ATS feeds, USAJOBS, Adzuna) + explainable scoring.
4. Scholarship dataset (DE / UK / AU seed) + rule engine + masters programme join.
5. Project Forge signals + scoping + scaffold.
6. Learning Compass weekly planner + gap tracking.
7. Private-MVP verification against the five-profile test set, then the open-source checklist in §8.

## 11. Open questions (not blockers for the MVP)

- Licence: MIT vs Apache 2.0?
- Frontend: localhost htmx-style UI for speed, or Next.js from the start to match the AgentOps stack?
- Default local model for Ollama (size vs quality on a typical laptop)?
- USAJOBS / Adzuna keys: user-supplied at setup, with a key-free demo mode?

## 12. Next step requested

Approve this blueprint (or amend it), and the next step is to start the MVP build in order §10, in a private repo — no code, no repo and no external submission until you say go.
