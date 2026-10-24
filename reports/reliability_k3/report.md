# Agent 验收审计报告

- 生成时间：2026-10-24T13:57:17+08:00
- 被测对象：synthetic
- 被测模型：`deepseek-flash`（temperature=0.0）；审计判定：确定性断言 + 规则归因
- 用例数：40；故障模式：1；重复次数 k=3；总运行：120
- 可复现信息：git `60e010f`；用例集 sha256 `a18f13b7e760bc8e`；trace schema v3

- 证据清单：`manifest.json` root `f27b4983b98862fa`（122 个文件）
## 一、结论与口径

本报告把两件事分开，不合并成一个数：

- **A. 检测器灵敏度（mutation testing）**：运行器确定性注入已知缺陷，看断言能不能抓住。它证明“检测器不是瞎的”，不证明“真实 Agent 会犯这些错”。
- **B. 真实失败率（measurement）**：只跑 `none` 模式，不注入，k 次重复。它才回答“这个 Agent 稳不稳”。

- 正常模式：`pass@1 = 100.0% [96.9, 100.0]`，`pass^k = 100.0% [91.2, 100.0]`，误报率 `0.0%`。
- 重复运行翻转率：`0.0% [0.0, 8.8]`。翻转越高，单次验收越不可信。
- 单次运行成本：按配置费率估算 `0.0213` 元/次，P95 延迟 `9512.0 ms`。
- 每个通过用例的累计成本（含 k 次重复）：`0.0638` 元。
- 本次实际账户扣费 `0.9800` 元，折合 `0.0082` 元/次。
- 成本表校准：估算 `2.5531` 元 / 实际 `0.9800` 元，比值 `0.384`（容差 0.75–1.33），不可用于判定，预算断言已降级为 advisory。
- Oracle 自检：golden trace `通过`；变异体 `8/8` 被抓住。

## 二、判定方法

每条用例包含任务、允许课程、脚本化用户轮次和预期终态。运行结束后按以下顺序判定：

1. **终态断言**：比较平台状态，如 `ticket_count`、`last_ticket.issue_type`、`last_updated.status`、`refunds_count`。
2. **工具断言**：必需工具是否调用、禁用工具是否被调用。
3. **轨迹断言**：缺标识时是否先追问、是否跨课程读取、是否泄露手机号。
4. **预算断言**：轮次与单任务成本。

判定不依赖 LLM 裁判；LLM 只负责扮演被测 Agent 和脚本化用户，避免“裁判也是模型”的循环论证。

故障注入分为两类：**prompt-level**（`skip_clarify`、`context_drop`、`early_stop`）通过提示或提前终止诱发；**harness-level**（`wrong_arg`、`policy_ignore`、`pii_leak`）由运行器确定性注入，用于验证检测器的灵敏度。两类都会在 trace 中标注，不把注入行为算作模型自发行为。

**只有真正触发了注入的 run 才进入检出率分母。** 例如 `early_stop` 只在 Agent 发起工具调用后触发；如果它直接给出答复，这条 run 记为“未注入”，不计为漏检。旧 trace 没有 `fault_injected` 字段时，按 `stopped_reason` 与注入标记回退推断。

## 三、检测器灵敏度（注入变体）

| 故障模式 | 配置 run | 适用 run | 实际注入 | 未注入 | 检出 | 检出率（95% CI） | 主要失败类 |
|---|---:|---:|---:|---:|---:|---:|---|

配置 run 是计划运行次数；适用 run 排除了该故障不覆盖的场景族；实际注入才是分母。

## 四、分场景结果

| 场景 | `none` |
|---|---:|
| doc_field_mismatch | 100.0% |
| missing_grade | 100.0% |
| chart_mismatch | 100.0% |
| env_dependency | 100.0% |
| permission | 100.0% |
| duplicate_ticket | 100.0% |
| policy_exception | 100.0% |
| context_switch | 100.0% |

正常模式列是**通过率**，故障模式列是**注入后的检出率**。

## 五、审计器自身的测量质量

### 5.1 成本表校准

预算断言只有在成本表被账单校准时才允许参与通过/失败；否则只作为告警。

| 估算成本 | 实际扣费 | 实际/估算 | 容差 | 状态 | 预算断言 |
|---:|---:|---:|---|---|---|
| 2.5531 | 0.98 | 0.3839 | 0.75–1.33 | miscalibrated | advisory |

