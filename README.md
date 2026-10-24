<div align="center">

# AgentAttest

**给 LLM Agent 加一层可验证的关口：调用前拦得住，调用后查得清，上线前验得过。**

`Python 3.11` · `运行时 Attest` · `40 条验收用例` · `7 种故障注入` · `四层确定性断言` · `哈希链存证` · `MIT`

</div>

![运行时拦截 demo](docs/images/runtime_demo.png)

> 真实输出：7 次工具调用，3 次放行、4 次拦截；`ledger.jsonl` 校验通过，篡改副本第 1 行就被抓住。

---

## 1. 为什么做 AgentAttest

一个 ReAct Agent 的典型链路是：

```text
用户输入 → LLM 规划 → 选择工具 → 填参数 → 执行 → 把结果塞回上下文 → 继续
```

这条链路有四个绕不过去的问题：

| 问题 | 典型表现 | 只靠 prompt 能解决吗 |
|---|---|---|
| 非法工具调用 | 模型编造 `delete_all_files`，或调用未授权的工具 | 不能，模型可能被注入说服 |
| 参数/权限越界 | 把 `C001` 写成 `C002`，跨课程读学生成绩 | 不能，prompt 不是强制边界 |
| 行为不可追溯 | 出事后只有聊天记录，无法证明"第几步、什么参数、谁批准的" | 不能，日志可改 |
| 上线没有验收 | demo 能跑就上线，换模型/换 prompt 后没人知道有没有退化 | 不能，需要固定用例和可复现判定 |

市面上的常见做法各缺一块：

- **只加 prompt 约束**：模型可以不遵守，越狱/注入后失效。
- **LLM 当裁判**：换模型、换温度分数就变，出了问题无法追责。
- **只打日志**：知道"错了"，但说不出错在哪一步，也无法证明日志没被改。
- **只跑 demo**：一次成功不代表 k 次稳定，更不代表故障时能抓住。

AgentAttest 把问题拆成两层，共用一套确定性规则和证据格式：

1. **运行时 Attest**：每次工具调用前做白名单、参数、RBAC、政策、注入检查；拦截就不执行；每次调用写入哈希链账本。
2. **离线验收 Audit**：固定用例 → 运行目标 Agent → 采集完整 trace → 四层断言 → 6 类归因 → 输出可回放报告。

> 它不训练模型，也不替代 Agent 框架。它回答两个问题：**这次调用该不该放行？这个 Agent 能不能上线？**

---

## 2. 架构

```text
                    ┌──────────────────────────────────┐
用户 / 任务 ───────▶│ Planner                          │
                    │ ReAct / LangGraph / 脚本化策略    │
                    └───────────────┬──────────────────┘
                                    │ tool_call(name, args)
                                    ▼
                    ┌──────────────────────────────────┐
                    │ Attest 预检（确定性，无模型调用）  │
                    │ 工具白名单 · 必填参数 · 参数格式   │
                    │ RBAC 课程边界 · 退课政策 · 注入扫描│
                    └───────┬──────────────────┬───────┘
                       allow│                  │deny
                            ▼                  ▼
                    ┌───────────────┐   ┌──────────────────┐
                    │ Tool 执行      │   │ 阻断 + 规则原因   │
                    │ 结果做 PII 脱敏│   │ 不执行任何副作用  │
                    └───────┬───────┘   └────────┬─────────┘
                            │                    │
                            ▼                    ▼
                    ┌──────────────────────────────────┐
                    │ 哈希链账本 ledger.jsonl           │
                    │ seq · tool · args_hash · decision │
                    │ prev_hash · hash · 可选 HMAC      │
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │ 离线验收 Audit                    │
                    │ trace → 四层断言 → 6 类归因 → 报告 │
                    │ pass@k / pass^k / Wilson / 成本   │
                    └──────────────────────────────────┘
```

两条路径的分工：

- **运行时**解决"这一次调用"，要求低延迟、可阻断、可存证。
- **离线验收**解决"这个版本"，要求可复现、可比较、可归因。

两者共用同一套规则语义，避免"线上拦一套、线下评另一套"。

---

## 3. 核心功能

### 3.1 运行时 Attest：调用前拦截

`attest/engine.py` 是纯函数式检查器，不调用模型、不访问网络。当前实现的规则：

