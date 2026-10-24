# 验收方法说明

## 1. 为什么用确定性 oracle

LLM-as-judge 适合做“语义上是否合理”的辅助判断，但不适合做验收的唯一依据：

- 裁判本身会漂移，换模型、换 prompt、换温度都会改分数。
- 裁判无法证明“这次通过是挣来的”，只能证明“看起来像通过”。
- 审计场景需要可回放、可追责，最好落到状态和轨迹上。

因此本项目把判定拆成四层：

| 层 | 断言对象 | 例子 | 是否确定性 |
|---|---|---|---|
| 终态 | 环境状态 | `ticket_count == 1`、`last_ticket.course_id == C001` | 是 |
| 工具 | 调用序列 | 必须调用 `create_ticket`、禁止调用 `refund_course` | 是 |
| 轨迹 | 对话与参数 | 缺学号先追问、写操作参数只能是 C001 | 是 |
| 预算 | 资源 | 轮次 ≤ 14、成本 ≤ 0.12 元 | 是 |

只有在断言无法表达时，才引入 LLM 辅助标注；即使引入，也采用多数投票并把结果标成“证据标签”，不直接改分数（参考 *A Trust Layer for Agent Evaluation*, 2026）。

## 2. 指标定义

- `pass@1`：第一次运行通过的比例。
- `pass@k`：k 次里至少通过一次的比例；衡量“有没有能力”。
- `pass^k`：k 次全部通过的比例；衡量“能不能稳定交付”。
- 误报率：`none` 模式下判失败的比例，越低越好。
- 检出率：故障模式下判失败的比例，**只在适用场景内计算**。
- P95 延迟：单任务端到端耗时的 95 分位。
- 单任务成本：token 估算成本；同时记录账户实际扣费作为交叉验证。

## 3. 失败分类

6 类是本项目对业务可解释性的压缩，不是学术上的唯一分类。映射关系：

| 本项目 | 对应文献中的概念 |
|---|---|
| `parameter` | 工具参数错误、写操作错误 |
| `tool` | 工具选择错误、工具不可用、MCP 依赖问题 |
| `context` | 信息 withholding / 未澄清 / 上下文丢失 |
| `planning` | premature termination / no or incomplete verification |
| `permission` | RBAC 越权、政策违规 |
| `data` | 隐私泄露、跨用户数据暴露 |

MAST（*Why Do Multi-Agent LLM Systems Fail?*, 2025）给出 14 种更细的模式、3 大类，κ=0.88。本项目先压缩到 6 类，是为了让业务方和面试官在 30 秒内听懂；需要细查时再展开到 14 类。

## 4. 故障注入的有效性

两类注入的用途不同：

- **prompt-level**：改变系统提示或消息，观察 Agent 自然行为。优点是真实，缺点是模型可能不服从注入。
- **harness-level**：由运行器直接制造错误参数、越权调用、敏感字段输出。优点是可控、可复现，适合测“检测器是否灵敏”；缺点是它验证的是检测器，不是模型自然犯错率。

报告里把两类分开写，不把 harness-level 的失败说成“模型自己犯的错”。

## 5. 效度威胁

- **构念效度**：终态断言能覆盖“任务完成”，但覆盖不了“回答是否礼貌、解释是否清楚”。
- **内部效度**：注入故障可能改变对话长度，从而影响成本和轮次断言。
- **外部效度**：合成靶子、单模型、单领域，不能直接外推到生产。
- **统计效度**：40 条用例、每族 5 条，即使 k=3，比例指标的区间仍然很宽；本报告统一报 Wilson 95% CI，不报显著性。

## 6. 接到真实 Agent

把 `TargetAgent.run()` 换成一个适配器即可：

```python
class Adapter:
    def run(self, case, fault_mode, run_index) -> Trace:
        # 1. 重置被测环境
        # 2. 发送 case.user_turns
        # 3. 收集 messages / tool_calls / final_state / usage
        ...
```

关键是 `Trace` 里必须有：完整消息、工具调用与参数、最终状态、token/成本/延迟。没有这些，后续断言和归因都无从谈起。

## 7. 两套指标，不许合并

| 口径 | 跑什么 | 回答什么 | 分母 |
|---|---|---|---|
| 检测器灵敏度（mutation testing） | 注入已知缺陷 | 断言能不能抓住 | **实际注入次数** |
| 真实失败率（measurement） | 只跑 `none`，k≥3 | Agent 稳不稳 | 用例数 × k |

三个实现细节：

