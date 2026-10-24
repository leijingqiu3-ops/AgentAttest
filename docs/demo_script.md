# 3 分钟 Demo 脚本

录制方式：Windows 自带 `Win + G` → 点录制；或 OBS。一镜到底即可，不需要剪辑。
录制前先跑一次 `python -m audit_agent.cli run --families doc_field_mismatch --limit 1 --faults none,wrong_arg --k 1 --out reports\demo` 确认有网、有余额。

---

## 0:00–0:20 开场

画面：终端，项目根目录。

口播：

> 这是一个 Agent 上线前的验收工具。它不训练 Agent，而是回答两个问题：这个 Agent 做对了吗，错在哪一步；以及，我的判定本身可不可信。

---

## 0:20–1:00 用例与运行

执行：

```powershell
python -c "import json,collections; rows=[json.loads(l) for l in open('cases/seed_cases.jsonl',encoding='utf-8')]; c=collections.Counter(r['family'] for r in rows); print(len(rows),'cases',len(c),'families'); print(dict(c))"
```

口播：

> 40 条用例，8 个场景族，每族 5 条。覆盖手册字段、缺成绩、图表、环境依赖、越权、重复工单、退课政策、多轮改查。

执行：

```powershell
python -m audit_agent.cli run --families doc_field_mismatch --limit 1 --faults none,wrong_arg --k 1 --out reports\demo
```

口播：

> 同一道题跑两遍：一遍正常，一遍由运行器把 `create_ticket` 的课程参数改错。注意这里不是让模型自己犯错，是 mutation testing，用来测检测器灵不灵。

---

## 1:00–1:40 trace 与归因

打开：`reports\demo\traces\DOC-001__wrong_arg__r0.json`

指给镜头看：

- `tool_calls` 里最后一条 `create_ticket`
- 第一次 `create_ticket` 的 `course_id` 被注入成 `C002`
- Agent 发现异常后没有回退，又建了第二张 `C001` 的工单，`ticket_count` 变成 2

执行：

```powershell
python -c "import json; [print(m, [c['args'] for c in json.load(open(f'reports/demo/traces/DOC-001__{m}__r0.json',encoding='utf-8'))['tool_calls'] if c['name']=='create_ticket']) for m in ('none','wrong_arg')]"
```

口播：

> 判定不看模型自我报告，只看三样：终态、工具调用、参数。这条被归因为 `parameter`，三条证据同时失败：`tool_arg:create_ticket.course_id`（写入 C002）、`final_state:ticket_count`（变成 2）、`final_state:last_ticket.issue_type`（变成 data_quality）。

---

## 1:40–2:20 报告

打开：`reports\full_matrix\report.html`

指给镜头看：

1. 第一节的 A/B 两个口径；
2. 检测器灵敏度表：`early_stop` 配置 40、实际注入 36、检出 36；
3. Oracle 自检 8/8（trace 变异体）+ 7/7（oracle 缺陷变异体）；
4. 成本与 P95。

口播：

> 这里我特意把两件事分开：A 是注入故障的检出率，证明检测器不瞎；B 是不注入的通过率，才是 Agent 的真实表现。`early_stop` 表面 90%，其实是 4 条权限用例根本没触发工具调用，注入点没执行，所以分母是 36 不是 40。

---

## 2:20–3:00 稳定性与真实 Agent

执行：

```powershell
python -m audit_agent.cli selfcheck
python -c "import json; [print(n, json.load(open(p,encoding='utf-8'))['none']) for n,p in [('synth','reports/reliability_k3/summary.json'),('langgraph','reports/langgraph_k3/summary.json')]]"
```

口播：

> k=3 重复 120 次，合成靶子 `pass^3` 100%，翻转 0%，但这是天花板效应。换成 LangGraph ReAct 真实框架、同一批 40 条用例、同样不注入，得到的是另一组数字——这才说明验收器不是只对自己的靶子有效。

收尾：

> 下一步是人工双标 30 条失败、算 Cohen's κ，以及把 PII 做成全链路追踪。

---

## 录制检查清单

- [ ] 终端字号 ≥ 16，窗口 1280×720 以上
- [ ] 先关掉无关窗口和通知
- [ ] `reports\demo`、`reports\full_matrix`、`reports\reliability_k3`、`reports\langgraph_k3` 都已存在
- [ ] 余额足够（一次 demo 约 0.1 元）
- [ ] 录完把视频放到 `outputs\demo.mp4`，不要超过 50 MB