- **工具白名单**：不在 `TOOL_ALLOWLIST` 的工具直接拒绝。
- **必填参数**：按工具 schema 检查缺失参数。
- **参数格式**：`course_id` 必须是 `C\d{3}`，`student_id` 是 `S\d{3}`，`ticket_id` 是 `T-\d{4}`。
- **枚举值**：`issue_type` 必须在允许列表；工单 `status` 只能是 `open/reopened/closed`。
- **RBAC**：课程相关工具只能访问 `allowed_courses`；`admin` 角色除外。
- **退课政策**：开课超过 7 天默认拒绝；必须带人工审批令牌才放行。
- **注入启发式**：识别"忽略之前的规则 / ignore previous instructions / 删除所有文件"等模式；命中后，状态变更类工具默认拒绝。
- **PII 脱敏**：工具结果里的手机号、身份证号在返回给 Planner 之前打码。

**关键点：拦截发生在执行之前。** `examples/runtime_demo.py` 里第 3 条把 `execute()` 换成一个会抛错的函数；因为被 Attest 拦截，它根本没有被调用。

### 3.2 哈希链存证：改一行就露馅

`attest/ledger.py` 每次追加一条 JSONL：

```json
{"seq": 5, "tool": "refund_course", "decision": "deny",
 "blocked_by": ["refund_window", "untrusted_instruction"],
 "prev_hash": "...", "hash": "..."}
```

- `hash = SHA256(prev_hash + canonical(payload))`，形成链。
- 设置 `ATTEST_SECRET` 后追加 HMAC-SHA256。
- `verify()` 重算整条链；篡改任意一行，后续 `prev_hash` 全部对不上。

**诚实边界**：这是"防篡改"的哈希链 + 可选 HMAC，不是公钥签名。能改整个文件并重算链的人仍可伪造；要防这一层，需要把链锚定到外部时间戳/透明日志。

### 3.3 离线验收：40 条用例 × 7 种故障

- **用例即契约**：40 条用例、8 个场景族（文档字段不一致、缺学号、图表配置异常、环境依赖、越权查询、重复工单、超期退课、多轮改查）。每条写明任务、允许课程、预期终态。
- **四层确定性断言**：终态 / 工具 / 轨迹 / 轮次。预算层在成本表未校准时降级为 advisory（见 6.4）。
- **7 种故障注入**：`wrong_arg`、`skip_clarify`、`context_drop`、`policy_ignore`、`pii_leak`、`early_stop`，加 `none` baseline。
- **6 类归因**：`parameter` / `tool` / `context` / `planning` / `permission` / `data`。
- **指标**：`pass@1`、`pass^k`、翻转率、Wilson 95% CI、P95、单任务成本。
- **完成声明核验**：把"已创建工单 / 已退款 / 已重开"与 trace 里的工具调用、终态对照；说了没做会被判失败。
- **报告**：`report.md`、`report.html`、`summary.json`、`verdicts.jsonl`、每条 trace 的 JSON。
- **证据清单**：`manifest.json` 记录 summary、verdicts、全部 trace 的 SHA-256；`manifest --verify` 发现任何改动。

### 3.4 审计器自己也被测

`audit_agent/oracle_integrity.py` 对 oracle 做 5 条不变量 + 3 条 known-answer 控制：

| 检查 | 内容 |
|---|---|
| INV-1 | 判定不能修改 case / trace |
| INV-2 | 同一输入两次判定必须一致 |
| INV-3 | 判定不能依赖评分顺序 |
| INV-4 | oracle 异常必须抛出，且不污染 trace |
| INV-5 | 终止后动作列表和终态不能被追加/改写 |
| CTL-1 | 没写任何东西、或只声称写过的 trace 不能判通过 |
| CTL-2 | 参考解必须通过 |
| CTL-3 | 可接受的替代表述必须通过 |

同时注入 7 类 oracle 缺陷（状态污染、动作未还原、异常吞掉、全放行、忽略终态、顺序依赖、严格字符串匹配），要求每类都被至少一条检查抓住。

### 3.5 框架无关

`audit_agent/adapters/langgraph_react.py` 把同一批用例接到 LangGraph ReAct；断言、归因、报告不依赖具体 Agent 框架。运行时侧的 `guarded_call` 也不绑定框架：只要你的执行器能包成一个 `execute()` 回调即可。

