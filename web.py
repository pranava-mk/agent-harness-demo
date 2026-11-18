"""
web.py — THE CHAT INTERFACE (web)
=================================

A browser chat UI for the agent. Same thin-interface idea as a CLI REPL, just
rendered in HTML: you type, the agent runs its full loop (RAG + tools + LLM),
and the page shows the answer PLUS what the agent did under the hood (which
knowledge it retrieved, which tools it called) — so a learner can *see* the
harness working.

Zero dependencies — pure Python standard library http.server. All the
intelligence still lives in agent/; this file only moves bytes.

Run:  python web.py            → http://localhost:8000
      PORT=9000 python web.py
"""
import base64
import json
import os
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from agent import Agent
from agent.pdf_extract import extract_text as extract_pdf_text

PORT = int(os.environ.get("PORT", "8000"))


def _port_is_free(port, host="127.0.0.1"):
    """True if a server can actually bind to (host, port) right now."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        s.bind((host, port))
        return True
    except OSError:
        return False
    finally:
        s.close()


def _pick_port(preferred, host="127.0.0.1", tries=50):
    """Use PORT if free; otherwise scan upward for the next open one.
    If PORT came from the user explicitly (env var), tell them it was busy."""
    if _port_is_free(preferred, host):
        return preferred, False
    for candidate in range(preferred + 1, preferred + 1 + tries):
        if _port_is_free(candidate, host):
            return candidate, True
    # last resort: let the OS assign any free ephemeral port
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind((host, 0))
    candidate = s.getsockname()[1]
    s.close()
    return candidate, True

# One agent instance, guarded by a lock (the LLM call isn't reentrant).
_agent = Agent()
_lock = threading.Lock()

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Harness — Chat</title>
<style>
  :root{
    --bg:#0b0b12; --surface:#14141f; --line:#26263a; --text:#f2f2f7;
    --muted:#9a9ab2; --accent:#7c6cff; --accent2:#ff6ec7;
    --rag:#4aa3ff; --tool:#ffb84a;
  }
  *{box-sizing:border-box}
  body{margin:0;background:
      radial-gradient(900px 500px at 85% -10%,rgba(124,108,255,.16),transparent 60%),
      radial-gradient(700px 420px at 0% 110%,rgba(255,110,199,.10),transparent 60%),
      var(--bg);
    color:var(--text);font-family:'Space Grotesk',system-ui,-apple-system,sans-serif;
    min-height:100vh;display:flex;flex-direction:column}
  header{padding:18px 22px;border-bottom:1px solid var(--line);display:flex;
    align-items:center;gap:12px;backdrop-filter:blur(8px)}
  header .dot{width:10px;height:10px;border-radius:50%;
    background:linear-gradient(135deg,var(--accent),var(--accent2));
    box-shadow:0 0 12px var(--accent)}
  header h1{font-size:16px;margin:0;font-weight:700;letter-spacing:.01em}
  header .pieces{margin-left:auto;font-family:ui-monospace,monospace;font-size:12px;color:var(--muted)}
  header .pieces b{color:var(--text)}
  #log{flex:1;overflow-y:auto;padding:26px 0;display:flex;flex-direction:column;gap:18px}
  .wrap{width:min(760px,92vw);margin:0 auto;width:100%}
  .msg{display:flex;flex-direction:column;gap:6px}
  .msg .who{font-size:12px;color:var(--muted);font-family:ui-monospace,monospace;letter-spacing:.04em}
  .bubble{padding:14px 18px;border-radius:16px;line-height:1.55;font-size:15.5px;
    max-width:86%;white-space:pre-wrap;overflow-wrap:anywhere}
  .you .bubble{align-self:flex-end;background:linear-gradient(135deg,var(--accent),var(--accent2));color:#0b0b12;font-weight:500}
  .you{align-items:flex-end}
  .bot .bubble{align-self:flex-start;background:var(--surface);border:1px solid var(--line)}
  /* the "what the agent did" trace */
  .trace{align-self:flex-start;display:flex;flex-direction:column;gap:6px;margin:2px 0 2px 2px}
  .step{font-family:ui-monospace,monospace;font-size:12.5px;color:var(--muted);
    display:flex;align-items:center;gap:8px;opacity:0;transform:translateY(4px);
    animation:rise .35s ease forwards}
  .step .tag{padding:2px 8px;border-radius:999px;font-weight:600;font-size:11px}
  .step.rag  .tag{background:rgba(74,163,255,.15);color:var(--rag);border:1px solid rgba(74,163,255,.4)}
  .step.tool .tag{background:rgba(255,184,74,.15);color:var(--tool);border:1px solid rgba(255,184,74,.4)}
  .step.score .tag{background:rgba(74,163,255,.08);color:var(--rag);border:1px solid rgba(74,163,255,.25)}
  .step.score.fail{opacity:.55}
  .step.doc   .tag{background:rgba(124,108,255,.15);color:var(--accent);border:1px solid rgba(124,108,255,.4)}
  @keyframes rise{to{opacity:1;transform:translateY(0)}}
  .typing{display:inline-flex;gap:4px;padding:14px 18px}
  .typing i{width:7px;height:7px;border-radius:50%;background:var(--muted);animation:blink 1.2s infinite}
  .typing i:nth-child(2){animation-delay:.2s}.typing i:nth-child(3){animation-delay:.4s}
  @keyframes blink{0%,60%,100%{opacity:.25}30%{opacity:1}}
  form{border-top:1px solid var(--line);padding:16px 0;background:rgba(11,11,18,.6);backdrop-filter:blur(8px)}
  .inrow{width:min(760px,92vw);margin:0 auto;display:flex;gap:10px}
  #q{flex:1;background:var(--surface);border:1px solid var(--line);border-radius:14px;
    color:var(--text);padding:14px 16px;font-size:15px;font-family:inherit;outline:none}
  #q:focus{border-color:var(--accent)}
  button{border:none;border-radius:14px;padding:0 20px;font-weight:700;cursor:pointer;
    color:#0b0b12;background:linear-gradient(135deg,var(--accent),var(--accent2));font-size:15px}
  button:disabled{opacity:.5;cursor:default}
  .hint{width:min(760px,92vw);margin:10px auto 0;font-size:12px;color:var(--muted)}
  .hint b{color:var(--text)}
  .chip{display:inline-block;margin:0 6px 6px 0;padding:5px 11px;border:1px solid var(--line);
    border-radius:999px;font-size:12.5px;color:var(--muted);cursor:pointer;background:var(--surface)}
  .chip:hover{border-color:var(--accent);color:var(--text)}
  .upload{display:flex;align-items:center;gap:8px;margin-left:10px}
  .upload label{display:flex;align-items:center;gap:6px;padding:7px 13px;border-radius:999px;
    border:1px solid var(--line);background:var(--surface);color:var(--muted);font-size:12.5px;
    cursor:pointer;white-space:nowrap}
  .upload label:hover{border-color:var(--accent);color:var(--text)}
  .upload input[type=file]{display:none}
  .docpill{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;
    background:rgba(124,108,255,.1);border:1px solid rgba(124,108,255,.35);color:var(--accent);
    font-size:11.5px;font-family:ui-monospace,monospace}
  .docpill .x{cursor:pointer;opacity:.7}.docpill .x:hover{opacity:1}
</style>
</head>
<body>
<header>
  <span class="dot"></span>
  <h1>Agent Harness — live chat</h1>
  <span class="pieces"><b>🧠 LLM</b> + <b>📚 RAG</b> + <b>🔧 Tools</b> + <b>🔁 Loop</b></span>
  <div class="upload">
    <label for="pdf"><span>📄</span><span id="uploadLabel">Upload a PDF</span></label>
    <input id="pdf" type="file" accept="application/pdf">
  </div>
</header>

<div id="docbar" class="wrap" style="padding-top:12px;display:none"></div>

<div id="log"><div class="wrap" id="logwrap">
  <div class="msg bot"><span class="who">agent</span>
    <div class="bubble">Hi — I'm a tiny but complete agent: a local LLM, a knowledge base (RAG), and some tools, wired in a loop. Ask me something and watch what I do under the hood. Upload a PDF above and I'll chunk it, embed it, and let you ask questions about it — RAG, live.</div>
  </div>
  <div class="wrap">
    <div class="hint">Try:
      <span class="chip" onclick="ask(this.textContent)">what is an agent harness?</span>
      <span class="chip" onclick="ask(this.textContent)">what is 1287 * 43?</span>
      <span class="chip" onclick="ask(this.textContent)">what time is it?</span>
    </div>
  </div>
</div></div>

<form id="f" onsubmit="return send()">
  <div class="inrow">
    <input id="q" autocomplete="off" placeholder="Ask the agent…" autofocus>
    <button id="b" type="submit">Send</button>
  </div>
</form>

<script>
const log = document.getElementById('log');
const logwrap = document.getElementById('logwrap');
const q = document.getElementById('q');
const b = document.getElementById('b');

function el(cls, html){ const d=document.createElement('div'); d.className=cls; if(html)d.innerHTML=html; return d; }
function scroll(){ log.scrollTop = log.scrollHeight; }
function esc(s){ return s.replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function bubble(who, text){
  const m = el('msg '+(who==='you'?'you':'bot'));
  m.appendChild(el('who', who==='you'?'you':'agent'));
  m.appendChild(el('bubble', esc(text)));
  logwrap.appendChild(m); scroll(); return m;
}

function ask(text){ q.value = text; send(); }

// ── PDF upload: parse → chunk → embed, with every step shown live ──────────
const pdfInput = document.getElementById('pdf');
const uploadLabel = document.getElementById('uploadLabel');
const docbar = document.getElementById('docbar');
const docs = {}; // source name -> pill element

function renderDocPill(name, nChunks){
  if(docs[name]) docs[name].remove();
  const pill = el('docpill', `<span>📄 ${esc(name)} — ${nChunks} chunk(s) indexed</span><span class="x" data-name="${esc(name)}">✕</span>`);
  pill.querySelector('.x').onclick = () => removeDoc(name);
  docbar.appendChild(pill);
  docs[name] = pill;
  docbar.style.display = 'block';
}

async function removeDoc(name){
  await fetch('/api/document', {method:'DELETE', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({source: name})});
  if(docs[name]){ docs[name].remove(); delete docs[name]; }
  if(!Object.keys(docs).length) docbar.style.display = 'none';
}

function renderTrace(trace){
  if(!trace || !trace.length) return;
  const t = el('trace');
  trace.forEach((s,i)=>{
    let line, cls = s.kind;
    if(s.kind==='doc_parsed') line = `<span class="tag">📄 PARSE</span> extracted <b>${s.n_words}</b> word(s) from <b>${esc(s.source)}</b>`;
    else if(s.kind==='doc_chunk') line = `<span class="tag">✂️ CHUNK</span> split <b>${esc(s.source)}</b> (${s.n_words} words) into <b>${s.n_chunks}</b> chunk(s)`;
    else if(s.kind==='doc_embed') line = `<span class="tag">🧮 EMBED</span> chunk ${s.chunk_index+1}/${s.n_chunks} → vector — "<i>${esc(s.preview)}…</i>"`;
    else if(s.kind==='query_embed') line = `<span class="tag">🧮 EMBED</span> query → ${s.dims}-dim vector: "<i>${esc(s.question)}</i>"`;
    else if(s.kind==='score'){
      cls += s.passed ? ' pass' : ' fail';
      line = `<span class="tag">📐 COMPARE</span> cosine(query, <b>${esc(s.source)}</b> "${esc(s.preview)}…") = <b>${s.score}</b> ${s.passed?`≥ ${s.threshold} ✓ used`:`< ${s.threshold} ✗ skipped`}`;
    }
    else if(s.kind==='rag') line = `<span class="tag">📚 RAG</span> retrieved ${s.chunks} knowledge chunk(s) → added to context`;
    else if(s.kind==='tool') line = `<span class="tag">🔧 TOOL</span> called <b>${esc(s.name)}</b>(${esc(JSON.stringify(s.arguments))}) → ${esc(String(s.result))}`;
    else return;
    const step = el('step '+cls, line);
    step.style.animationDelay = (i*0.08)+'s';
    t.appendChild(step);
  });
  logwrap.appendChild(t); scroll();
}

pdfInput.addEventListener('change', async () => {
  const file = pdfInput.files[0];
  if(!file) return;
  uploadLabel.textContent = 'Parsing…';
  pdfInput.disabled = true;
  bubble('you', `📄 uploaded ${file.name}`);
  try{
    const buf = await file.arrayBuffer();
    const b64 = btoa(new Uint8Array(buf).reduce((s,b)=>s+String.fromCharCode(b), ''));
    const r = await fetch('/api/upload', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({filename: file.name, data_b64: b64})});
    const data = await r.json();
    if(data.error){ bubble('bot', '⚠️ '+data.error); }
    else{
      renderTrace(data.trace);
      renderDocPill(data.source, data.n_chunks);
      bubble('bot', `Indexed **${data.source}** — ${data.n_words} words → ${data.n_chunks} chunks, embedded and searchable. Ask me something about it.`);
    }
  }catch(e){ bubble('bot', '⚠️ '+e); }
  uploadLabel.textContent = 'Upload a PDF';
  pdfInput.value = '';
  pdfInput.disabled = false;
});

async function send(){
  const text = q.value.trim();
  if(!text) return false;
  bubble('you', text);
  q.value=''; b.disabled=true; q.disabled=true;

  // typing indicator
  const think = el('msg bot');
  think.appendChild(el('typing','<i></i><i></i><i></i>'));
  logwrap.appendChild(think); scroll();

  try{
    const r = await fetch('/api/chat', {method:'POST', headers:{'Content-Type':'application/json'},
      body: JSON.stringify({message:text})});
    const data = await r.json();
    think.remove();

    // show the trace (what the agent did) BEFORE the answer
    renderTrace(data.trace);
    bubble('bot', data.answer || '(no answer)');
  }catch(e){
    think.remove();
    bubble('bot', '⚠️ '+e);
  }
  b.disabled=false; q.disabled=false; q.focus();
  return false;
}
document.getElementById('f').addEventListener('submit', e=>e.preventDefault());
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):  # keep the console clean
        pass

    def _send(self, code, body, ctype="application/json"):
        data = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        else:
            self._send(404, "not found", "text/plain")

    def do_POST(self):
        if self.path == "/api/chat":
            return self._handle_chat()
        if self.path == "/api/upload":
            return self._handle_upload()
        return self._send(404, '{"error":"not found"}')

    def do_DELETE(self):
        if self.path == "/api/document":
            return self._handle_delete_document()
        return self._send(404, '{"error":"not found"}')

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length) or b"{}")

    def _handle_chat(self):
        try:
            payload = self._read_json()
            msg = (payload.get("message") or "").strip()
            if not msg:
                return self._send(400, '{"error":"empty message"}')
            trace = []
            with _lock:
                answer = _agent.ask(msg, trace=trace)
            self._send(200, json.dumps({"answer": answer, "trace": trace}))
        except Exception as e:  # never 500 silently
            self._send(200, json.dumps({"answer": f"⚠️ error: {e}", "trace": []}))

    def _handle_upload(self):
        """PDF upload -> parse -> chunk -> embed -> index, with every step
        of that pipeline recorded in `trace` so the UI can show it live
        (this is the point of the demo: make RAG's internals visible)."""
        try:
            payload = self._read_json()
            filename = (payload.get("filename") or "upload.pdf").strip()
            data_b64 = payload.get("data_b64") or ""
            if not data_b64:
                return self._send(400, json.dumps({"error": "no file data received"}))

            pdf_bytes = base64.b64decode(data_b64)
            trace = []

            text = extract_pdf_text(pdf_bytes)
            n_words = len(text.split())
            trace.append({"kind": "doc_parsed", "source": filename, "n_words": n_words})

            if not text.strip():
                return self._send(200, json.dumps({
                    "error": ("Couldn't extract any text from this PDF — it may be "
                              "scanned/image-only (no text layer), which this demo's "
                              "stdlib-only parser doesn't OCR."),
                    "trace": trace,
                }))

            with _lock:
                if _agent.knowledge is None:
                    return self._send(400, json.dumps({"error": "RAG is disabled on this agent"}))
                _agent.knowledge.remove_document(filename)  # replace, don't duplicate
                added = _agent.knowledge.add_document(filename, text, trace_steps=trace)

            self._send(200, json.dumps({
                "source": filename,
                "n_words": n_words,
                "n_chunks": len(added),
                "trace": trace,
            }))
        except Exception as e:
            self._send(200, json.dumps({"error": f"upload failed: {e}"}))

    def _handle_delete_document(self):
        try:
            payload = self._read_json()
            source = (payload.get("source") or "").strip()
            if not source:
                return self._send(400, json.dumps({"error": "no source given"}))
            with _lock:
                removed = _agent.knowledge.remove_document(source) if _agent.knowledge else 0
            self._send(200, json.dumps({"removed_chunks": removed}))
        except Exception as e:
            self._send(200, json.dumps({"error": f"delete failed: {e}"}))


def main():
    port, fell_back = _pick_port(PORT)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://localhost:{port}"
    if fell_back:
        print(f"\n  ⚠️  Port {PORT} was busy — using {port} instead.")
    print(f"\n  🌐  Agent Harness web chat → {url}")
    print("  (Ctrl-C to stop)\n")
    try:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n  bye 👋\n")
        server.shutdown()


if __name__ == "__main__":
    main()
