"""Personal AI Career Platform - MVP v0.1 (local, private, draft-only).

Python stdlib only. No auto-apply, no submission, no telemetry.
Data lives in a local SQLite file. Ollama / cloud LLM is NOT required:
CV tailoring in v0.1 is reorder-only (rule-based), so it cannot invent facts.
Run:  python3 app.py demo
       python3 app.py --help
"""
import argparse, csv, hashlib, html, json, os, re, sqlite3, sys, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE, "data")
DEFAULT_DB = os.path.join(BASE, "career.db")
USER_AGENT = "PersonalCareerPlatform-MVP/0.1 (local, private)"
STOPWORDS = set("and or the a an to of in for with on at by from as is are we you will have has had this that it its be been".split())

def load_json(name):
    with open(os.path.join(DATA_DIR, name), encoding="utf-8") as f:
        return json.load(f)

def templates():
    return load_json("profession_templates.json")

def scholarships():
    return load_json("scholarships.json")["awards"]

def init_db(path=DEFAULT_DB):
    con = sqlite3.connect(path)
    con.execute("""CREATE TABLE IF NOT EXISTS profiles
        (id INTEGER PRIMARY KEY, name TEXT, profession TEXT, data_json TEXT, settings_json TEXT)""")
    con.execute("""CREATE TABLE IF NOT EXISTS cvs
        (id INTEGER PRIMARY KEY, profile_id INTEGER, job_title TEXT, text TEXT, hash TEXT, approved INTEGER DEFAULT 0)""")
    con.execute("""CREATE TABLE IF NOT EXISTS applications
        (id INTEGER PRIMARY KEY, job_title TEXT, company TEXT, cv_hash TEXT, status TEXT, follow_up TEXT, outcome TEXT)""")
    con.commit()
    return con

def create_profile(con, name, profession, data, settings=None):
    if profession not in templates():
        raise ValueError(f"Unknown profession '{profession}'. Choose one of: {', '.join(sorted(templates()))}")
    cur = con.execute("INSERT INTO profiles (name, profession, data_json, settings_json) VALUES (?,?,?,?)",
                      (name, profession, json.dumps(data), json.dumps(settings or {})))
    con.commit()
    return cur.lastrowid

def get_profile(con, pid):
    row = con.execute("SELECT id, name, profession, data_json, settings_json FROM profiles WHERE id=?", (pid,)).fetchone()
    if not row:
        return None
    return {"id": row[0], "name": row[1], "profession": row[2],
            "data": json.loads(row[3]), "settings": json.loads(row[4])}

def list_profiles(con):
    return [{"id": r[0], "name": r[1], "profession": r[2]}
            for r in con.execute("SELECT id, name, profession FROM profiles ORDER BY id")]

# ---------------- Job scoring (explainable) ----------------

def _tokens(text):
    return set(w for w in re.findall(r"[a-z][a-z0-9+#-]*", (text or "").lower()) if w not in STOPWORDS)

def score_job(profile, job):
    """Return (score 1-5, breakdown). No opaque percentage."""
    skills = [s.lower() for s in profile["data"].get("skills", [])]
    jd = _tokens(job.get("description", "") + " " + job.get("title", ""))
    matched = [s for s in skills if any(t in jd for t in _tokens(s))]
    skill_ratio = (len(matched) / len(skills)) if skills else 0.0
    title_match = 1 if _tokens(profile["data"].get("target_role", "")) & _tokens(job.get("title", "")) else 0
    loc = profile["data"].get("location", "").lower()
    loc_match = 1 if loc and loc in (job.get("location", "") or "").lower() else 0
    # 1-5 scale: skills weighted most, then title, then location
    raw = 1 + 3 * skill_ratio + 0.5 * title_match + 0.5 * loc_match
    score = max(1, min(5, round(raw)))
    return score, {"skills_matched": matched, "skill_ratio": round(skill_ratio, 2),
                   "title_match": bool(title_match), "location_match": bool(loc_match)}

# ---------------- Job sources (public feeds first) ----------------

def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_greenhouse(board, limit=20):
    data = _get_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true")
    out = []
    for j in data.get("jobs", [])[:limit]:
        desc = html.unescape(re.sub(r"<[^>]+>", " ", j.get("content", "") or ""))
        out.append({"title": j.get("title"), "company": board, "location": (j.get("location") or {}).get("name", ""),
                    "url": j.get("absolute_url"), "description": re.sub(r"\s+", " ", desc)[:2000], "source": "greenhouse"})
    return out

