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
| Q2-I-001 | M6 尚未完成 | M5B Garea/Qarea、风险阈值 shortlist 与 received-subset worst 已完成；1440 baseline 现已可完整运行，但 candidate convergence 仍未通过；1440→2880、eps-cert/Lmin 敏感性和整体收敛仍待完成 | C | OPEN | 后续轮次 | Q2-robust-selection-v2.1 | eps_rec_cert 已冻结为数值认证精度且物理阈值为 0；不得在完成前声明 Q2 TESTED/VERIFIED |
| Q2-I-002 | M6A 全域运行超出有界窗口 | 历史阻塞：strict certificate、粗层 M4、5 m candidate generation 与 5 m batch classification 曾导致 1440 全域超过 300 s；在 M6A.1/A.2/A.4/A.5 合并后，完整 1440 50→20→5 已在 GitHub Actions 中多次完成 | C | RESOLVED | 保留完整回归与 runtime diagnostics | Q2-robust-selection-v2.1 | 本轮完整 1440 wall-clock 约 29--53 s（不同 runner），未降低候选覆盖、source/error、Gverify/replay 或严格证书标准 |
| Q2-I-003 | 粗层 objective M4 调用量 | M6A.2 用 lazy queue + 单向 C20 sample rejection 将 50 m full M4 从 1184 estimate 降至 6 calls，总耗时约 9.54 s | C | RESOLVED | 完整 M6A 前持续执行 legacy/lazy、tie、no-C20 和 parent-bound 回归 | Q2-robust-selection-v2.1 | 只减少无需评价的 candidate，不改变单点 M4、选择规则或 Fstrict |
| Q2-I-004 | 1440 baseline 5 m 层超时 | 历史阻塞：M6A.3 的 5 m region/objective processing 曾达到 300 s 单级上限；M6A.4/A.5 后 5 m 可完成，完整 1440 已产出 5 m selected、candidate convergence 与独立 revalidation | C | RESOLVED | 继续保留性能回归；当前阻塞已转移为 candidate-convergence 语义问题 | Q2-robust-selection-v2.1 | 正式 5 m selected=(1727.5,-42.5)，独立 source/error/Gverify/replay 均 PASS；不得因本 issue resolved 而进入 2880 |
| Q2-I-005 | 5 m 批量 strict classification 超时 | incremental/event-driven anchor propagation 将正式50→20→5 region-only从>300 s降至约56.5 s；legacy/incremental点状态、whole-cell状态及anchor sequence零差异 | C | RESOLVED | 后续完整1440继续使用incremental production path；保留legacy oracle回归 | Q2-robust-selection-v2.1 | 未采用KDTree/并行/近似；物理阈值0、eps认证精度和四态证书均不变；5 m仍有6个UNRESOLVED cells须保留 |
| Q2-I-006 | candidate convergence 与近优分支语义不一致 | 正式 1440 的 20 m→5 m selected 比较得到 relchg(T2)=0.00724、relchg(JD)=0.13077、relchg(JR)=0.13077，故当前 `assess_candidate_convergence` 判为 CANDIDATE_GRID_SENSITIVE；但局部 2.5 m 诊断显示 20 m/5 m 两选点附近存在连续的离散 C20 严格点链，且存在 `||S2-S1||=Lmin=50 m`、T2=10 s 的 strict+C20+M4/Gverify PASS 点，说明固定原点 cell-center 网格相位会使不同分辨率 selected 沿同一近优前沿迁移 | M+C | OPEN | 建模确认后再处理 | Q2-robust-selection-v2.1 | 不得通过放宽 1e-3 阈值解决。需明确：A) T12 candidate convergence 是否允许“同一近优连通分支+理论 T2 下界达到”的解释性 PASS；或 B) 若必须逐点指标收敛，则需重新定义候选离散/边界 refinement。确认前 T12=UNRESOLVED、禁止 2880 |

## P2

| 问题编号 | 标题 | 描述 | 负责人 | 状态 | 截止时间 | 关联版本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |

## P3

| 问题编号 | 标题 | 描述 | 负责人 | 状态 | 截止时间 | 关联版本 | 备注 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |
