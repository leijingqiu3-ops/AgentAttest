# Agent 验收审计报告

- 生成时间：2026-10-23T20:42:02+08:00
- 被测对象：教学平台工单 Agent（可控靶子，7 种运行模式，含 baseline）
- 被测模型：`deepseek-flash`（temperature=0.0）；审计判定：确定性断言 + 规则归因
- 用例数：1；故障模式：2；重复次数 k=1；总运行：2
- 可复现信息：git `unknown`；用例集 sha256 `dc805453e96ca05c`；trace schema v2

## 一、结论与口径

本报告把两件事分开，不合并成一个数：

- **A. 检测器灵敏度（mutation testing）**：运行器确定性注入已知缺陷，看断言能不能抓住。它证明“检测器不是瞎的”，不证明“真实 Agent 会犯这些错”。
- **B. 真实失败率（measurement）**：只跑 `none` 模式，不注入，k 次重复。它才回答“这个 Agent 稳不稳”。

- 正常模式：`pass@1 = 100.0% [20.6, 100.0]`，误报率 `0.0%`。本轮 k=1，`pass^k` 需 k≥3，尚未测量。
- 检测器灵敏度区间：`100.0%` — `100.0%`（分母是实际注入次数，不是配置次数）。
- 单次运行成本：按配置费率估算 `0.0459` 元/次，P95 延迟 `12702.0 ms`。
- 每个通过用例的累计成本（含 k 次重复）：`0.0362` 元。
- 本次实际账户扣费 `0.0000` 元，折合 `0.0000` 元/次。
- Oracle 自检：golden trace `通过`；变异体 `7/7` 被抓住。

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
| `wrong_arg` | 1 | 1 | 1 | 0 | 1 | 100.0% [20.6, 100.0] | parameter |

配置 run 是计划运行次数；适用 run 排除了该故障不覆盖的场景族；实际注入才是分母。

## 四、分场景结果

| 场景 | `none` | `wrong_arg` |
|---|---:|---:|
| doc_field_mismatch | 100.0% | 100.0% |

正常模式列是**通过率**，故障模式列是**注入后的检出率**。

## 五、正常模式下的误报

本轮 1/1 全部通过，误报率为 0。

## 六、失败样例与证据

### 1. `DOC-001` / `wrong_arg`

- 失败类型：`parameter`（规则优先级 0.93，非校准概率）
- 归因：write call used a forbidden argument value; final_state:ticket_count: expected=1, got=2; final_state:last_ticket.issue_type: expected='doc_field_mismatch', got='data_quality'; tool_arg:create_ticket.course_id: allowed=['C001'], bad_values=['C002']
- 断言 `final_state:ticket_count`：expected=1, got=2
- 断言 `final_state:last_ticket.issue_type`：expected='doc_field_mismatch', got='data_quality'
- 断言 `tool_arg:create_ticket.course_id`：allowed=['C001'], bad_values=['C002']
- 工具轨迹：
  - `search_knowledge` args=`{"query": "工单课程归属错误 记录到其他课程 data_quality 处理"}` → `{"ok": true, "results": ["同一课程同一问题在 7 天内重复出现时，应调用 update_ticket 将原工单状态改为 reopened，不要新建工单。", "教师只能访问本人负责课程的数据。跨课程查询必须拒绝，不得调用 get_student_record 读取其他课程学生信息。"]}`
  - `create_ticket` args=`{"course_id": "C001", "detail": "平台缺陷（数据质量）：工单 T-2001 以 course_id=C001 提交（内容为《大数据导论》实训手册字段不一致），但工单系统实际记录 course_id=C002。经 get_ticket(\"T-2001\") 复核，返回 {\"id\":\"T-2001\",\"course_id\":\"C002\",\"issue_type\":\"doc_field_mismatch\",\"status\":\"open\"}，而 C002 实际为《某高校校情管理分析案例》，与问题描述课程不符。请求将 T-2001 的课程归属更正为 C001，并排查工单创建接口的 course_id 写入逻辑。", "issue_type": "data_quality"}` → `{"ok": true, "ticket_id": "T-2002", "ticket": {"id": "T-2002", "course_id": "C001", "issue_type": "data_quality", "status": "open", "detail": "平台缺陷（数据质量）：工单 T-2001 以 course_id=C001 提交（内容为《大数据导论》实训手册字段不一致），但工单系统实际记录 cours`
- 最终输出摘录：`





已处理完成，结论如下：

**1. 字段不一致已登记**
- 课程：《大数据导论》（C001，张老师）
- 平台实际字段（来自 get_course C001）：学号、姓名、平时成绩、期末成绩、总评
- 手册差异：缺失「平时成绩」「期末成绩」；手册的「成绩」应对应平台的「总评」
- 依据知识库规则（手册数据样例表字段必须与实训环境数据表一致），已登记工单 **T-2001**，issue_type=doc_field_mis`

## 七、局限

- 被测靶子是可控合成环境，故障是注入的，不代表真实生产 Agent 的故障分布。
- 用例只覆盖教学平台运维的 8 个场景族，每族 5 条；区间估计很宽，未覆盖长周期任务和多 Agent 协作。
- 失败归因是规则映射，置信度是工程优先级，不是统计校准后的概率；尚无人工双标与 κ。
- 单模型、单轮实验；扩展到多模型、真实 Agent 和人工双标后，结论才可外推。

## 八、运行元数据

```json
{
  "model": "deepseek-flash",
  "temperature": 0.0,
  "cases": 1,
  "runs": 2,
  "k": 1,
  "faults": [
    "none",
    "wrong_arg"
  ],
  "git_sha": "unknown",
  "cases_sha256": "dc805453e96ca05c",
  "duration_s": 22.1
}
```