def fetch_lever(company, limit=20):
    data = _get_json(f"https://api.lever.co/v0/postings/{company}?mode=json")
    out = []
    for j in data[:limit]:
        cats = j.get("categories") or {}
        out.append({"title": j.get("text"), "company": company, "location": cats.get("location", ""),
                    "url": j.get("hostedUrl"), "description": j.get("descriptionPlain", "")[:2000], "source": "lever"})
    return out

def fetch_usajobs(keyword, limit=20):
    key = os.environ.get("USAJOBS_API_KEY")
    if not key:
        return [], "USAJOBS_API_KEY not set - set it in your local environment to enable USAJOBS (no key is stored in the repo)."
    data = _get_json(f"https://data.usajobs.gov/api/search?Keyword={keyword}&ResultsPerPage={limit}",
                     headers={"Host": "data.usajobs.gov", "Authorization-Key": key})
    out = []
    for item in data.get("SearchResult", {}).get("SearchResultItems", []):
        d = item.get("MatchedObjectDescriptor", {})
        out.append({"title": d.get("PositionTitle"), "company": d.get("OrganizationName"), "location": "",
                    "url": d.get("PositionURI"), "description": "", "source": "usajobs"})
    return out, ""

def fetch_adzuna(keyword, country="gb", limit=20):
    app_id, key = os.environ.get("ADZUNA_APP_ID"), os.environ.get("ADZUNA_APP_KEY")
    if not app_id or not key:
        return [], "ADZUNA_APP_ID / ADZUNA_APP_KEY not set - set them locally to enable Adzuna."
    data = _get_json(f"https://api.adzuna.com/v1/api/jobs/{country}/search/1?app_id={app_id}&app_key={key}&results_per_page={limit}&what={keyword}")
    out = [{"title": r.get("title"), "company": (r.get("company") or {}).get("display_name"), "location": (r.get("location") or {}).get("display_name"),
            "url": r.get("redirect_url"), "description": r.get("description", "")[:2000], "source": "adzuna"} for r in data.get("results", [])]
    return out, ""

def demo_jobs():
    return [
        {"title": "AI/ML Engineer", "company": "Demo Company", "location": "Remote",
         "url": "https://example.com/jobs/ai-ml-engineer", "source": "demo",
         "description": "We need Python, LLM Ops, FastAPI and PostgreSQL. Build LLM pipelines, Docker deployments, and evaluation."},
        {"title": "Secondary School Teacher - Computer Science", "company": "Demo School", "location": "Karachi",
         "url": "https://example.com/jobs/teacher-cs", "source": "demo",
         "description": "Teach curriculum design, classroom management and assessment for computer science students."},
        {"title": "Financial Analyst", "company": "Demo Bank", "location": "Remote",
         "url": "https://example.com/jobs/financial-analyst", "source": "demo",
         "description": "Financial modelling in Excel, risk analysis for a portfolio."},
        {"title": "Resident Doctor", "company": "Demo Hospital", "location": "Karachi",
         "url": "https://example.com/jobs/resident-doctor", "source": "demo",
         "description": "Clinical assessment, patient safety review, evidence-based medicine in clinic."},
    ]

# ---------------- CV Studio: reorder-only tailoring ----------------

def tailor_cv(profile, job):
    """Reorder only. Every bullet/skill in the output already exists in the profile.
    Returns (text, diff, cv_hash). Nothing is invented."""
    data = profile["data"]
    jd = _tokens(job.get("description", "") + " " + job.get("title", ""))
    def bullet_score(b):
        return len(_tokens(b) & jd)
    skills_before = list(data.get("skills", []))
    skills_after = sorted(skills_before, key=lambda s: (-len(_tokens(s) & jd), skills_before.index(s)))
    lines = [profile["name"], f"Profession: {templates()[profile['profession']]['label']}", "",
             "SKILLS", ", ".join(skills_after), ""]
    all_bullets_after = []
    exp_lines = []
    for exp in data.get("experience", []):
        bullets = list(exp.get("bullets", []))
        ordered = sorted(bullets, key=lambda b: (-bullet_score(b), bullets.index(b)))
        all_bullets_after.extend(ordered)
        exp_lines.append(f"{exp.get('role','')} - {exp.get('org','')} ({exp.get('dates','')})")
        exp_lines.extend(f"- {b}" for b in ordered)
        exp_lines.append("")
    lines.append("EXPERIENCE")
    lines.extend(exp_lines)
    lines.append("EDUCATION")
    lines.extend(f"- {e}" for e in data.get("education", []))
    text = "\n".join(lines).strip() + "\n"
    diff = {"skills_before": skills_before, "skills_after": skills_after,
            "note": "Reorder-only: no bullet, skill, title, date or metric was added, removed or rewritten."}
    return text, diff, hashlib.sha256(text.encode()).hexdigest()

