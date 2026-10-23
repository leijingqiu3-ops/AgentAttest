$ErrorActionPreference = "Stop"
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
Set-Location $PSScriptRoot

function Pause-Step($text) {
    Write-Host ""
    Write-Host "---- $text ----" -ForegroundColor Cyan
    Read-Host "按回车继续（录制时可停在这里讲）"
}

Write-Host "=== Agent 验收审计 3 分钟 Demo ===" -ForegroundColor Green

Pause-Step "1/6 用例集：40 条，8 个场景族"
python -c @"
import json, collections
rows=[json.loads(l) for l in open('cases/seed_cases.jsonl', encoding='utf-8') if l.strip()]
c=collections.Counter(r['family'] for r in rows)
print('cases:', len(rows), 'families:', len(c))
for k,v in c.items(): print(f'  {k}: {v}')
"@

Pause-Step "2/6 跑一条正常 + 一条参数篡改（约 20 秒）"
python -m audit_agent.cli run --families doc_field_mismatch --limit 1 --faults none,wrong_arg --k 1 --out reports\demo

Pause-Step "3/6 对比两条 trace 的 create_ticket 参数"
python -c @"
import json
for mode in ('none','wrong_arg'):
    t=json.load(open(f'reports/demo/traces/DOC-001__{mode}__r0.json', encoding='utf-8'))
    calls=[c['args'] for c in t['tool_calls'] if c['name']=='create_ticket']
    print(mode, '->', calls)
"@
Write-Host "打开 trace 目录：" -ForegroundColor Yellow
Write-Host "  reports\demo\traces\DOC-001__wrong_arg__r0.json"

Pause-Step "4/6 Oracle 自检：golden trace + 7 类变异体"
python -m audit_agent.cli selfcheck | Select-Object -Last 12

Pause-Step "5/6 打开检测器灵敏度报告"
Start-Process "reports\full_matrix\report.html"

Pause-Step "6/6 稳定性与真实 Agent 对照"
python -c @"
import json
for name, path in [('synthetic k=3','reports/reliability_k3/summary.json'), ('LangGraph k=3','reports/langgraph_k3/summary.json')]:
    try:
        s=json.load(open(path, encoding='utf-8'))
        n=s['none']
        print(f"{name}: pass@1={n['pass_at_1']:.1%} pass^k={n['pass_pow_k']:.1%} flip={n['flip_rate']:.1%} cost={s['overall'].get('cost_cny_actual')}")
    except FileNotFoundError:
        print(name, 'not ready')
"@

Write-Host ""
Write-Host "Demo 结束。" -ForegroundColor Green
