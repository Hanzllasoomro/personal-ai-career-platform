"""MVP v0.1 tests - stdlib only. Run: python3 tests.py"""
import os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app import (templates, create_profile, get_profile, init_db, score_job,
                 tailor_cv, save_cv, approve_cv, add_application, export_applications,
                 match_scholarships, suggest_project, weekly_plan, demo_jobs)
from llm_rewrite import rewrite_cv, fact_check, call_cloud, ollama_status

def check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    assert cond, name

def main():
    db = os.path.join(tempfile.mkdtemp(), "test.db")
    con = init_db(db)
    check("5 profession templates", len(templates()) == 5)
    data = {"skills": ["Python", "LLM Ops"], "experience": [{"role": "AI Engineer", "org": "Demo Lab", "dates": "2024", "bullets": ["Built LLM pipelines in Python", "Deployed FastAPI"]}], "education": ["BSc Software Engineering"], "target_role": "AI/ML Engineer", "location": "Remote", "level": "master", "prior_degree": "bachelor", "experience_years": 2, "language_level": "B2"}
    pid = create_profile(con, "Test Engineer", "engineer", data)
    pr = get_profile(con, pid)
    job = demo_jobs()[0]
    score, br = score_job(pr, job)
    check("job score 1-5 with breakdown", 1 <= score <= 5 and "skills_matched" in br)
    text, diff, h = tailor_cv(pr, job)
    master_bullets = [b for e in data["experience"] for b in e["bullets"]]
    check("tailoring invents nothing: all output bullets are master bullets",
          all(any(b in line for b in master_bullets) for line in text.splitlines() if line.startswith("- ") and "BSc" not in line))
    check("tailoring is single-column plain text (no tables)", "|" not in text and "\t" not in text)
    cv_id = save_cv(con, pid, job["title"], text, h)
    check("approval hash matches CV hash", approve_cv(con, cv_id) == h)
    add_application(con, job["title"], job["company"], h, status="draft-approved")
    out = os.path.join(tempfile.mkdtemp(), "apps.csv")
    check("tracker CSV export", export_applications(con, out) == 1)
    sch = match_scholarships(pr, countries=["Germany", "UK", "Australia"])
    check("scholarship engine covers DE/UK/AU", {s["country"] for s in sch} == {"Germany", "UK", "Australia"})
    check("scholarship verdicts are pass/fail/unknown, not opaque %",
          all(g["verdict"] in ("pass", "fail", "unknown") for s in sch for g in s["gates"]))
    # unknown gate: profile with no nationality/level info
    pid2 = create_profile(con, "Test NoInfo", "student", {"skills": ["Python"], "experience": [], "education": []})
    pr2 = get_profile(con, pid2)
    sch2 = match_scholarships(pr2)
    check("missing profile field gives 'unknown', not rejection",
          any(g["verdict"] == "unknown" for s in sch2 for g in s["gates"]))
    proj = suggest_project(pr, ["Python", "Kubernetes"])
    check("project suggestion names a real gap", proj["gap"] == "Kubernetes")
    plan = weekly_plan(pr, ["Kubernetes"])
    check("learning plan has CPD unit + checkpoint", plan["cpd_unit"] and plan["checkpoint"])
    # --- v0.2: Ollama rewrite, same approval gate ---
    good_rewrite = "Test Engineer\nProfession: Engineer (AI/ML/LLM Ops)\n\nSKILLS\nPython, LLM Ops\n\nEXPERIENCE\nAI Engineer - Demo Lab (2024)\n- Built LLM pipelines in Python for production use\n- Deployed FastAPI services\n\nEDUCATION\n- BSc Software Engineering\n"
    res = rewrite_cv(pr, job, llm_fn=lambda prompt: good_rewrite)
    check("clean LLM rewrite passes fact-check and is NOT auto-approved",
          res["mode"] == "custom-llm (test/injectable)" and res["flags"] == [])
    cv2 = save_cv(con, pid, job["title"], res["text"], res["hash"])
    row = con.execute("SELECT approved FROM cvs WHERE id=?", (cv2,)).fetchone()
    check("rewritten CV saved as unapproved until explicit approval", row[0] == 0)
    check("same approval gate approves rewritten CV hash", approve_cv(con, cv2) == res["hash"])
    bad_rewrite = good_rewrite.replace("Demo Lab", "Google").replace("2024", "2026").replace("FastAPI services", "FastAPI services serving 10 million users")
    res_bad = rewrite_cv(pr, job, llm_fn=lambda prompt: bad_rewrite)
    check("invented employer/year/metric rewrite is rejected to reorder-only",
          res_bad["mode"] == "rejected-fallback-reorder" and len(res_bad["flags"]) >= 2)
    check("fact-check flags invented facts directly",
          len(fact_check(pr, bad_rewrite, job)) >= 2)
    res_fb = rewrite_cv(pr, job)
    check("Ollama unavailable here falls back to reorder-only, sends nothing",
          res_fb["mode"] == "fallback-reorder" and "Nothing left" in res_fb["egress"])
    try:
        call_cloud("test", allow_cloud=False)
        cloud_blocked = False
    except PermissionError:
        cloud_blocked = True
    check("cloud blocked without double opt-in (flag + env + key)", cloud_blocked)
    st = ollama_status()
    check("ollama-status reports availability honestly (dict, not crash)", isinstance(st, dict) and "available" in st)
    # --- v1.0: trends, masters, dashboard ---
    from trends import fuse_trends, suggest_project_v1, CURATED_SEED
    from app import match_masters
    from dashboard import render
    trends, notes = fuse_trends(github_fn=lambda: (_ for _ in ()).throw(RuntimeError("offline test")),
                                hn_fn=lambda: (_ for _ in ()).throw(RuntimeError("offline test")))
    check("trend fusion falls back to labelled seed when live sources fail",
          trends == CURATED_SEED and any("curated seed" in n for n in notes))
    trends2, _ = fuse_trends(github_fn=lambda: [{"topic": "Test Repo: cool Python tool", "source": "github-search", "url": "https://example.com", "score": "100 stars"}],
                             hn_fn=lambda: [])
    check("trend fusion uses live items when available", trends2[0]["source"] == "github-search")
    proj2 = suggest_project_v1(pr, ["Kubernetes"], trends2)
    check("v1 project suggestion cites its trend source", "github-search" in proj2["scaffold"][-1] and proj2["gap"] == "Kubernetes")
    political = [{"topic": "Meta Ignores Brazilian Court Order to End Bolsonaro Favoritism", "source": "hacker-news", "url": "https://example.com", "score": "282 points"}]
    proj3 = suggest_project_v1(pr, ["Kubernetes"], political)
    check("non-tech HN story is NOT used as a project idea (falls back to curated seed)",
          proj3["trend"]["source"] == "curated-seed")
    matches, note = match_masters(field="computer science", country="Germany")
    check("masters match returns Germany CS search starters", len(matches) >= 1 and matches[0]["country"] == "Germany")
    check("masters note warns these are search starters, not verified offers", "NOT verified" in note)
    html_out = render(con)
    check("dashboard renders profiles and applications without crashing",
          "Personal AI Career Platform" in html_out and "Test Engineer" in html_out)
    print("All MVP v1.0 tests passed.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