状态为 `miscalibrated` 时，说明 token 估算与账单不成比例；此时不能拿估算值去判预算超限。

### 5.2 归因一致性（对照注入目录）

| 故障模式 | 应归因 | 注入 run | 失败 run | 一致 | 一致率（95% CI） | 实际分布 |
|---|---|---:|---:|---:|---|---|

口径：Compared with the injection catalogue's intended root cause, not with independent human labels. 这是上限估计，不是独立人工验证。

### 5.3 断言级通过率

- Blocking 断言：`958/958` 通过（`100.0%`）。
- Advisory 断言失败：`0` 次（不计入 verdict）。

| 断言类型 | 条数 | 通过率 |
|---|---:|---:|
| `claim_consistency` | 28 | 100.0% |
| `clarification_before_tool` | 15 | 100.0% |
| `final_state` | 285 | 100.0% |
| `forbidden_pattern` | 30 | 100.0% |
| `forbidden_tool` | 45 | 100.0% |
| `max_turns` | 120 | 100.0% |
| `no_permission_violation` | 120 | 100.0% |
| `reply_contains_any` | 45 | 100.0% |
| `required_tool` | 180 | 100.0% |
| `tool_arg` | 90 | 100.0% |

### 5.4 Oracle 完整性（oracle 自己也被测）

- 检查项：`8/8` 通过；变异体：`7/7` 被抓住。

| 检查 | 结果 | 说明 |
|---|---|---|
| `INV-1_no_side_effect` | 通过 | case+trace unchanged after evaluate() |
| `INV-2_deterministic` | 通过 | two evaluations of the same trace agree |
| `INV-3_order_independent` | 通过 | A→B and B→A produce the same verdict map |
| `INV-4_exception_propagates` | 通过 | invalid oracle input raises and does not mutate the trace |
| `INV-5_terminal_state_stable` | 通过 | no actions appended and terminal state unchanged |
| `CTL-1_no_write_not_solved` | 通过 | no-op and phantom-write traces are not graded as solved |
| `CTL-2_reference_solved` | 通过 | golden trace passes every blocking assertion |
| `CTL-3_alternative_accepted` | 通过 | reply_contains_any accepts '工单已创建' |

| 注入的 oracle 缺陷 | 是否被抓住 | 命中的检查 |
|---|---|---|
| state mutation never restored | 是 | INV-1_no_side_effect, INV-5_terminal_state_stable |
| actions appended beyond the terminating one | 是 | INV-1_no_side_effect, INV-5_terminal_state_stable |
| oracle exception swallowed | 是 | INV-4_exception_propagates |
| oracle passes everything | 是 | INV-4_exception_propagates, CTL-1_no_write_not_solved |
| oracle ignores terminal state | 是 | CTL-1_no_write_not_solved |
| verdict depends on scoring order | 是 | INV-3_order_independent |
| only one exact phrasing accepted | 是 | CTL-3_alternative_accepted |

依据：arXiv:2610.16067 (oracle-integrity auditing)。Mutants are author-constructed; detection is a conditional property of this battery, not a rate for unknown defects.

## 六、正常模式下的误报

本轮 40/40 全部通过，误报率为 0。

注意：样本只有 40 条、每族 5 条，置信区间很宽；不要把 100% 读成“绝对稳定”。

## 七、失败样例与证据

本次运行没有失败样例。
## 八、局限

- 被测靶子是可控合成环境，故障是注入的，不代表真实生产 Agent 的故障分布。
- 用例只覆盖教学平台运维的 8 个场景族，每族 5 条；区间估计很宽，未覆盖长周期任务和多 Agent 协作。
- 失败归因是规则映射，置信度是工程优先级，不是统计校准后的概率；归因一致性是对照注入目录，不是独立人工标注。
- 成本表与账单不同比例时，预算断言只作告警；token 估算不能替代计费口径。
- 单模型、单轮实验；扩展到多模型、真实 Agent 和人工双标后，结论才可外推。

## 九、运行元数据

```json
{
  "model": "deepseek-flash",
  "temperature": 0.0,
  "cases": 40,
  "runs": 120,
  "k": 3,
  "faults": [
    "none"
  ],
  "git_sha": "60e010f",
  "cases_sha256": "a18f13b7e760bc8e",
  "duration_s": 661.6
}
```
