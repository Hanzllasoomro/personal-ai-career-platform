"""Live trend fusion for Project Forge (v1.0).

Sources, in order, with labels - never presented as a single opaque trend:
- GitHub Search API: repos created in the last 30 days, sorted by stars.
  Unauthenticated limit is 60 requests/hour; set GITHUB_TOKEN to raise it.
- Hacker News Firebase API: top stories, ranked by points/hour (velocity),
  not raw score, so new fast-rising items surface.
If both live sources fail (offline, rate-limited, API error), the function
returns the curated seed and says so explicitly. No trend is ever invented.
"""
import json, os, time, urllib.request
from datetime import datetime, timedelta, timezone

USER_AGENT = "PersonalCareerPlatform/1.0 (local, private)"
CURATED_SEED = [
    {"topic": "Local-first LLM agent evaluation and cost tracking", "source": "curated-seed", "url": "", "score": ""},
    {"topic": "Evidence-linked debugging assistant for small codebases", "source": "curated-seed", "url": "", "score": ""},
    {"topic": "Accessible, offline-first learning planner for teachers", "source": "curated-seed", "url": "", "score": ""},
    {"topic": "Personal finance dashboard with explainable budgeting", "source": "curated-seed", "url": "", "score": ""},
]

def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_github_trending(limit=10, days=30):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    data = _get_json(f"https://api.github.com/search/repositories?q=created:>{since}&sort=stars&order=desc&per_page={limit}", headers)
    out = []
    for r in data.get("items", []):
        out.append({"topic": f"{r.get('full_name')}: {r.get('description') or ''}".strip(),
                    "source": "github-search", "url": r.get("html_url", ""), "score": f"{r.get('stargazers_count')} stars"})
    return out

def fetch_hn_velocity(limit=10):
    ids = _get_json("https://hacker-news.firebaseio.com/v0/topstories.json")[:50]
    now = time.time()
    items = []
    for i in ids:
        try:
            item = _get_json(f"https://hacker-news.firebaseio.com/v0/item/{i}.json")
        except Exception:
            continue
        if not item or item.get("type") != "story":
            continue
        hours = max(1.0, (now - item.get("time", now)) / 3600.0)
        items.append({"topic": item.get("title", ""), "source": "hacker-news",
                      "url": item.get("url", "") or f"https://news.ycombinator.com/item?id={i}",
                      "score": f"{item.get('score', 0)} points, {item.get('score', 0) / hours:.1f} points/hour"})
        if len(items) >= limit:
            break
    items.sort(key=lambda x: float(x["score"].split(",")[1].split()[0]) if "," in x["score"] else 0, reverse=True)
    return items

def fuse_trends(github_fn=None, hn_fn=None):
    """Return (trends, notes). Trends are labelled by source. Fallback is labelled, never silent."""
    trends, notes = [], []
    for name, fn in (("github", github_fn or fetch_github_trending), ("hacker-news", hn_fn or fetch_hn_velocity)):
        try:
            got = fn()
            trends.extend(got)
            notes.append(f"{name}: {len(got)} items (live)")
        except Exception as e:
            notes.append(f"{name}: live fetch failed ({e}) - not used")
    if not trends:
        trends = list(CURATED_SEED)
        notes.append("Both live sources failed - using labelled curated seed only. Check network / rate limits and retry.")
    return trends, notes

TECH_WORDS = ("ai", "llm", "python", "software", "code", "developer", "data", "security", "database", "cloud", "open source", "programming", "machine learning", "web", "app")

def suggest_project_v1(profile, target_skills, trends):
    gaps = [s for s in target_skills if s not in profile["data"].get("skills", [])]
    gap = gaps[0] if gaps else "a skill from your target roles"
    # Filter: a Hacker News top story about politics is not a tech project idea.
    # Prefer a trend whose topic mentions the gap or a tech word; otherwise use the curated seed.
    top = None
    for t in (trends or []):
        topic = t["topic"].lower()
        if gap.lower() in topic or any(w in topic for w in TECH_WORDS):
            top = t
            break
    if top is None:
        top = CURATED_SEED[0]
    return {"gap": gap, "trend": top,
            "title": f"{top['topic']} - learning {gap}",
            "scaffold": ["README: problem, what it does, how to run it", "Milestone 1: smallest working version",
                         "Milestone 2: add tests and a demo", "Milestone 3: 'what I learned' artefact + CV bullet",
                         f"Trend source: {top['source']} - {top.get('url','')} ({top.get('score','')})"]}
