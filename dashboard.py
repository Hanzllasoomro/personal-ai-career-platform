"""Localhost dashboard (v1.0). Read + approve only. Binds 127.0.0.1 only.
No submission, no external call, no auth needed locally because it never
leaves this machine. Do NOT expose this port publicly.
Run: python3 app.py serve --port 8000   then open http://127.0.0.1:8000/
"""
import html, os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse
from app import init_db, approve_cv

def _esc(x):
    return html.escape(str(x))

def render(con):
    profiles = con.execute("SELECT id, name, profession FROM profiles ORDER BY id").fetchall()
    cvs = con.execute("SELECT id, profile_id, job_title, substr(hash,1,12), approved FROM cvs ORDER BY id DESC LIMIT 50").fetchall()
    apps = con.execute("SELECT job_title, company, substr(cv_hash,1,12), status, follow_up, outcome FROM applications ORDER BY id DESC LIMIT 50").fetchall()
    rows_p = "".join(f"<tr><td>{p[0]}</td><td>{_esc(p[1])}</td><td>{_esc(p[2])}</td></tr>" for p in profiles)
    rows_c = "".join(
        f"<tr><td>{c[0]}</td><td>{c[1]}</td><td>{_esc(c[2])}</td><td>{c[3]}...</td>"
        f"<td>{'APPROVED' if c[4] else 'draft - not approved'}</td>"
        f"<td>{'' if c[4] else f'<form method=post action=/approve><input type=hidden name=cv_id value={c[0]}><button>Approve exact CV</button></form>'}</td></tr>"
        for c in cvs)
    rows_a = "".join(f"<tr><td>{_esc(a[0])}</td><td>{_esc(a[1])}</td><td>{a[2]}...</td><td>{_esc(a[3])}</td><td>{_esc(a[4])}</td><td>{_esc(a[5])}</td></tr>" for a in apps)
    return f"""<!doctype html><html><head><meta charset=utf-8><title>Personal AI Career Platform - local dashboard</title>
<style>body{{font-family:system-ui,sans-serif;max-width:900px;margin:2em auto;padding:0 1em}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:6px;text-align:left}}</style></head>
<body><h1>Personal AI Career Platform</h1>
<p><strong>Local only (127.0.0.1).</strong> Draft &amp; approve only - this dashboard never submits an application.</p>
<h2>Profiles</h2><table><tr><th>ID</th><th>Name</th><th>Profession</th></tr>{rows_p or '<tr><td colspan=3>No profiles yet - run: python3 app.py demo</td></tr>'}</table>
<h2>CVs (approve the exact hash, nothing else)</h2><table><tr><th>ID</th><th>Profile</th><th>Job</th><th>Hash</th><th>Status</th><th>Action</th></tr>{rows_c or '<tr><td colspan=6>No CVs yet</td></tr>'}</table>
<h2>Applications (tracked to CV hash)</h2><table><tr><th>Job</th><th>Company</th><th>CV hash</th><th>Status</th><th>Follow-up</th><th>Outcome</th></tr>{rows_a or '<tr><td colspan=6>No applications yet</td></tr>'}</table>
<p>Use the CLI for jobs, scholarships, projects and learning plans - see README.md.</p></body></html>"""

def make_handler(db_path):
    class H(BaseHTTPRequestHandler):
        def do_GET(self):
            con = init_db(db_path)
            body = render(con).encode()
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            data = parse_qs(self.rfile.read(length).decode())
            if urlparse(self.path).path == "/approve" and "cv_id" in data:
                con = init_db(db_path)
                approve_cv(con, int(data["cv_id"][0]))
            self.send_response(303); self.send_header("Location", "/"); self.end_headers()
        def log_message(self, *a):
            pass
    return H

def serve(db_path, port=8000):
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(db_path))
    print(f"Dashboard at http://127.0.0.1:{port}/  (local only, Ctrl+C to stop)")
    server.serve_forever()
