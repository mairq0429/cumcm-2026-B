# 团队状态

> 更新日期：2026-09-11
> 负责人：M + C

## 已完成/已验证

- Q1 有界角误差集合成员定位：VERIFIED
- 当前版本：Q1-set-membership-v1 / Q1-localization-v1
- 验证记录：03_results/q1/Q1_INDEPENDENT_VERIFICATION_REPORT.md

## 进行中

- Q3-improved-v1: Q3I-01 COMPLETE; Q3I-02 COMPLETE; Q3I-03 COMPLETE; Q3I-04
  COMPLETE after the independent MEC oracle, OUTER-corner containment replay,
  revision/stale checks and joint true-source certificate Monte Carlo; Q3I-05
  NOT_STARTED. Scope is Problem 3 omnidirectional sources only. Overall status
  remains CODED=NO, TESTED=NO, VERIFIED=NO.

- Q2-robust-selection-v2.1 IMPLEMENTATION：M1--M5B 已实现，strict certificate 已 MODEL_ALIGNED。M6A.1 anchor propagation + shared physical tree 已通过 50 m benchmark（1190→82 full calls，约 1.24 s）。正式 M6A 已按加速路径重启，但 1440 完整 50→20→5 配置在 300 s watchdog 内未完成；新瓶颈为粗层大量完整 M4 评价。T12 仍 UNRESOLVED，M6B 不得开始。
- Q2 M6A.2 lazy objective benchmark：1440/50 m 全域的 1184 strict objective candidates 仅调用 6 次完整 M4，2 次由 cheap C20 下界拒绝，1176 次在已有 C20 后按严格 T2 次序跳过；总耗时约 9.54 s。该结果只覆盖 50 m benchmark，尚未重跑完整 M6A，T12 仍 UNRESOLVED。
- Q2 M6A.3：1440 baseline 已启动并逐级保存证据；50 m、20 m 完成，5 m 在 300 s 单级 watchdog 内未完成。未形成最终 5 m selected，未执行独立 selected revalidation，2880 未运行；T12=`UNRESOLVED`，M6B 禁止进入。
- Q2 M6A.4 sparse generation PASS：20 m legacy/sparse 均为3883 cells；5 m 由991 region parents生成17292 cells，missing/extra=0，约0.512 s。5 m region-only strict classification 仍超300 s，下一瓶颈为批量 anchor propagation/certificate classification。
- Q2 M6A.5 incremental anchor propagation PASS：legacy oracle 与 incremental 三批次的点状态、whole-cell状态及anchor序列零差异；正式5 m region-only复用246个既有anchors、新增881个full anchors，完成17292 cells分类，整套50→20→5 region-only约56.5 s（原>300 s），且M4=0。5 m结果为strict 9432、violation 150、uncertain-boundary 0、unresolved 6；本轮不重跑完整1440，T12仍UNRESOLVED。
- Q2 M6A.6 unresolved-competitive gate 已实现并通过回归。完整1440代表性 baseline 已于84.03 s完成：6个最终UNRESOLVED cells全部为noncompetitive，gate=`PASS_NONCOMPETITIVE_UNRESOLVED`；selected独立复核、source/error、Gverify、JD/JR/JA replay及monotone均PASS。但20→5的T2/JD/JR relchg分别为0.00724/0.13077/0.13077，故`CANDIDATE_GRID_SENSITIVE`，1440状态与T12保持UNRESOLVED，禁止进入2880。
- Q2 M6A.7a Lmin boundary radial projection diagnostic：将20m/5m selected按公式投影到`||S2-S1||=50m`后，两个点均以fresh P1通过CERTIFIED_STRICT、完整M4、source/error、Gverify与JD/JR/JA replay，且重新满足official20/operational17。故代表性案例存在boundary C20 witness，并由Lmin证明`T2*=10s`；这是VALIDATION/DIAGNOSTIC，不改变全局selection rule、T12或1440 candidate-grid sensitivity状态。
- Q2 M6A.7b Lmin-circle branch discovery：因1度预计需302次完整M4，采用允许的2度全圆扫描。180个角全部CERTIFIED_STRICT；30个由cheap screen证明非C20，150个经完整M4成为STRICT_C20，形成两个sampled connected arcs：4--152度与208--356度。诊断最小JR样本在314度（JR=5.389448m），仅作为M6A.7c refinement seed，不作最终secondary optimum签字；2880/M6B未运行。

## 待验证

- Q2 T12、1440→2880、candidate 整体收敛、Lmin 敏感性、`eps_rec_cert_m=1e-4/1e-3/1e-2` 正式全域敏感性与正式结果文件；T13--T17 中 T13/T14/T15/T16/T17 已通过。

## 阻塞问题

- 无模型冲突；strict certificate 性能瓶颈已解决，但完整 M6A 的 coarse-objective M4 工作量仍超过单配置 watchdog，Q2-I-002 保持 OPEN。启动时仓库已有与本任务不重叠的 tools/results 未提交改动，须继续保留。

## 今天必须完成

- Q2 M1--M5B（已完成）；后续 M6 不得牺牲正确性抢进度。

## 当前冻结版本

- 当前版本：Q1-set-membership-v1 / Q1-localization-v1
- 模型版本：Q1-set-membership-v1
- 算法版本：Q1-localization-v1
- 代码位置：B_code/src/q1_localization.py
- 验证记录：03_results/q1/Q1_INDEPENDENT_VERIFICATION_REPORT.md
- 冻结副本：B_code/frozen/q1_localization_v1/（SHA256 与 signoff 源一致）