def save_cv(con, profile_id, job_title, text, h):
    cur = con.execute("INSERT INTO cvs (profile_id, job_title, text, hash) VALUES (?,?,?,?)", (profile_id, job_title, text, h))
    con.commit()
    return cur.lastrowid

def approve_cv(con, cv_id):
    row = con.execute("SELECT hash FROM cvs WHERE id=?", (cv_id,)).fetchone()
    if not row:
        raise ValueError("CV not found")
    con.execute("UPDATE cvs SET approved=1 WHERE id=?", (cv_id,))
    con.commit()
    return row[0]  # approval is tied to this exact hash

def add_application(con, job_title, company, cv_hash, status="draft", follow_up="", outcome=""):
    cur = con.execute("INSERT INTO applications (job_title, company, cv_hash, status, follow_up, outcome) VALUES (?,?,?,?,?,?)",
                      (job_title, company, cv_hash, status, follow_up, outcome))
    con.commit()
    return cur.lastrowid

def export_applications(con, path):
    rows = con.execute("SELECT job_title, company, cv_hash, status, follow_up, outcome FROM applications ORDER BY id").fetchall()
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["job_title", "company", "cv_hash", "status", "follow_up", "outcome"])
        w.writerows(rows)
    return len(rows)

# ---------------- Scholarship rule engine ----------------

def eval_gate(profile_data, gate):
    field, typ, val = gate["field"], gate["type"], gate["value"]
    if field not in profile_data or profile_data[field] in (None, ""):
        return "unknown"
    actual = profile_data[field]
    if typ == "in":
        return "pass" if actual in val else "fail"
    if typ == "not_equals":
        return "pass" if actual != val else "fail"
    if typ == "min":
        try:
            return "pass" if float(actual) >= float(val) else "fail"
        except (TypeError, ValueError):
            return "unknown"
    if typ == "min_text":
        # crude CEFR order for MVP: A1<A2<B1<B2<C1<C2
        order = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
        return "pass" if order.get(str(actual), 0) >= order.get(str(val), 0) else "fail"
    return "unknown"

def match_scholarships(profile, countries=None):
    out = []
    for a in scholarships():
        if countries and a["country"] not in countries:
            continue
        gates = [{"gate": g, "verdict": eval_gate(profile["data"], g)} for g in a["gates"]]
        fails = [g for g in gates if g["verdict"] == "fail"]
        unknowns = [g for g in gates if g["verdict"] == "unknown"]
        fix = []
        for g in fails:
            fix.append(f"Fix gate '{g['gate']['field']}': required {g['gate']['value']}, you have {profile['data'].get(g['gate']['field'])}")
        for g in unknowns:
            fix.append(f"Missing info for gate '{g['gate']['field']}' - add it to your profile to get a verdict, not a rejection.")
        out.append({**a, "gates": gates, "overall": "eligible-so-far" if not fails and not unknowns else ("blocked" if fails else "needs-info"), "fix_it": fix})
    return out

# ---------------- Project Forge v0 + Learning Compass v0 ----------------

TREND_TOPICS = [
    "Local-first LLM agent evaluation and cost tracking",
    "Evidence-linked debugging assistant for small codebases",
    "Accessible, offline-first learning planner for teachers",
    "Personal finance dashboard with explainable budgeting",
]

def suggest_project(profile, target_skills):
    gaps = [s for s in target_skills if s not in profile["data"].get("skills", [])]
    gap = gaps[0] if gaps else "a skill from your target roles"
    topic = TREND_TOPICS[0]
    return {"gap": gap, "topic": topic,
            "title": f"{topic} - learning {gap}",
            "scaffold": ["README: problem, what it does, how to run it", "Milestone 1: smallest working version",
                         "Milestone 2: add tests and a demo", "Milestone 3: 'what I learned' artefact + CV bullet",
                         "Note: trend topics above are a curated seed in v0.1; live GitHub/HN/arXiv fusion is the next iteration."]}

