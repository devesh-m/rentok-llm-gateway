from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text
from app.config import settings
from app.db import get_db

router = APIRouter(tags=["Health & Status"])


@router.get("/health", summary="Service Liveness Probe")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint verifying database connectivity and configuration."""
    db_status = "healthy"
    try:
        await db.execute(text("SELECT 1"))
    except Exception as exc:
        db_status = f"unhealthy: {str(exc)}"

    return {
        "status": "healthy" if db_status == "healthy" else "degraded",
        "service": settings.APP_NAME,
        "version": settings.VERSION,
        "database": db_status,
        "providers": {
            "groq_configured": bool(settings.GROQ_API_KEY),
            "gemini_configured": bool(settings.GEMINI_API_KEY),
            "mock_fallback_enabled": settings.ENABLE_MOCK_FALLBACK,
        },
    }


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>RentOk Minimal LLM Gateway — Console</title>
  <style>
    :root {
      --bg: #0d1117;
      --panel: #161b22;
      --border: #30363d;
      --text: #e6edf3;
      --muted: #8b949e;
      --accent: #2f81f7;
      --green: #3fb950;
      --red: #f85149;
      --yellow: #d29922;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
      background: var(--bg);
      color: var(--text);
      padding: 20px;
      line-height: 1.5;
    }
    .container { max-width: 1250px; margin: 0 auto; }
    header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding-bottom: 16px;
      margin-bottom: 20px;
      border-bottom: 1px solid var(--border);
    }
    h1 { font-size: 1.35rem; font-weight: 600; }
    .subtitle { color: var(--muted); font-size: 0.85rem; }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      background: rgba(63, 185, 80, 0.15);
      color: var(--green);
      border: 1px solid rgba(63, 185, 80, 0.4);
      padding: 4px 10px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 600;
    }
    .grid {
      display: grid;
      grid-template-columns: 1fr 1.25fr;
      gap: 20px;
    }
    @media (max-width: 900px) { .grid { grid-template-columns: 1fr; } }
    .card {
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 18px;
    }
    .card h2 {
      font-size: 1rem;
      margin-bottom: 14px;
      color: var(--text);
      border-bottom: 1px solid var(--border);
      padding-bottom: 8px;
    }
    label {
      display: block;
      font-size: 0.8rem;
      color: var(--muted);
      margin-bottom: 5px;
      margin-top: 12px;
    }
    select, input, textarea {
      width: 100%;
      background: var(--bg);
      color: var(--text);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px 10px;
      font-size: 0.88rem;
      font-family: inherit;
    }
    textarea { min-height: 85px; resize: vertical; }
    .btn-row { display: flex; gap: 10px; margin-top: 14px; }
    button {
      cursor: pointer;
      background: var(--accent);
      color: #fff;
      border: none;
      border-radius: 6px;
      padding: 9px 16px;
      font-size: 0.88rem;
      font-weight: 600;
      transition: opacity 0.15s;
    }
    button:hover { opacity: 0.9; }
    button.secondary {
      background: transparent;
      border: 1px solid var(--border);
      color: var(--text);
    }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
      margin-bottom: 16px;
    }
    .stat-box {
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 10px;
    }
    .stat-label { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; }
    .stat-val { font-size: 1.05rem; font-weight: 700; margin-top: 4px; font-family: monospace; }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 4px;
      font-size: 0.75rem;
      font-weight: 700;
      font-family: monospace;
    }
    .badge-ok { background: rgba(63,185,80,0.2); color: var(--green); }
    .badge-err { background: rgba(248,81,73,0.2); color: var(--red); }
    .badge-hit { background: rgba(210,153,34,0.25); color: var(--yellow); }
    .badge-miss { background: rgba(139,148,158,0.2); color: var(--muted); }
    .response-box {
      margin-top: 16px;
      background: var(--bg);
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 12px;
      font-size: 0.88rem;
    }
    .meta-bar {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 10px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
      font-size: 0.78rem;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.8rem;
      margin-top: 8px;
    }
    th, td {
      text-align: left;
      padding: 7px 8px;
      border-bottom: 1px solid var(--border);
      font-family: monospace;
    }
    th { color: var(--muted); font-weight: 600; }
    a { color: var(--accent); text-decoration: none; }
    a:hover { text-decoration: underline; }
  </style>
</head>
<body>
  <div class="container">
    <header>
      <div>
        <h1>RentOk Minimal LLM Gateway</h1>
        <div class="subtitle">Virtual Keys &bull; Per-Key Budget Enforcement &bull; Groq + Gemini Fallback &bull; Smart Cache</div>
      </div>
      <div style="display:flex; align-items:center; gap:14px;">
        <a href="/docs" style="font-size:0.85rem;">Swagger API Docs (/docs) &rarr;</a>
        <span class="status-pill" id="health-pill">&#9679; Gateway Online</span>
      </div>
    </header>

    <div class="grid">
      <!-- LEFT PANEL: Request Playground -->
      <div class="card">
        <h2>1. Proxy Request Tester (POST /v1/chat/completions)</h2>

        <label for="key-select">Select Virtual API Key</label>
        <select id="key-select" onchange="onKeyChange()">
          <option value="gw-live-test">gw-live-test (Active Key — $1.00 Budget)</option>
          <option value="gw-live-exhausted">gw-live-exhausted (Exhausted Key — $0.00 Budget &rarr; Triggers HTTP 429)</option>
        </select>

        <label for="custom-key">Or Enter Key Value Directly</label>
        <input type="text" id="custom-key" value="gw-live-test" />

        <label for="model-select">Upstream Model</label>
        <select id="model-select">
          <option value="openai/gpt-oss-20b">openai/gpt-oss-20b (Groq Primary)</option>
          <option value="meta-llama/llama-4-scout-17b-16e-instruct">meta-llama/llama-4-scout-17b-16e-instruct (Groq Llama 4)</option>
          <option value="gemini-1.5-flash">gemini-1.5-flash (Fallback Model)</option>
        </select>

        <label for="prompt-input">User Message Prompt</label>
        <textarea id="prompt-input">Explain what an LLM Gateway does in one short sentence.</textarea>

        <div class="btn-row">
          <button onclick="sendChatRequest()" id="send-btn">Send Request to Gateway</button>
          <button class="secondary" onclick="refreshMetrics()">Refresh Spend Metrics</button>
        </div>

        <div class="response-box" id="response-container" style="display:none;">
          <div class="meta-bar" id="response-meta"></div>
          <div id="response-text" style="white-space: pre-wrap;"></div>
        </div>
      </div>

      <!-- RIGHT PANEL: Live Usage & Spend Tracker -->
      <div class="card">
        <h2>2. Live Key Spend &amp; Cache Analytics (GET /v1/admin/usage)</h2>

        <div class="stats-grid">
          <div class="stat-box">
            <div class="stat-label">Current Spend</div>
            <div class="stat-val" id="stat-spend">$0.000000</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Remaining Budget</div>
            <div class="stat-val" id="stat-remaining">$1.0000</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Total Tokens</div>
            <div class="stat-val" id="stat-tokens">0</div>
          </div>
          <div class="stat-box">
            <div class="stat-label">Cache Saved ($)</div>
            <div class="stat-val" id="stat-saved" style="color:var(--green);">$0.000000</div>
          </div>
        </div>

        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
          <span style="font-size:0.82rem; color:var(--muted);">Recent Usage Logs for Selected Key</span>
          <span style="font-size:0.78rem; color:var(--muted);" id="cache-summary">Cache Hits: 0</span>
        </div>

        <div style="overflow-x:auto;">
          <table>
            <thead>
              <tr>
                <th>Time</th>
                <th>Provider</th>
                <th>Model</th>
                <th>Tokens</th>
                <th>Cost ($ USD)</th>
                <th>Cache</th>
                <th>Latency</th>
              </tr>
            </thead>
            <tbody id="logs-tbody">
              <tr><td colspan="7" style="color:var(--muted);">Loading usage logs...</td></tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>

  <script>
    function onKeyChange() {
      const val = document.getElementById('key-select').value;
      document.getElementById('custom-key').value = val;
      refreshMetrics();
    }

    async function sendChatRequest() {
      const btn = document.getElementById('send-btn');
      const key = document.getElementById('custom-key').value.trim();
      const model = document.getElementById('model-select').value;
      const prompt = document.getElementById('prompt-input').value;

      btn.disabled = true;
      btn.textContent = 'Calling Gateway...';

      const respContainer = document.getElementById('response-container');
      const metaBar = document.getElementById('response-meta');
      const respText = document.getElementById('response-text');
      respContainer.style.display = 'block';
      metaBar.innerHTML = '<span style="color:var(--muted);">Waiting for response...</span>';
      respText.textContent = '';

      try {
        const res = await fetch('/v1/chat/completions', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'X-API-Key': key,
            'Authorization': 'Bearer ' + key
          },
          body: JSON.stringify({
            model: model,
            messages: [{ role: 'user', content: prompt }],
            temperature: 0.7
          })
        });

        const cacheHeader = res.headers.get('X-Cache') || 'MISS';
        const providerHeader = res.headers.get('X-Provider') || '-';
        const data = await res.json();

        if (res.ok) {
          const content = data.choices?.[0]?.message?.content || JSON.stringify(data);
          const tokens = data.usage?.total_tokens || 0;
          const cost = data.gateway_metadata?.cost_usd ?? 0;
          const latency = data.gateway_metadata?.latency_ms ?? 0;

          metaBar.innerHTML = `
            <span class="badge badge-ok">HTTP ${res.status} OK</span>
            <span class="badge ${cacheHeader === 'HIT' ? 'badge-hit' : 'badge-miss'}">X-Cache: ${cacheHeader}</span>
            <span>Provider: <b>${providerHeader}</b></span>
            <span>Tokens: <b>${tokens}</b></span>
            <span>Cost: <b>$${Number(cost).toFixed(7)}</b></span>
            <span>Latency: <b>${latency} ms</b></span>
          `;
          respText.textContent = content;
        } else {
          const errMsg = data.detail?.error?.message || JSON.stringify(data.detail || data);
          metaBar.innerHTML = `
            <span class="badge badge-err">HTTP ${res.status} REJECTED</span>
            <span>Reason: <b>${data.detail?.error?.type || 'Error'}</b></span>
          `;
          respText.textContent = errMsg;
        }
      } catch (err) {
        metaBar.innerHTML = `<span class="badge badge-err">Request Error</span>`;
        respText.textContent = String(err);
      } finally {
        btn.disabled = false;
        btn.textContent = 'Send Request to Gateway';
        await refreshMetrics();
      }
    }

    async function refreshMetrics() {
      const key = document.getElementById('custom-key').value.trim();
      try {
        const [usageRes, cacheRes] = await Promise.all([
          fetch('/v1/admin/usage?key=' + encodeURIComponent(key)),
          fetch('/v1/admin/cache/stats')
        ]);

        if (usageRes.ok) {
          const u = await usageRes.json();
          document.getElementById('stat-spend').textContent = '$' + Number(u.current_spend_usd).toFixed(6);
          document.getElementById('stat-remaining').textContent = '$' + Number(u.remaining_budget_usd).toFixed(4);
          document.getElementById('stat-remaining').style.color = u.is_exhausted ? 'var(--red)' : 'var(--text)';
          document.getElementById('stat-tokens').textContent = u.total_tokens;

          const tbody = document.getElementById('logs-tbody');
          if (!u.recent_logs || u.recent_logs.length === 0) {
            tbody.innerHTML = '<tr><td colspan="7" style="color:var(--muted);">No requests logged yet for this key. Click "Send Request to Gateway" to test!</td></tr>';
          } else {
            tbody.innerHTML = u.recent_logs.map(l => {
              const t = new Date(l.timestamp).toLocaleTimeString();
              return `<tr>
                <td>${t}</td>
                <td><b>${l.provider_used}</b></td>
                <td>${l.model}</td>
                <td>${l.prompt_tokens} &rarr; ${l.completion_tokens} (${l.total_tokens})</td>
                <td>$${Number(l.cost).toFixed(7)}</td>
                <td><span class="badge ${l.is_cache_hit ? 'badge-hit' : 'badge-miss'}">${l.is_cache_hit ? 'HIT' : 'MISS'}</span></td>
                <td>${Number(l.latency_ms).toFixed(1)}ms</td>
              </tr>`;
            }).join('');
          }
        }

        if (cacheRes.ok) {
          const c = await cacheRes.json();
          document.getElementById('stat-saved').textContent = '$' + Number(c.total_cost_saved_usd).toFixed(6);
          document.getElementById('cache-summary').textContent = `Cache Hits: ${c.total_cache_hits} | Cached Prompts: ${c.total_cached_entries}`;
        }
      } catch (e) {
        console.error(e);
      }
    }

    refreshMetrics();
  </script>
</body>
</html>
"""


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def root():
    return HTMLResponse(content=DASHBOARD_HTML)
