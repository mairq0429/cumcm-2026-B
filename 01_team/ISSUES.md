# 问题清单

优先级说明：`P0` 为立即阻塞，`P1` 为高优先级，`P2` 为一般优先级，`P3` 为低优先级。

## P0

| 问题编号 | 标题 | 描述 | 负责人 | 状态 | 截止时间 | 关联版本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## P1

| 问题编号 | 标题 | 描述 | 负责人 | 状态 | 截止时间 | 关联版本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |
| Q2-I-001 | M6 尚未完成 | M5B Garea/Qarea、风险阈值 shortlist 与 received-subset worst 已完成；正式全域结果、1440→2880、Lmin 敏感性和整体收敛仍待实现 | C | OPEN | 后续轮次 | Q2-robust-selection-v2.1 | eps_rec_cert 已冻结为数值认证精度且物理阈值为 0；仍需正式全域 1e-4/1e-3/1e-2 敏感性。area_q_tol 仍为 implementation parameter；不得在完成前声明 Q2 TESTED/VERIFIED |
| Q2-I-002 | M6A 全域运行超出有界窗口 | strict certificate 已由 M6A.1 加速至约 1.24 s；正式重跑的 1440 完整配置仍在 300 s 未完成，3 个粗层 M4 样本约 0.75--0.81 s/点，当前瓶颈转移到大量粗层 objective M4 评价 | C | OPEN | 在不减少候选覆盖、source/error、Gverify/replay 标准的前提下安全减少/复用粗层 M4 工作，再完整重跑 M6A | Q2-robust-selection-v2.1 | 未启动 2880/eps-cert/Lmin；T12=UNRESOLVED，M6B 禁止进入 |
| Q2-I-003 | 粗层 objective M4 调用量 | M6A.2 用 lazy queue + 单向 C20 sample rejection 将 50 m full M4 从 1184 estimate 降至 6 calls，总耗时约 9.54 s | C | RESOLVED | 完整 M6A 前持续执行 legacy/lazy、tie、no-C20 和 parent-bound 回归 | Q2-robust-selection-v2.1 | 只减少无需评价的 candidate，不改变单点 M4、选择规则或 Fstrict |
| Q2-I-004 | 1440 baseline 5 m 层超时 | M6A.3 的 50 m/20 m 已完成并写 checkpoint；5 m region/objective processing 达到 300 s 单级上限 | C | OPEN | profile 5 m region/certificate/objective 子阶段，在不降低完整 region mapping、M4 或验证标准下加速 | Q2-robust-selection-v2.1 | 最终 5 m selected 不存在，candidate convergence 与独立 revalidation 未运行；不得进入 2880 |
| Q2-I-005 | 5 m 批量 strict classification 超时 | incremental/event-driven anchor propagation 将正式50→20→5 region-only从>300 s降至约56.5 s；legacy/incremental点状态、whole-cell状态及anchor sequence零差异 | C | RESOLVED | 后续完整1440继续使用incremental production path；保留legacy oracle回归 | Q2-robust-selection-v2.1 | 未采用KDTree/并行/近似；物理阈值0、eps认证精度和四态证书均不变；5 m仍有6个UNRESOLVED cells须保留 |

## P2

| 问题编号 | 标题 | 描述 | 负责人 | 状态 | 截止时间 | 关联版本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## P3

| 问题编号 | 标题 | 描述 | 负责人 | 状态 | 截止时间 | 关联版本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |
