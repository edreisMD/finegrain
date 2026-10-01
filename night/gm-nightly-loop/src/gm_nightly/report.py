from __future__ import annotations

import html
import json
from pathlib import Path

from .pipeline import load_dataset


def render_report(path: Path, tenant: str, training: dict | None = None) -> Path:
    manifest, tasks = load_dataset(path, tenant)

    def esc(value):
        return html.escape(str(value))

    cards = "".join(
        f'<div class="stat"><strong>{manifest["counts"].get(key, 0)}</strong><span>{label}</span></div>'
        for key, label in [
            ("train", "SFT + RL tasks"),
            ("recall", "Memory recall tests"),
            ("generalization", "Source holdout tests"),
            ("regression", "Behavior checks"),
        ]
    )
    rows = "".join(
        f'''<details data-suite="{esc(t.split)}"><summary><span class="badge">{esc(t.split)}</span>
{esc(t.question)}</summary><div class="detail"><p class="label">Expected answer</p><pre>{esc(json.dumps(t.answer, ensure_ascii=False, indent=2))}</pre>
<p class="label">Source evidence</p><blockquote>{esc(t.evidence or t.context)}</blockquote>
<p class="muted">{esc(t.memory_id)} · {esc(t.kind)} · {esc(t.id)}</p></div></details>'''
        for t in tasks
    )
    status = (
        "Offline fixture · no model has been trained"
        if manifest["demo"]
        else "Compiled with River · ready for training"
    )
    result = ""
    if training and training.get("dataset") == manifest["id"]:
        status = (
            "Candidate passed evaluation"
            if training["gate"]["passed"]
            else "Candidate held back by evaluation"
        )
        result = f"<pre>{esc(json.dumps({k: training[k] for k in ('checkpoint', 'before', 'after', 'gate')}, indent=2))}</pre>"
    document = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>GM Nightly Loop · Learning manifest</title><style>