def weekly_plan(profile, gaps):
    unit = templates()[profile["profession"]]["cpd_unit"]
    return {"cpd_unit": unit,
            "week": [{"day": "Mon", "task": f"Learn fundamentals of {gaps[0] if gaps else 'your top gap'} (90 min)"},
                     {"day": "Wed", "task": "Build a small exercise / project milestone (90 min)"},
                     {"day": "Fri", "task": "Checkpoint: quiz yourself, write 'what I learned', update profile evidence (45 min)"}],
            "checkpoint": "End of week: can you explain the gap skill and show an artefact? If not, re-plan, don't just add hours."}

# ---------------- Masters search starters ----------------

def masters_list():
    return load_json("masters.json")

def match_masters(field="", level="master", country=""):
    out = []
    data = masters_list()
    for m in data["programmes"]:
        if country and m["country"].lower() != country.lower():
            continue
        if level and m["level"].lower() != level.lower():
            continue
        if field and field.lower() not in m["field"].lower():
            continue
        out.append(m)
    return out, data["note"]

# ---------------- CLI ----------------

def main(argv=None):
    p = argparse.ArgumentParser(description="Personal AI Career Platform MVP v0.1 - local, draft-only")
    p.add_argument("--db", default=DEFAULT_DB)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    a = sub.add_parser("profile-add"); a.add_argument("name"); a.add_argument("profession"); a.add_argument("--data", required=True, help="JSON string")
    a = sub.add_parser("profile-list")
    a = sub.add_parser("demo")
    a = sub.add_parser("jobs-demo")
    a = sub.add_parser("jobs-greenhouse"); a.add_argument("board")
    a = sub.add_parser("jobs-lever"); a.add_argument("company")
    sub.add_parser("ollama-status")
    a = sub.add_parser("cv-rewrite"); a.add_argument("--profile-id", type=int, required=True)
    a.add_argument("--demo-job", type=int, default=0); a.add_argument("--job-file", default="")
    a.add_argument("--model", default=""); a.add_argument("--allow-cloud", action="store_true")
    a = sub.add_parser("cv-approve"); a.add_argument("--cv-id", type=int, required=True)
    a = sub.add_parser("cv-list")
    a = sub.add_parser("cv-tailor"); a.add_argument("--profile-id", type=int, required=True); a.add_argument("--demo-job", type=int, default=0)
    a = sub.add_parser("scholarships-match"); a.add_argument("--profile-id", type=int, required=True); a.add_argument("--country", action="append", default=[])
    a = sub.add_parser("masters-match"); a.add_argument("--field", default=""); a.add_argument("--level", default="master"); a.add_argument("--country", default="")
    a = sub.add_parser("project-suggest"); a.add_argument("--profile-id", type=int, required=True); a.add_argument("--target-skills", default="")
    a = sub.add_parser("plan-learn"); a.add_argument("--profile-id", type=int, required=True); a.add_argument("--gaps", default="")
    a = sub.add_parser("jobs-usajobs"); a.add_argument("keyword")
    a = sub.add_parser("jobs-adzuna"); a.add_argument("keyword"); a.add_argument("--country", default="gb")
    a = sub.add_parser("track-add"); a.add_argument("--job", required=True); a.add_argument("--company", required=True); a.add_argument("--cv-hash", required=True); a.add_argument("--status", default="draft")
    a = sub.add_parser("track-list")
    a = sub.add_parser("track-export"); a.add_argument("--out", default="applications.csv")
    a = sub.add_parser("serve"); a.add_argument("--port", type=int, default=8000)
    args = p.parse_args(argv)
    con = init_db(args.db)
    if args.cmd == "init":
        print(f"Database ready: {args.db} (local only)")
    elif args.cmd == "profile-add":
        pid = create_profile(con, args.name, args.profession, json.loads(args.data))
        print(f"Profile {pid}: {args.name} ({args.profession})")
    elif args.cmd == "profile-list":
        for pr in list_profiles(con):
            print(pr)
    elif args.cmd == "jobs-demo":
        for j in demo_jobs():
            print(j["title"], "-", j["company"], "-", j["source"], "-", j["url"])
    elif args.cmd == "jobs-greenhouse":
        for j in fetch_greenhouse(args.board):
            print(j["title"], "-", j.get("location"), "-", j["url"])
    elif args.cmd == "jobs-lever":
        for j in fetch_lever(args.company):
            print(j["title"], "-", j.get("location"), "-", j["url"])
    elif args.cmd == "demo":
        run_demo(con)
    elif args.cmd == "ollama-status":
        from llm_rewrite import ollama_status
        st = ollama_status()
        print(st)
        if not st["available"]:
            print("Ollama is not reachable. To enable local rewrite: install Ollama, run 'ollama serve',")
            print("then 'ollama pull llama3.1' (or set OLLAMA_MODEL to a model you have pulled), and retry.")
            print("Without Ollama, cv-rewrite safely falls back to the reorder-only CV - nothing is sent anywhere.")
    elif args.cmd == "cv-rewrite":
        from llm_rewrite import rewrite_cv
        pr = get_profile(con, args.profile_id)
        if not pr:
            print(f"No profile with id {args.profile_id}"); return 1
        if args.job_file:
            with open(args.job_file, encoding="utf-8") as f:
                job = json.load(f)
        else:
            job = demo_jobs()[args.demo_job]
        res = rewrite_cv(pr, job, allow_cloud=args.allow_cloud, model=(args.model or None))
        cv_id = save_cv(con, pr["id"], job["title"], res["text"], res["hash"])
        print(f"Mode: {res['mode']}")
        print(f"Egress: {res['egress']}")
        print(f"Saved CV id {cv_id}, hash {res['hash']} - NOT approved yet.")
        if res["flags"]:
            print("Fact-check flags:", res["flags"])
        print("Diff (first 40 lines):")
        print("\n".join(res["diff"].splitlines()[:40]))
        print(f"To approve this exact text, run: python3 app.py cv-approve --cv-id {cv_id}")
        print("Nothing has been submitted. Approval only marks this hash as approved for you to submit yourself.")
    elif args.cmd == "cv-approve":
        h = approve_cv(con, args.cv_id)
        print(f"Approved CV {args.cv_id} with hash {h}. This does not submit anything.")
    elif args.cmd == "cv-list":
        for r in con.execute("SELECT id, profile_id, job_title, substr(hash,1,12), approved FROM cvs ORDER BY id"):
            print(r)
    elif args.cmd == "cv-tailor":
        pr = get_profile(con, args.profile_id)
        job = demo_jobs()[args.demo_job]
        text, diff, h = tailor_cv(pr, job)
        cv_id = save_cv(con, pr["id"], job["title"], text, h)
        print(f"Reorder-only CV id {cv_id}, hash {h} - NOT approved yet. Approve with: python3 app.py cv-approve --cv-id {cv_id}")
        print(text)
    elif args.cmd == "scholarships-match":
        pr = get_profile(con, args.profile_id)
        for s in match_scholarships(pr, countries=(args.country or None)):
            print(f"\n{s['name']} ({s['country']}) - {s['overall']}")
            print(f"  {s['summary']} | {s['official_url']} | last verified: {s['last_verified']}")
            for g in s["gates"]:
                print(f"  gate {g['gate']['field']}: {g['verdict']}")
            for f in s["fix_it"]:
                print(f"  - {f}")
    elif args.cmd == "masters-match":
        matches, note = match_masters(field=args.field, level=args.level, country=args.country)
        print(note)
        for m in matches:
            print(f"\n{m['programme_type']} - {m['country']} ({m['language']})")
            print(f"  Search: {m['official_search_url']} | {m['tuition_note']}")
        if not matches:
            print("No matching search starters - try a broader field or country (Germany / UK / Australia).")
    elif args.cmd == "project-suggest":
        from trends import fuse_trends, suggest_project_v1
        pr = get_profile(con, args.profile_id)
        trends, notes = fuse_trends()
        for n in notes:
            print(n)
        proj = suggest_project_v1(pr, [s.strip() for s in args.target_skills.split(",") if s.strip()], trends)
        print(f"\nTitle: {proj['title']}\nGap: {proj['gap']}\nTrend: {proj['trend']}")
        for step in proj["scaffold"]:
            print(f"- {step}")
    elif args.cmd == "plan-learn":
        pr = get_profile(con, args.profile_id)
        gaps = [s.strip() for s in args.gaps.split(",") if s.strip()]
        plan = weekly_plan(pr, gaps)
        print(f"CPD unit: {plan['cpd_unit']}")
        for d in plan["week"]:
            print(f"{d['day']}: {d['task']}")
        print(plan["checkpoint"])
    elif args.cmd == "jobs-usajobs":
        jobs, note = fetch_usajobs(args.keyword)
        if note:
            print(note)
        for j in jobs:
            print(j["title"], "-", j.get("company"), "-", j["url"])
    elif args.cmd == "jobs-adzuna":
        jobs, note = fetch_adzuna(args.keyword, country=args.country)
        if note:
            print(note)
        for j in jobs:
            print(j["title"], "-", j.get("company"), "-", j["url"])
    elif args.cmd == "track-add":
        aid = add_application(con, args.job, args.company, args.cv_hash, status=args.status)
        print(f"Application {aid} tracked (status: {args.status}). This does not submit anything.")
    elif args.cmd == "track-list":
        for r in con.execute("SELECT id, job_title, company, substr(cv_hash,1,12), status, follow_up, outcome FROM applications ORDER BY id"):
            print(r)
    elif args.cmd == "track-export":
        print(f"Exported {export_applications(con, args.out)} rows to {args.out}")
    elif args.cmd == "serve":
        from dashboard import serve
        serve(args.db, port=args.port)
    return 0