---

## 4. 快速开始

### 4.1 安装

```powershell
git clone https://github.com/leijingqiu3-ops/AgentAttest.git
cd AgentAttest
python -m pip install -r requirements.txt
```

离线验收需要模型 API；运行时 demo、oracle 自检、单测都不需要。

```powershell
copy .env.example .env
# 编辑 .env，填入 LLM_API_KEY
```

### 4.2 运行时 demo（不需要 API key）

```powershell
python examples\runtime_demo.py
```

真实输出：

```text
ALLOW | 正常登记工单          | blocked_by=-
BLOCK | 跨课程读成绩          | blocked_by=course_scope
BLOCK | 未知工具（删除）       | blocked_by=tool_allowlist
BLOCK | 非法 issue_type      | blocked_by=issue_type_enum
BLOCK | 注入指令后退课         | blocked_by=refund_window,untrusted_instruction
ALLOW | 超期退课（有审批）      | blocked_by=-
ALLOW | 查成绩（手机号脱敏）    | blocked_by=-
        result={'ok': True, ... 'phone': '138****8001' ...}

ledger: {'ok': True, 'entries': 7, 'errors': [], 'integrity': 'hash_chain_only'}
tampered copy: {'ok': False, 'entries': 7, 'errors': ['line 1: hash mismatch']}
```

### 4.3 离线验收

```powershell
python -m audit_agent.cli selfcheck
python -m pytest -q
python -m audit_agent.cli run --one-per-family --faults none --k 1 --out reports\smoke
python -m audit_agent.cli manifest --run reports\smoke --verify
```

正式实验（40 条 × 7 模式，约 40 分钟、约 1.4 元）：

```powershell
python -m audit_agent.cli run --faults none,wrong_arg,skip_clarify,context_drop,policy_ignore,pii_leak,early_stop --k 1 --out reports\full_matrix
```

不重复调用 API、只重算已有 trace：

```powershell
python -m audit_agent.cli recompute --run reports\full_matrix --suite cases\seed_cases.jsonl
```

### 4.4 接到你的 Agent

运行时：

```python
from attest import AttestContext, AttestEngine, HashChainLedger, guarded_call

engine = AttestEngine()
ledger = HashChainLedger("reports/ledger.jsonl")
ctx = AttestContext(allowed_courses=("C001",), role="teacher")

result = guarded_call(
    engine, ledger,
    tool="create_ticket",
    args={"course_id": "C001", "issue_type": "doc_field_mismatch", "detail": "..."},
    ctx=ctx,
    execute=lambda: my_tool(**args),
)
```

离线验收：

```python
class Adapter:
    def run(self, case, fault_mode, run_index) -> Trace:
        # 1. 重置被测环境
        # 2. 发送 case.user_turns
        # 3. 收集 messages / tool_calls / final_state / usage
        ...
```

`Trace` 必须包含完整消息、工具调用与参数、最终状态、token/成本/延迟。没有这些，断言和归因都无从谈起。

---

## 5. 实测结果

### 5.1 运行时 demo

| 项 | 结果 |
|---|---|
| 工具调用 | 7 次：3 次放行、4 次拦截 |
| 拦截原因 | 跨课程、未知工具、非法枚举、超期退课 + 注入 |
| 执行隔离 | 被拦截的 `execute()` 未被调用 |
| PII | `13800138001` → `138****8001` |
| 账本 | 7 条，`verify()` 通过 |
| 篡改副本 | 改第 1 行后 `verify()` 失败，报 `line 1: hash mismatch` |
| 单次检查开销 | `engine.check` 约 **0.0036 ms**；账本追加约 **0.42 ms/次**（本机 2000 次实测） |

> 账本开销主要来自 JSONL 追加；相对 LLM 秒级延迟可以忽略。

### 5.2 正常模式（不注入，k=3）— `reports/reliability_k3/`

| 指标 | 结果（95% CI） |
|---|---:|
| `pass@1` | **100%** [96.9, 100.0] |
| `pass^3` | **100%** [91.2, 100.0] |
| 翻转率 | **0%** [0.0, 8.8] |
| 误报率 | **0%** |
| 实际扣费 | **0.98 元 / 120 次**（约 0.0082 元/次） |
| P95 延迟 | **9.5 s** |

