# 统一交接日志

## 交接记录

- handoff id：Q1-C-MW-20260911-01
- 时间：2026-09-11
- 发送人：C（编程实现）
- 接收人：M/W（建模/写作）
- 问题编号：Q1
- 版本：Q1-localization-v1
- 结论：有界角误差集合成员定位独立模块已实现并通过本地测试，未接入 Q3。
- 输入：[{"x": float, "y": float, "theta_deg": float}, ...]
- 输出：可行区域、退化类型、面积、直径证书、指定直径圆覆盖、MEC、20 m 光学保证、17 m 操作阈值、松弛诊断。
- 公式：P_m=D∩W_1∩...∩W_m；clearable=(R_MEC+EPS_MEC<=17 m)；within_optical_guarantee=(R_MEC+EPS_MEC<=20 m)。
- 参数：官方参数为 1 degree 示向误差界、1800 m 目标区域半径和 20 m 光学清除半径；EPS_MEC=1.8e-4 m。外切正 720 边形、3 m 队内安全裕度、17 m 操作阈值及数值容差均为本队模型/程序参数，不是官方参数。
- 程序要求：实现 B_code/src/q1_localization.py；测试位于 B_code/tests/test_q1_localization.py；保持 B_code/frozen/q3_baseline_v1/** 零修改。
- 验证方法：18 项 unittest；1000 组固定 seed Monte Carlo；300 个随机凸多边形直径双算法；单调收缩；N 收敛；容差 0.1x/1x/10x 敏感性。
- 影响论文章节：问题一定位区域、定位不确定性与清除判据；17 m 应表述为队内操作阈值而非官方物理阈值。
- 状态：TESTED（待团队交叉验证，不得标记 VERIFIED）
- 尚未解决风险：官方题面/附件参数仍需按 SOURCE_OF_TRUTH.md 由团队交叉核验；REPAIRED 是否允许未来自动进入 Q3 clear 流程尚未决定，本实现未作 Q3 集成。

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
