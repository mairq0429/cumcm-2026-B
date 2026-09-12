# 统一交接日志

## 交接记录

- handoff id：Q1-C-MW-20260911-01
- 时间：2026-09-11
- 发送人：C（编程实现）
- 接收人：M/W（建模/写作）
- 问题编号：Q1
- 版本：Q1-localization-v1
- 结论：有界角误差集合成员定位独立模块已实现并完成验证，未接入 Q3。
- 输入：[{"x": float, "y": float, "theta_deg": float}, ...]
- 输出：可行区域、退化类型、面积、直径证书、指定直径圆覆盖、MEC、20 m 光学保证、17 m 操作阈值、松弛诊断。
- 公式：P_m=D∩W_1∩...∩W_m；clearable=(R_MEC+EPS_MEC<=17 m)；within_optical_guarantee=(R_MEC+EPS_MEC<=20 m)。
- 参数：官方参数为 1 degree 示向误差界、1800 m 目标区域半径和 20 m 光学清除半径；EPS_MEC=1.8e-4 m。外切正 720 边形、3 m 队内安全裕度、17 m 操作阈值及数值容差均为本队模型/程序参数，不是官方参数。
- 程序要求：实现 B_code/src/q1_localization.py；测试位于 B_code/tests/test_q1_localization.py；保持 B_code/frozen/q3_baseline_v1/** 零修改。
- 验证方法：18 项 unittest；1000 组固定 seed Monte Carlo；300 个随机凸多边形直径双算法；单调收缩；N 收敛；容差 0.1x/1x/10x 敏感性；独立验证报告 03_results/q1/Q1_INDEPENDENT_VERIFICATION_REPORT.md。
- 实现提交：18fb837ff2ca0f8426b68a730fd82a906f4d645b
- 文档对齐提交：6100162eb574c2a278519ca556203dd7d3720b35
- 影响论文章节：问题一定位区域、定位不确定性与清除判据；17 m 应表述为队内操作阈值而非官方物理阈值。
- 状态：VERIFIED
- 尚未解决风险：REPAIRED 是否允许未来自动进入 Q3 clear 流程尚未决定，本实现未作 Q3 集成。

- handoff id：Q3I-02-C-MW-20260912-01
- 时间：2026-09-12
- 发送人：C（编程实现）
- 接收人：M/W（建模/写作）
- 问题编号：Q3
- 版本：Q3-improved-v1 / Q3I-02
- 结论：完成 normalized protocol adapter、六态频道状态机、20×7 coverage、`900*sqrt(3)` 七点确定性调度、terminal certificate 与可读历史 console replay；未进入 Q3I-03。
- 适用范围：仅问题三全向源；七点缺席证书不得复用于定向源。
- 验证方法：Q3I-02 S01--S18、C01 integration、C02、C03、C06、七点坐标与 dense-grid sanity、历史 console clear 计数 replay。
- 状态：阶段 COMPLETE；整体 CODED=NO / TESTED=NO / VERIFIED=NO。

- handoff id：Q3I-03-C-MW-20260912-01
- 时间：2026-09-12
- 发送人：C（编程实现）
- 接收人：M/W（建模/写作）
- 问题编号：Q3
- 版本：Q3-improved-v1 / Q3I-03
- 结论：完成不可变频道几何观测、固定未知接收半径点级一致性、保守整盒排除与可预算重建的 adaptive axis-aligned OUTER；未实现 MEC、fallback、主动选点或 P1。
- 安全不变量：保留盒仅表示 RETAINED_UNCERTAIN；预算耗尽保留粗盒；clear `no_target_in_range` 仅经 Q3I-02 先验存在性 guard 后进入几何历史。
- 验证方法：C01 box regression、C04/C05、全部要求的距离/严格端点边界、1000-case 独立 fixed-R point oracle、1000-case 逐观测 true-source OUTER containment、确定性 rebuild 与 budget-zero 保留测试。
- 状态：Q3I-03 COMPLETE；Q3I-04 NOT_STARTED；整体 CODED=NO / TESTED=NO / VERIFIED=NO。

- handoff id：待填写
- 时间：待填写
- 发送人：待填写
- 接收人：待填写
- 问题编号：待填写
- 版本：待填写
- 结论：待填写
- 输入：待填写
- 输出：待填写
- 公式：待填写
- 参数：待填写
- 程序要求：待填写
- 验证方法：待填写
- 影响论文章节：待填写
- 状态：待填写
# 2026-09-12 Q2 M6A.6 handoff

- 基线：`9afce0061447b3a376b982213bbb220cd3cd269f`（当前分支另含不相交Q3审计commit）。
- M6A.6 gate COMPLETE：最终5m的6个UNRESOLVED cells全部为noncompetitive；0 targeted rechecks；uncertainty polygons仍保留于Fstrict验证输出。
- 完整1440代表性运行完成，runtime 84.03 s。5m selected=`(1727.5,-42.5)`，T2=10.1242284，JD=10.9187415，JR=5.45937077，JA=17.3078593，official20/operational17均true。
- 独立source/error convergence、Gverify、JD/JR/JA replay、monotone均PASS。
- 阻塞：20→5 relchg(T2,JD,JR)=0.0072377/0.130774/0.130774，状态`CANDIDATE_GRID_SENSITIVE`。因此1440/T12=`UNRESOLVED`，`entry_to_2880_comparison=false`；2880、eps sensitivity、Lmin sensitivity均NOT_RUN。
