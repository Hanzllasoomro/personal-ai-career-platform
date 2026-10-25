"""Ollama local-first CV rewrite mode (MVP v0.2).

Local by default. Cloud is a double gate: --allow-cloud on the command line
AND CAREER_ALLOW_CLOUD=1 in the environment AND a cloud key/base URL set.
If either gate is missing, no cloud call is made, ever.

Even after a rewrite, the same approval gate applies: the rewritten CV is
saved with its SHA-256 hash, it is NOT approved until the user approves
that exact hash, and it is never submitted by the platform.

Fact-check here is a heuristic safety net, not proof. It catches the
common hallucination shapes (new years, new numbers, new employers,
new skills). The human approval of the exact text is still required.
"""
import difflib, json, os, re, urllib.request
from app import tailor_cv, templates

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")

def ollama_status(url=OLLAMA_URL):
    try:
        req = urllib.request.Request(url + "/api/tags", headers={"User-Agent": "PersonalCareerPlatform-MVP/0.2"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = [m.get("name") for m in data.get("models", [])]
        return {"available": True, "models": models, "url": url, "error": ""}
    except Exception as e:
        return {"available": False, "models": [], "url": url, "error": str(e)}

def build_prompt(profile, job, reorder_text):
    settings = profile.get("settings", {}) or {}
    tone = settings.get("tone", "professional")
    return (
        "Rewrite the CV below for the job described. Rules, in order:\n"
        "1. Do NOT invent anything: no new employers, job titles, dates, qualifications, skills, or numbers.\n"
        "2. You may only reword the existing bullets and skills, in a " + tone + " tone, to match the job description.\n"
        "3. Keep the same sections and single-column plain-text format. Output ONLY the CV text, no commentary.\n\n"
        f"JOB: {job.get('title','')} at {job.get('company','')}\n{job.get('description','')}\n\n"
        f"MASTER PROFILE (facts you may use, nothing else):\n{json.dumps(profile['data'], indent=2)}\n\n"
        f"REORDER-ONLY CV TO REWRITE:\n{reorder_text}"
    )

def call_ollama(prompt, model=None, url=OLLAMA_URL, timeout=180):
    payload = json.dumps({"model": model or DEFAULT_MODEL, "prompt": prompt, "stream": False,
                          "options": {"temperature": 0.2}}).encode()
    req = urllib.request.Request(url + "/api/generate", data=payload,
                                 headers={"Content-Type": "application/json", "User-Agent": "PersonalCareerPlatform-MVP/0.2"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))["response"]

def call_cloud(prompt, model=None, allow_cloud=False):
    """Double-gated cloud call. Returns text, or raises PermissionError without calling anything."""
    base = os.environ.get("CAREER_CLOUD_BASE_URL", "")
    key = os.environ.get("CAREER_CLOUD_API_KEY", "")
    if not allow_cloud or os.environ.get("CAREER_ALLOW_CLOUD") != "1" or not base or not key:
        raise PermissionError(
            "Cloud blocked: pass --allow-cloud AND set CAREER_ALLOW_CLOUD=1 AND "
            "CAREER_CLOUD_BASE_URL + CAREER_CLOUD_API_KEY. Nothing was sent.")
    payload = json.dumps({"model": model or os.environ.get("CAREER_CLOUD_MODEL", "gpt-4o-mini"),
                          "messages": [{"role": "system", "content": "You rewrite CVs without inventing any fact."},
                                       {"role": "user", "content": prompt}],
                          "temperature": 0.2}).encode()
    req = urllib.request.Request(base.rstrip("/") + "/chat/completions", data=payload,
                                 headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=180) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]

def fact_check(profile, rewritten, job):
    """Return a list of flags. Empty = no heuristic violation found."""
    flags = []
    master = json.dumps(profile["data"])
    master_lower = master.lower()
    # 1. New numbers / years: every number in the rewrite must appear in the master profile.
    master_numbers = set(re.findall(r"\d+(?:\.\d+)?%?", master))
    for n in sorted(set(re.findall(r"\d+(?:\.\d+)?%?", rewritten))):
        if n not in master_numbers:
            flags.append(f"New number not in master profile: {n}")
    # 2. New skills in the SKILLS section.
    m = re.search(r"SKILLS\s*\n(.+?)(?:\n\s*\n|\nEXPERIENCE)", rewritten, re.S)
    if m:
        listed = [s.strip().lower() for s in m.group(1).split(",") if s.strip()]
        known = [s.lower() for s in profile["data"].get("skills", [])]
        for s in listed:
            if s not in known:
                flags.append(f"New skill not in master profile: {s}")
    # 3. New employer-like names after 'at / for / with' (heuristic).
    known_skills = [s.lower() for s in profile["data"].get("skills", [])]
    job_company = (job.get("company") or "").lower()
    for cand in re.findall(r"\b(?:at|for|with)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)?)", rewritten):
        cl = cand.lower()
        if cl not in master_lower and cl != job_company and cl not in known_skills:
            flags.append(f"Possible new employer not in master profile: {cand}")
    return flags

def rewrite_cv(profile, job, llm_fn=None, allow_cloud=False, model=None):
    """Return dict with mode, text, hash, diff, flags, egress label.
    Modes: 'ollama', 'cloud', 'rejected-fallback-reorder', 'fallback-reorder' (no LLM available)."""
    base_text, _diff, base_hash = tailor_cv(profile, job)
    prompt = build_prompt(profile, job, base_text)
    if llm_fn is not None:
        rewritten = llm_fn(prompt)
        mode, egress = "custom-llm (test/injectable)", "Injected LLM function (test path only - no network claim)."
    elif allow_cloud:
        rewritten = call_cloud(prompt, model=model, allow_cloud=True)
        mode = "cloud"
        egress = (f"Egress (opt-in only): profile skills/experience + job description sent to "
                  f"{os.environ.get('CAREER_CLOUD_BASE_URL')} - you passed --allow-cloud and CAREER_ALLOW_CLOUD=1.")
    else:
        status = ollama_status()
        if not status["available"]:
            return {"mode": "fallback-reorder", "text": base_text, "hash": base_hash,
                    "diff": "No LLM used: Ollama not reachable at " + OLLAMA_URL + " - returned reorder-only CV.",
                    "flags": [], "egress": "Nothing left this machine: no LLM call was made.",
                    "note": "To enable rewrite: install Ollama, run 'ollama serve', then 'ollama pull " + (model or DEFAULT_MODEL) + "', and retry."}
        rewritten = call_ollama(prompt, model=model)
        mode, egress = "ollama", "Nothing left this machine: Ollama on localhost only."
    flags = fact_check(profile, rewritten, job)
    if flags:
        return {"mode": "rejected-fallback-reorder", "text": base_text, "hash": base_hash,
                "diff": "Rewrite REJECTED by fact-check - returned reorder-only CV instead.",
                "flags": flags, "egress": egress, "llm_text": rewritten}
    diff = "\n".join(difflib.unified_diff(base_text.splitlines(), rewritten.splitlines(), lineterm=""))
    import hashlib
    return {"mode": mode, "text": rewritten.strip() + "\n", "hash": hashlib.sha256(rewritten.strip().encode()).hexdigest(),
            "diff": diff, "flags": [], "egress": egress}
