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

def fetch_github_trending(limit=10, days=30, query=""):
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    q = f"{query} created:>{since}" if query else f"created:>{since}"
    data = _get_json(f"https://api.github.com/search/repositories?q={urllib.parse.quote(q)}&sort=stars&order=desc&per_page={limit}", headers)
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

# ---------------- v1.1: full live fusion ----------------
# Added without breaking v1.0: fuse_trends() and suggest_project_v1() above
# keep their old behaviour. fuse_all_trends() is the new, full fusion.

import re
import urllib.parse
import xml.etree.ElementTree as ET

def _get_text(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read().decode("utf-8")

def parse_arxiv_xml(xml_text):
    """Parse arXiv Atom XML (no network). Returns trend dicts."""
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(xml_text)
    out = []
    for entry in root.findall("atom:entry", ns):
        title = (entry.findtext("atom:title", default="", namespaces=ns) or "").strip()
        title = re.sub(r"\s+", " ", title)
        link = ""
        for ln in entry.findall("atom:link", ns):
            if ln.get("title") == "pdf" or ln.get("rel") == "alternate":
                link = ln.get("href", "")
                if ln.get("title") == "pdf":
                    break
        published = entry.findtext("atom:published", default="", namespaces=ns) or ""
        if title:
            out.append({"topic": title, "source": "arxiv", "url": link, "score": f"published {published[:10]}"})
    return out

def fetch_arxiv(query="artificial intelligence", limit=5):
    q = urllib.parse.quote(query)
    xml_text = _get_text(f"https://export.arxiv.org/api/query?search_query=all:{q}&sortBy=submittedDate&sortOrder=descending&max_results={limit}")
    return parse_arxiv_xml(xml_text)

def parse_stackoverflow(data):
    out = []
    for item in data.get("items", []):
        out.append({"topic": item.get("title", ""), "source": "stackoverflow",
                    "url": item.get("link", ""), "score": f"{item.get('score', 0)} votes"})
    return out

def fetch_stackoverflow(tag="python", limit=5):
    data = _get_json(f"https://api.stackexchange.com/2.3/questions?order=desc&sort=votes&tagged={urllib.parse.quote(tag)}&site=stackoverflow&pagesize={limit}&filter=default")
    return parse_stackoverflow(data)

def fetch_github_issues(query="python", limit=5):
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    q = urllib.parse.quote(f'label:"good first issue" {query}')
    data = _get_json(f"https://api.github.com/search/issues?q={q}&per_page={limit}", headers)
    out = []
    for item in data.get("items", []):
        out.append({"topic": item.get("title", ""), "source": "github-issues",
                    "url": item.get("html_url", ""), "score": f"repo {item.get('repository_url','').split('/')[-1]}"})
    return out

def _norm_topic(topic):
    return re.sub(r"[^a-z0-9 ]+", "", topic.lower())[:80].strip()

def fuse_all_trends(query="", sources=None, github_fn=None, hn_fn=None, arxiv_fn=None, so_fn=None, issues_fn=None):
    """Fuse all live sources. sources: subset of github, hacker-news, arxiv, stackoverflow, github-issues.
    Returns (trends, notes). Deduplicated by normalised topic. Falls back to labelled seed if nothing live."""
    wanted = set(sources) if sources else {"github", "hacker-news", "arxiv", "stackoverflow", "github-issues"}
    calls = []
    if "github" in wanted:
        calls.append(("github", github_fn or (lambda: fetch_github_trending(query=query) if query else fetch_github_trending())))
    if "hacker-news" in wanted:
        calls.append(("hacker-news", hn_fn or fetch_hn_velocity))
    if "arxiv" in wanted:
        calls.append(("arxiv", arxiv_fn or (lambda: fetch_arxiv(query or "artificial intelligence"))))
    if "stackoverflow" in wanted:
        calls.append(("stackoverflow", so_fn or (lambda: fetch_stackoverflow(tag=re.sub(r"[^a-z0-9-]+", "", (query.split()[0] if query else "python").lower()) or "python"))))
    if "github-issues" in wanted:
        calls.append(("github-issues", issues_fn or (lambda: fetch_github_issues(query or "python"))))
    trends, notes, seen = [], [], set()
    for name, fn in calls:
        try:
            got = fn()
            added = 0
            for t in got:
                key = _norm_topic(t["topic"])
                if key and key not in seen:
                    seen.add(key)
                    trends.append(t)
                    added += 1
            notes.append(f"{name}: {added} new items (live, {len(got)} fetched)")
        except Exception as e:
            notes.append(f"{name}: live fetch failed ({e}) - not used")
    if not trends:
        trends = list(CURATED_SEED)
        notes.append("All live sources failed - using labelled curated seed only. Check network / rate limits and retry.")
    return trends, notes

def _relevance(topic, gap, query=""):
    t = topic.lower()
    score = 0
    if gap and gap.lower() in t:
        score += 10
    if query and query.lower() in t:
        score += 5
    score += sum(1 for w in TECH_WORDS if w in t)
    return score

def _signal_strength(trend):
    m = re.search(r"(\d+(?:\.\d+)?)", trend.get("score", "") or "")
    try:
        return float(m.group(1)) if m else 0.0
    except ValueError:
        return 0.0

def suggest_project(profile, target_skills, trends, query=""):
    """v1.1 suggestion: best trend by gap/query relevance, then signal strength,
    plus up to 3 supporting trends from different sources."""
    gaps = [s for s in target_skills if s not in profile["data"].get("skills", [])]
    gap = gaps[0] if gaps else "a skill from your target roles"
    ranked = sorted((trends or []), key=lambda t: (_relevance(t["topic"], gap, query), _signal_strength(t)), reverse=True)
    top = ranked[0] if ranked and _relevance(ranked[0]["topic"], gap, query) > 0 else CURATED_SEED[0]
    supporting = []
    seen_sources = {top["source"]}
    for t in ranked:
        if t is top:
            continue
        if t["source"] not in seen_sources and _relevance(t["topic"], gap, query) > 0:
            supporting.append(t)
            seen_sources.add(t["source"])
        if len(supporting) >= 3:
            break
    scaffold = ["README: problem, what it does, how to run it", "Milestone 1: smallest working version",
                "Milestone 2: add tests and a demo", "Milestone 3: 'what I learned' artefact + CV bullet"]
    for s in supporting:
        scaffold.append(f"Supporting signal ({s['source']}): {s['topic']} - {s.get('url','')} ({s.get('score','')})")
    scaffold.append(f"Trend source: {top['source']} - {top.get('url','')} ({top.get('score','')})")
    return {"gap": gap, "trend": top, "supporting": supporting,
            "title": f"{top['topic']} - learning {gap}", "scaffold": scaffold}