def run_demo(con):
    print("== MVP demo: 5 professions, one core loop ==")
    samples = {
        "student": {"skills": ["Python", "Research"], "experience": [{"role": "Research Assistant", "org": "Demo University", "dates": "2025", "bullets": ["Built a Python data-cleaning script", "Wrote a research summary"]}], "education": ["BSc Computer Science (in progress)"], "target_role": "AI Engineer", "location": "Remote", "nationality": "Pakistan", "level": "master", "prior_degree": "bachelor", "experience_years": 1, "language_level": "B2"},
        "teacher": {"skills": ["Curriculum design", "Classroom management"], "experience": [{"role": "Teacher", "org": "Demo School", "dates": "2023-2025", "bullets": ["Designed a computer science curriculum", "Managed classroom assessment"]}], "education": ["BEd"], "target_role": "Teacher", "location": "Karachi", "level": "master", "experience_years": 3, "language_level": "B2"},
        "finance": {"skills": ["Financial modelling", "Excel"], "experience": [{"role": "Analyst", "org": "Demo Bank", "dates": "2023-2025", "bullets": ["Built a financial model in Excel", "Analysed risk for a portfolio"]}], "education": ["BCom"], "target_role": "Analyst", "location": "Remote", "level": "master", "experience_years": 2, "language_level": "B2"},
        "doctor": {"skills": ["Clinical assessment", "Patient safety"], "experience": [{"role": "Resident Doctor", "org": "Demo Hospital", "dates": "2023-2025", "bullets": ["Assessed patients in clinic", "Led a patient safety review"]}], "education": ["MBBS"], "target_role": "Doctor", "location": "Karachi", "level": "master", "experience_years": 3, "language_level": "B2"},
        "engineer": {"skills": ["Python", "LLM Ops", "FastAPI"], "experience": [{"role": "AI Engineer", "org": "Demo Lab", "dates": "2024-2025", "bullets": ["Built LLM pipelines in Python", "Deployed a FastAPI service with Docker"]}], "education": ["BSc Software Engineering"], "target_role": "AI/ML Engineer", "location": "Remote", "nationality": "Pakistan", "level": "master", "prior_degree": "bachelor", "experience_years": 2, "language_level": "B2"},
    }
    for prof, data in samples.items():
        pid = create_profile(con, f"Demo {prof}", prof, data, {"tone": "professional", "depth": "standard", "working_style": "reviewer"})
        pr = get_profile(con, pid)
        job_by_prof = {"student": 0, "engineer": 0, "teacher": 1, "finance": 2, "doctor": 3}
        job = demo_jobs()[job_by_prof[prof]]
        score, breakdown = score_job(pr, job)
        text, diff, h = tailor_cv(pr, job)
        cv_id = save_cv(con, pid, job["title"], text, h)
        approved_hash = approve_cv(con, cv_id)
        add_application(con, job["title"], job["company"], approved_hash, status="draft-approved", follow_up="Review in 7 days")
        sch = [s for s in match_scholarships(pr) if s["country"] in ("Germany", "UK", "Australia")]
        print(f"\n[{prof}] score {score}/5 for '{job['title']}' | matched skills: {breakdown['skills_matched']} | CV approved hash: {approved_hash[:12]}... | scholarships checked: {len(sch)}")
    n = export_applications(con, os.path.join(BASE, "applications.csv"))
    print(f"\nDemo complete. Applications exported: {n} rows to mvp/applications.csv. No application was submitted - all are draft-approved only.")

if __name__ == "__main__":
    sys.exit(main())