### 5.3 检测器灵敏度（注入变体）— `reports/full_matrix/`

| 故障模式 | 适用运行 | 实际注入 | 检出 | 检出率（95% CI） |
|---|---:|---:|---:|---:|
| `wrong_arg` | 25 | 25 | 25 | 100% [86.7, 100] |
| `skip_clarify` | 5 | 5 | 5 | 100% [56.5, 100] |
| `context_drop` | 10 | 10 | 10 | 100% [72.2, 100] |
| `policy_ignore` | 10 | 10 | 10 | 100% [72.2, 100] |
| `pii_leak` | 5 | 5 | 5 | 100% [56.5, 100] |
| `early_stop` | 40 | 36 | 36 | 100% [90.4, 100] |

- 280 次运行；正常模式 40/40 通过，**误报 0%**。
- 实际扣费 **1.42 元 / 280 次**（约 0.005 元/次），P95 **14.0 s**。
- 注入失败共 91 条；**91/91 的归因与注入目录的预期根因一致**（Wilson 95% CI [96.0, 100]）。

> 归因一致性是"对照注入目录"，不是"对照独立人工标注"。规则顺序参考了故障目录，所以这是上限估计，不是泛化验证。

### 5.4 审计器自身

| 项 | 结果 |
|---|---|
| Trace 变异体 | 8/8 被对应断言抓住 |
| Oracle 不变量 + 控制 | 8/8 通过 |
| Oracle 缺陷变异体 | 7/7 被抓住 |
| 完成声明核验 | 62 条声明，62/62 有工具或终态证据 |
| 证据清单 | `manifest.json` 覆盖 284 个文件，`--verify` 通过 |
| 单测 | 34 passed |

### 5.5 同一套策略回放到 280 条 trace 上（在线拦截，不调模型）— `prevention.json`

把已经跑完的 trace 里的工具调用按顺序回放给 `attest`，每次调用都在"执行前"判定。这一步回答的是：**如果线上真挂了这层，能挡住多少？**

| 故障模式 | 失败 | 执行前拦下 | 出口脱敏 | 仍漏 |
|---|---:|---:|---:|---:|
| `wrong_arg` | 25 | 25 | 0 | 0 |
| `policy_ignore` | 11 | 10 | 0 | 1 |
| `skip_clarify` | 5 | 4 | 0 | 1 |
| `pii_leak` | 5 | 0 | 5 | 0 |
| `context_drop` | 11 | 0 | 0 | 11 |
| `early_stop` | 36 | 0 | 0 | 36 |
| **合计** | **93** | **39** | **5** | **49** |

- **44/93（47.3%）** 的失败可以在执行前拦下或出口脱敏；187 条通过的 trace 里**误伤 0 条**。
- 命中的规则：`task_contract:course_id` 20、`task_contract:ticket_id` 5、`course_scope` 5、`refund_window` 5、`task_contract:student_id` 4。
- `wrong_arg` 全拦，靠的是**任务级参数契约**：角色权限说"你能操作 C001–C005"，任务契约说"这次只针对 C001"。只做 RBAC 拦不住这种"参数看起来合法、但属于另一个课程"的错。
- `policy_ignore` 拦下 10 条跨课程读；漏的 1 条根本没发起调用。
- `skip_clarify` 拦下 4 条"猜错 student_id"；剩 1 条调用都合法，只是该问没问。
- `pii_leak` 5 条靠出口正则脱敏。**这是事后判定**：靶子有时直接回话、不走 `send_reply`，线上必须把回复统一收口到出口才能生效。
- `early_stop` 36 条、`context_drop` 11 条**拦不住**：它们没有违规调用可拦，只能靠离线断言发现。

> 这是**反事实回放**：拦截只说明"这次调用没发出去"，不说明"Agent 被拒后会做对"。所以 44/93 是拦截上限，不是任务成功率。

### 5.6 一个被自己抓到的测量问题

旧报告用 token 单价估算成本 **6.1142 元**，实际账单 **1.42 元**，比值 **0.232**，远超 0.75–1.33 容差。

后果：4 条 env 用例的 `max_cost=0.03` 被误判为超预算，归因为 `planning`。修正方式不是调阈值，而是：

- 预算断言在成本表未校准时降级为 **advisory**，不计入 verdict；
- 报告同时展示估算值、实际扣费、比值和状态；
- 这 4 条从失败改为"advisory warning"，失败总数从 97 修正为 **93**。

