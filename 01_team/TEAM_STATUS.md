# 团队状态

> 更新日期：2026-09-11
> 负责人：M + C

## 已完成/已验证

- Q1 有界角误差集合成员定位：VERIFIED
- 当前版本：Q1-set-membership-v1 / Q1-localization-v1
- 验证记录：03_results/q1/Q1_INDEPENDENT_VERIFICATION_REPORT.md

## 进行中

- Q2-robust-selection-v2.1 IMPLEMENTATION：M1--M5B 已实现，strict certificate 已 MODEL_ALIGNED。M6A.1 anchor propagation + shared physical tree 已通过 50 m benchmark（1190→82 full calls，约 1.24 s）；正式 M6A 尚未重跑，T12 仍 UNRESOLVED，M6B 不得开始。

## 待验证

- Q2 T12、1440→2880、candidate 整体收敛、Lmin 敏感性、`eps_rec_cert_m=1e-4/1e-3/1e-2` 正式全域敏感性与正式结果文件；T13--T17 中 T13/T14/T15/T16/T17 已通过。

## 阻塞问题

- 无模型冲突；strict certificate 的 50 m 性能瓶颈已显著缓解，但 Q2-I-002 保持 OPEN，直到完整 M6A 重跑通过。启动时仓库已有与本任务不重叠的 tools/results 未提交改动，须继续保留。

## 今天必须完成

- Q2 M1--M5B（已完成）；后续 M6 不得牺牲正确性抢进度。

## 当前冻结版本

- 当前版本：Q1-set-membership-v1 / Q1-localization-v1
- 模型版本：Q1-set-membership-v1
- 算法版本：Q1-localization-v1
- 代码位置：B_code/src/q1_localization.py
- 验证记录：03_results/q1/Q1_INDEPENDENT_VERIFICATION_REPORT.md
- 冻结副本：B_code/frozen/q1_localization_v1/（SHA256 与 signoff 源一致）