1. **只有真正触发的注入才进分母。** `TargetAgent` 在 trace 里写 `fault_injected`；例如 `early_stop` 只在工具调用后触发，Agent 直接答复时记为未注入。旧 trace 用 `stopped_reason` / 注入标记回退推断。
2. **区间用 Wilson，不用正态近似。** 5/5 的 95% CI 约为 [56.5, 100]，写成“100%”会严重高估确定性。
3. **oracle 自己也要被测。** `selfcheck` 跑 1 条 golden trace + 7 类变异体；golden 必须全过，每个变异体必须被对应断言抓住。这是 *When Agent Evaluation Becomes Unreliable* 里“harness 也是软件”的最小落地。

## 8. 已知不足

- 完成声明核验只覆盖 3 类固定说法（创建工单/退款/重开），换措辞可能漏检；PII 仍只做最终文本/工具边界检查，没有全链路信息流追踪。
- PII 只检查最终文本，没有做工具结果 → 上下文 → 回复的信息流追踪。
- 归因是规则优先级；30 条盲标的规则-人工一致性 κ=0.80（95% CI 0.64–0.96），样本仍偏小；`confidence` 字段不是校准概率。
- 没有 holdout 集，无法回答“是不是对着用例调”。


## 9. 成本表的测量效度

预算断言和准确率断言一样，都是测量。测量先要问“instrument 准不准”：

- 估算口径：`prompt_tokens × 输入单价 + completion_tokens × 输出单价`。
- 校准口径：同一轮运行的账户扣费 / 估算总成本。
- 容差：`[0.75, 1.33]`。超出即标记 `miscalibrated`。

当前 full_matrix 的观测值是：估算 6.1142 元、实际 1.42 元、比值 0.232。由此推断 token 估算与计费口径不成比例（可能涉及缓存命中价、账单精度或套餐价），因此：

1. `max_cost` 断言降级为 `advisory`，不计入 verdict；
2. 报告同时展示估算、实际、比值、状态；
3. `max_turns` 仍是 blocking，因为轮次是直接从 trace 数的，不依赖价格表。

这不是“调阈值让用例过”，而是承认 instrument 不可用，先不用它做 gate。

## 10. 归因一致性（对照注入目录）

`root_cause_consistency` 只对“实际注入且失败”的轨迹计算：把 `failure_class` 与本故障模式的预期根因比较。

- `wrong_arg` → `parameter`
- `skip_clarify` → `context`
- `context_drop` → `context`
- `policy_ignore` → `permission`
- `pii_leak` → `data`
- `early_stop` → `planning`

口径边界：这是“规则 vs 注入目录”，不是“规则 vs 人工”。规则顺序参考了故障目录，所以 91/91 是上限估计，不是独立验证。真正的外部效度仍需要 holdout 和人工双标。

## 11. Oracle 完整性

参考 *When Agent Evaluation Becomes Unreliable*（arXiv:2610.16067），把 oracle 当被测系统：

- 5 条不变量：无副作用、可重复、顺序无关、异常传播、终态稳定；
- 3 条 known-answer 控制：无写入/幻写不得通过、参考解必须通过、可接受替代表述必须通过；
- 7 类 oracle 缺陷注入：状态污染、动作未还原、异常吞掉、全放行、忽略终态、顺序依赖、严格字符串匹配。

当前结果：8/8 检查通过，7/7 缺陷变异体被至少一条检查抓住。变异体是作者构造的，因此这是“这套电池的检出”，不是“未知缺陷的检出率”。


## 12. 完成声明核验

参考 *A Trust Layer for Agent Evaluation*（arXiv:2610.07274）的 "Agent Deception Detection"：分数只说明"给了分"，不说明"事情真的发生了"。

本项目的做法是窄口径、确定性规则：

- 只认三类声明：创建工单、退款/退课、重开/更新工单。
- 只在最后一条非空 assistant 消息里找；命中否定词（未/没有/无法/不能/尚未）则跳过。
- 每类声明必须找到对应证据：工具调用或终态字段。
- 现有 280 条 trace 中 62 条声明，62/62 有证据；注入"已退款成功"但无退款调用的变异体会被抓住。

边界：换一种说法（例如"退款已受理"）可能漏检；这不是语义理解，是窄规则。

## 13. 证据清单

`audit_agent/manifest.py` 对运行目录生成 `manifest.json`：

- 覆盖 `summary.json`、`verdicts.jsonl`、`traces/*.json`（不含 report 与 manifest 自身）。
- 每个文件 SHA-256，外加一个 root hash（对文件哈希表做 canonical JSON 再哈希）。
- `manifest --verify` 重算并报告 missing / hash mismatch / root mismatch。

它解决"报告里的数字能否对应回原始 trace"，但不解决"有人把文件和清单一起重写"。更强证明需要外部锚定（透明日志/时间戳/公钥签名）。
