# 变更日志

| 时间 | 修改人 | 修改内容 | 旧值 | 新值 | 原因 | 影响代码 | 影响论文 | 是否需要重新测试 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2026-09-11 | C（编程实现） | 新增 Q1 有界角误差集合成员定位、完整测试与规格同步 | Q1 无独立实现，规格占位 | Q1-localization-v1，状态 TESTED（未 VERIFIED） | 实现问题一最终规格并提供可复现数值证书 | B_code/src/q1_localization.py、B_code/tests/test_q1_localization.py | Q1 模型、算法、阈值解释及验证数据 | 是；本轮 18 项测试已通过，仍需团队交叉验证 |
| 2026-09-11 | Codex（编程实现） | 启动 Q2-robust-selection-v2.1，完成 M1--M3 与 T01--T11；冻结 Q1 verified 源 | Q2 规格占位、无正式模块 | Q2 DERIVED；M1--M3 implemented；Q1 freeze | 按建模确认清单冻结版逐里程碑实现，保留 M4--M6 为未完成 | B_code/src/q2_selection.py、B_code/tests/test_q2_selection.py、B_code/frozen/q1_localization_v1 | Q2 正式模型与 R1--R18 | 是；T12--T17 与全部收敛实验仍待完成 |
| 2026-09-12 | Codex（编程实现） | 完成 Q2 M4 单候选嵌套最坏场景引擎、独立 Gverify 与 replay | M1--M3，无嵌套收敛引擎 | M1--M4 implemented；T13/T14/T17 PASS | 按 source-outer/error-inner 顺序实现确定性收敛与独立验证 | B_code/src/q2_selection.py、B_code/tests/test_q2_selection.py | Q2 M4 数值最坏评价与可追溯场景 | 是；完整测试通过，T12 仍等待 M6 |
| 2026-09-12 | Codex（编程实现） | Q2 M4.1 加固真实物理边界、Gverify worst merge 与非平凡 stress cases | P1_out 边界/shifted grid，verify 仅检查不吸收 | 显式 1800/1500/5+eta 圆弧；validated worst；B/C/D stress | 防止真实圆边界与独立验证中新极值遗漏 | B_code/src/q2_selection.py、B_code/tests/test_q2_selection.py | 不改变 Q2 模型，仅加固 M4 数值实现 | 是；完整测试与保护检查必须通过 |
| 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 | 待填写 |