这件事写进 README，是因为**审计器本身也会坏**；能发现并修正自己的测量错误，比一个漂亮的 100% 更可信。

---

## 6. 和普通 ReAct Agent 的对比

| 维度 | 普通 ReAct | AgentAttest |
|---|---|---|
| 非法工具 | 依赖模型自觉 | 白名单，执行前拒绝 |
| 跨课程读数据 | prompt 里写"不要越权" | 确定性 RBAC + 课程边界 |
| 超期退课 | 模型可能直接调用退款 | 7 天窗口 + 人工审批令牌 |
| 注入指令 | 模型可能被说服 | 启发式扫描 + 状态变更默认阻断 |
| PII | 靠模型不输出 | 工具边界强制脱敏 |
| 审计日志 | 聊天记录，可改 | 哈希链 + 可选 HMAC，可验证 |
| 上线验收 | 人工点几下 | 40 条用例 + 7 类注入 + 统计区间 |
| 失败定位 | "它错了" | 6 类归因 + trace 步数/参数证据 |
| 失败可拦截率 | - | 44/93 执行前拦下或出口脱敏（回放，0 误伤） |
| 额外延迟 | - | 约 **0.42 ms/次**（本机实测，主要是 JSONL 追加） |
| 额外成本 | - | 运行时 0 模型调用；验收按实际 API 计费 |

**它不是"更聪明的 Agent"，而是"让 Agent 的行为可被证明"的基础设施。**

---

## 7. 技术栈

| 层 | 选型 | 说明 |
|---|---|---|
| 语言 | Python 3.11 | 类型标注 + dataclass/Pydantic |
| 模型调用 | OpenAI 兼容 SDK | 当前用 DeepSeek；可换任意兼容端点 |
| 结构化模型 | Pydantic v2 | `CaseSpec` / `Trace` / `Verdict` / `Assertion` |
| 运行时校验 | 纯 Python 正则 + 规则 | 无模型、无网络、可单测 |
| 存证 | JSONL + SHA-256 哈希链 | 可选 HMAC-SHA256；无数据库依赖 |
| Agent 框架 | LangGraph（仅适配器） | 证明验收器与框架解耦 |
| 报告 | Markdown + HTML + JSON | 人读、浏览器、机器读三种 |
| 测试 | pytest | 29 个测试，覆盖 oracle / 归因 / 运行时 / 账本 / 声明核验 |
| 文档截图 | Playwright + 本机 Edge | 只用于生成 `docs/images/*.png`，不是运行依赖 |

> 没有用 LangChain / LlamaIndex；没有数据库。需要 SQLite/Postgres 存证时，按 `HashChainLedger` 的接口加 adapter 即可。

---

## 8. 目录结构

```text
attest/                 运行时 Attest（本项目的护城河）
  engine.py             白名单 / 参数 / RBAC / 政策 / 注入检查
  policy.py             规则常量与工具 schema 约束
  ledger.py             哈希链账本 + verify()
  wrapper.py            guarded_call：检查 → 执行/阻断 → 脱敏 → 存证
  injection.py          注入启发式（明确标注为 heuristic）
  models.py             AttestContext / Decision / RuleHit
audit_agent/            离线验收
  runner.py             运行套件、指标、成本校准、根因一致性
  oracle.py             四层确定性断言
  classifier.py         6 类归因
  oracle_integrity.py   oracle 自检（5 不变量 + 3 控制 + 7 变异体）
  report.py             MD/HTML/JSON 报告
  manifest.py           证据清单：文件 SHA-256 + root hash
  target/               可控靶子 Agent：工具、状态、RBAC
  adapters/             LangGraph ReAct 适配器
cases/                  40 条种子用例、schema、badcase 导入
examples/               runtime_demo.py
tests/                  29 个单测
docs/                   方法、标注规则、截图、简历描述
reports/                full_matrix / reliability_k3 / runtime_demo
scripts/                用例生成、badcase 导入、κ 计算
```

---

## 9. 设计取舍

- **为什么规则放执行前，而不是事后审计？** 事后只能追责，不能阻止副作用。Attest 的第一目标是"不该发生的调用根本不发生"。
- **为什么运行时不用 LLM 判断？** LLM 判断会漂移，也无法解释"为什么拒"。运行时用确定性规则；LLM 只做离线辅助标注。
- **为什么还要离线验收？** 规则本身也会错。40 条用例 + 故障注入是给规则层做体检，防止"拦得很爽但把正常请求也拦了"。
- **为什么账本不是数据库？** 单机、零依赖、可直接进 Git/对象存储；需要查询时再加 adapter。哈希链先解决"有没有被改"。
- **为什么报区间不报显著性？** 40 条、每族 5 条，样本太小；Wilson CI 比"提升 X%"更诚实。

---

## 10. 已知局限

- 运行时规则是**确定性策略**，不理解语义。注入扫描是正则启发式，不是分类器；绕过写法它抓不到。
- `examples/runtime_demo.py` 直接驱动 `guarded_call`，**没有接真实 LLM Planner**；接法是包一个 `execute()` 回调。仓库里的离线靶子有自己的工具循环，未默认套运行时层。
- 账本是哈希链 + 可选 HMAC，**不是公钥签名**；没有外部时间戳/透明日志锚定。
- 没有数据库；JSONL 适合单机 demo，不适合高并发多实例。
- 40 条用例全部是 `synthetic_seed`，不是由真实 badcase 自动生成；单模型、单领域、无 holdout。
- 本地下载的 8 个公开数据集都不含"工具级失败 + 权限/PII 标签"，无法独立验证这套断言，逐条原因见 `docs/datasets.md`。
- 归因一致性是**对照注入目录**，不是独立人工标注；κ=0.80 只有 30 条样本，CI 0.64–0.96。
- 成本表与账单不成比例（6.11 vs 1.42），预算断言当前只作 advisory；token 估算不能替代计费口径。
- PII 只在工具边界和 `send_reply` 出口脱敏；靶子直接回话时绕过了出口，回放里的 5 条是事后判定，不是已生效的拦截。
- 任务级参数契约在回放里来自用例的 `expected`（即人工写好的正确值）。生产环境必须由**受校验的工单/表单**提供；如果让 Planner 自己生成契约，等于让模型给自己发许可证。
- 完成声明核验只覆盖 3 类固定说法（创建工单 / 退款 / 重开），且依赖固定措辞；换个说法可能漏检。
- 证据清单是本地 SHA-256 清单，不防"改文件并重算清单"；需要外部锚定才具备更强证明力。

---

## 11. Roadmap

- [ ] 把运行时 Attest 接进真实 ReAct/LangGraph Planner，测端到端延迟与误拦率
- [ ] 账本增加 SQLite adapter 与外部锚定（透明日志/时间戳）
- [ ] 注入检测从正则升级为小分类器，并做对抗样本评估
- [ ] 增加 holdout 用例与跨领域用例，降低过拟合风险
- [ ] 接入更多真实 Agent（OpenHands / Qwen-Agent / 自研业务 Agent）
- [ ] PII 全链路追踪，并把声明核验扩展到更多说法
- [ ] GitHub Action：把 `pass^k`、误报率、P95 变成 PR 门禁

---

## 12. 依据

方法设计参考了以下工作（只列实际读过、且落到代码里的）：

- *When Agent Evaluation Becomes Unreliable*（arXiv:2610.16067）：把评测 harness 当被测系统；5 条状态不变量 + 3 条 known-answer 控制 + 7 类 oracle 缺陷注入。
- *A Trust Layer for Agent Evaluation*（arXiv:2610.07274）：判定与证据分离；模型只标注证据，verdict 由确定性规则给出。
- *Why Do Multi-Agent LLM Systems Fail?*（arXiv:2503.13657）：MAST 14 类失败模式；本项目的 6 类是其业务化压缩，不是一一映射。
- *τ-bench*（arXiv:2406.12045）：`pass^k` 作为稳定性指标。
- *Evaluation and Benchmarking of LLM Agents: A Survey*（arXiv:2507.21504）：能力/成本/延迟/安全分维报告。
- *WebArena*（arXiv:2307.13854）与 *AgentBench*（arXiv:2308.03688）：可复现环境与跨环境泛化的效度威胁。

> 论文里的数字没有被移植成本项目的成绩；本 README 的数字都来自 `reports/` 下的实际运行。

---

## 13. License

MIT © 2026 Leijing Qiu