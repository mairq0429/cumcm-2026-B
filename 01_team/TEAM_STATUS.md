# 团队状态

> 更新日期：2026-09-11
> 负责人：M + C

## 已完成/已验证

- Q1 有界角误差集合成员定位：VERIFIED
- 当前版本：Q1-set-membership-v1 / Q1-localization-v1
- 验证记录：03_results/q1/Q1_INDEPENDENT_VERIFICATION_REPORT.md

## 进行中

- Q2-robust-selection-v2.1 IMPLEMENTATION：M1--M5B 已实现，包括 M5A.1 双细化链与 M5B geometric risk-area engine；strict certificate 已按零物理阈值与四态区间证书完成 MODEL_ALIGNED。M6A 判定/输出框架已实现，但正式代表性全域运行因 300 s 窗口耗尽而 UNRESOLVED；M6A 未完成，M6B 不得开始。

## 待验证

- Q2 T12、1440→2880、candidate 整体收敛、Lmin 敏感性、`eps_rec_cert_m=1e-4/1e-3/1e-2` 正式全域敏感性与正式结果文件；T13--T17 中 T13/T14/T15/T16/T17 已通过。

## 阻塞问题

- 无模型冲突；M6A 当前受全域 strict certificate 运行量阻塞。启动时仓库已有与本任务不重叠的 tools/results 未提交改动，须继续保留。

## 今天必须完成

- Q2 M1--M5B（已完成）；后续 M6 不得牺牲正确性抢进度。

## 当前冻结版本

- 当前版本：Q1-set-membership-v1 / Q1-localization-v1
- 模型版本：Q1-set-membership-v1
- 算法版本：Q1-localization-v1
- 代码位置：B_code/src/q1_localization.py
- 验证记录：03_results/q1/Q1_INDEPENDENT_VERIFICATION_REPORT.md
- 冻结副本：B_code/frozen/q1_localization_v1/（SHA256 与 signoff 源一致）