:root{color-scheme:light;--ink:#18362c;--muted:#69796f;--line:#dce4d9;--green:#286545}*{box-sizing:border-box}
body{margin:0;background:#f7f8f2;color:var(--ink);font:15px/1.6 ui-sans-serif,system-ui,sans-serif}
main{max-width:1120px;margin:auto;padding:42px 28px 80px}header{display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);padding-bottom:24px}
.brand{font-size:24px;font-weight:750;letter-spacing:-1px}.brand i{font-style:normal;color:#91aa43}.tag,.label{font:11px/1.4 ui-monospace,monospace;text-transform:uppercase;letter-spacing:1.5px;color:var(--muted)}
.hero{padding:54px 0 32px;max-width:750px}h1{font-size:clamp(36px,5vw,62px);letter-spacing:-2.5px;line-height:1.08;margin:14px 0 20px;font-weight:560}
.lead{font-size:18px;color:var(--muted);max-width:640px}.status{display:inline-block;border:1px solid #c6d9bd;border-radius:24px;padding:7px 13px;font-size:12px;background:#edf3e5}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin:20px 0 45px}.stat{border-top:2px solid #9ab181;padding:20px 0}.stat strong{display:block;font-size:38px;font-weight:500}.stat span,.muted{color:var(--muted);font-size:12px}
.flow{padding:18px 22px;background:#eaf0e3;border-radius:8px;font-size:14px;margin:20px 0 36px}.flow span{color:#809675;margin:0 14px}
.toolbar{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin:18px 0}input,select{font:inherit;padding:10px 12px;border:1px solid var(--line);border-radius:5px;background:white;color:var(--ink)}input{flex:1;min-width:180px}
h2{font-size:22px;font-weight:550;letter-spacing:-.5px}details{border-bottom:1px solid var(--line)}summary{cursor:pointer;padding:18px 5px;list-style:none;display:flex;gap:18px;align-items:baseline}.badge{min-width:108px;font:10px ui-monospace,monospace;text-transform:uppercase;letter-spacing:1px;color:var(--green)}
.detail{padding:0 20px 20px 131px}pre{background:#eef1e9;padding:16px;border-radius:6px;white-space:pre-wrap;overflow-wrap:anywhere;font:13px/1.6 ui-monospace,monospace}
blockquote{border-left:2px solid #9ab181;padding-left:15px;margin-left:0;color:var(--muted)}footer{margin-top:50px;border-top:1px solid var(--line);padding-top:20px;font-size:12px;color:var(--muted)}
@media(max-width:650px){.stats{grid-template-columns:repeat(2,1fr)}.detail{padding-left:5px}.flow span{margin:0 5px}header .tag{display:none}summary{display:block}.badge{display:block;margin-bottom:8px}}
</style><main><header><div class="brand">gm-nightly<i>✳</i></div><div class="tag">Memory → learning → ownership</div></header>
<section class="hero"><div class="tag">Company learning manifest</div><h1>A day's work.<br>A lasting memory.</h1><p class="lead">The knowledge your team creates becomes a curriculum your model can learn. Every task leads back to its source.</p>
<div class="status">STATUS</div></section><div class="flow">Gbrain source of truth <span>→</span> Teacher & critic <span>→</span> SFT + RL <span>→</span> Evaluation gate</div>
<section class="stats">CARDS</section><h2>Inspect the curriculum</h2><p class="muted">Recall tests hide the source. Generalization tests use held-out source context. Both are separate from training prompts.</p>
<div class="toolbar"><input id="search" aria-label="Search tasks" placeholder="Search a task, source, or answer…"><select id="suite" aria-label="Evaluation suite"><option value="all">All tasks</option><option>train</option><option>recall</option><option>generalization</option><option>regression</option></select><span id="count" class="muted"></span></div>
<section id="tasks">ROWS</section>RESULT<footer>TENANT · Dataset DATASET · Source-grounded, independently reviewed. Synthetic checks do not prove production quality.</footer></main>
<script>const search=document.querySelector('#search'),suite=document.querySelector('#suite');function filter(){let count=0;document.querySelectorAll('details').forEach(row=>{const show=(suite.value==='all'||row.dataset.suite===suite.value)&&row.textContent.toLowerCase().includes(search.value.toLowerCase());row.hidden=!show;if(show)count++});document.querySelector('#count').textContent=count+' tasks'}search.addEventListener('input',filter);suite.addEventListener('change',filter);filter();</script></html>"""
    for key, value in {
        "STATUS": esc(status),
        "CARDS": cards,
        "ROWS": rows,
        "RESULT": result,
        "TENANT": esc(tenant),
        "DATASET": esc(manifest["id"]),
    }.items():
        document = document.replace(key, value)
    target = path / "report.html"
    target.write_text(document)
    target.chmod(0o600)
    return target


def write_evaluation_report(path: Path, result: dict) -> Path:
    evaluations = result["evaluations"]
    lines = [
        "# GM Nightly Loop evaluation",
        "",
        f"Run: `{result['run_id']}`",
        "",
        "| Model | Recall | Abstention | Staleness | Procedure | Confident wrong | General |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]

    def pct(value):
        return "n/a" if value is None else f"{value:.1%}"

    for name, metrics in evaluations.items():
        values = [
            metrics.get("kinds", {}).get(k, {}).get("score")
            for k in ("recall", "abstention", "staleness", "procedure")
        ]
        values += [
            metrics.get("confident_wrong_rate"),
            metrics.get("suites", {}).get("regression", {}).get("score"),
        ]
        lines.append(f"| {name} | " + " | ".join(pct(v) for v in values) + " |")
    lines += [
        "",
        "Promotion: **" + ("passed" if result["gate"]["passed"] else "rejected") + "**.",
        "",
        "Reasons: " + (", ".join(result["gate"]["reasons"]) or "All thresholds met."),
        "",
        f"Candidate checkpoint: `{result['checkpoint']}`",
        "",
        "These are measured results on a small synthetic curriculum. They do not establish production reliability.",
        "Recall tests target known facts with held-out questions. Source holdouts test retrieval from unseen pages.",
        "Cost is null when River has not reported it; it must not be read as zero.",
    ]
    path.write_text("\n".join(lines) + "\n")
    return path
