# 代码规格

## Q1

- 对应 MODEL_SPEC 版本：Q1-set-membership-v1（VERIFIED）
- 源代码文件：B_code/src/q1_localization.py
- 公开主函数：q1_localize(observations, *, tolerances=DEFAULT_TOLERANCES, circle_polygon_sides=720) -> dict
- 输入：observations 为若干 {"x": float, "y": float, "theta_deg": float}；正常生产计算保留固定默认 N=720，circle_polygon_sides 仅用于收敛试验。
- 输出：至少含 status、polygon、region_type、area、diameter、diameter_endpoint_A/B、diameter_circle_center、diameter_circle_covers、exists_diameter_cover_circle、mec_center、mec_radius、within_optical_guarantee、clearable、relaxation_deg、certificate_under_original_bound、diagnostics。diameter_length_cover_exists 暂作为 exists_diameter_cover_circle 的兼容别名。
- 区域类型：EMPTY、POINT、SEGMENT、POLYGON。
- 状态码：NORMAL 表示原始 +/-1 degree 区域有效；REPAIRED 表示仅在最小统一角松弛下得到诊断区域；INCONSISTENT 表示允许松弛范围仍为空或内部几何验证失败。仅 NORMAL 的 certificate_under_original_bound=True。
- 模型常量：ANGLE_ERROR_DEG=1.0、TARGET_RADIUS_M=1800.0、CIRCLE_POLYGON_SIDES=720、OPTICAL_RADIUS_M=20.0、SAFETY_MARGIN_M=3.0、CLEAR_RADIUS_THRESHOLD_M=17.0。clearable 严格按 mec_radius+EPS_MEC <= 17.0；within_optical_guarantee 按 mec_radius+EPS_MEC <= 20.0。
- 正式数值容差：EPS_GEO=1.8e-6、EPS_MERGE=1.8e-5、EPS_COLLINEAR=1.8e-5、EPS_PARALLEL=1.8e-9、EPS_AREA=3.24e-4、EPS_CONVEX=3.24e-4、EPS_AREA2=3.24e-4、EPS_COVER=1.8e-4、EPS_MEC=1.8e-4、EPS_DIAMETER_REL=1e-7、EPS_ANGLE_DEG=1e-6。各调用点按语义分别使用，不以通用长度容差代替。
- 公开验证工具：wedge_halfplanes、circumscribed_circle_polygon、half_plane_clip、classify_region、rotating_calipers_diameter、brute_force_diameter、minimum_enclosing_circle、analyze_convex_region、point_in_convex_region。
- 异常行为：输入缺字段、不可转为浮点或非有限数时抛 ValueError；原区域为空不隐藏，进入最小松弛诊断；内部凸性、直径双算法、MEC 覆盖或 Jung 界失败时写入 diagnostics.validation_failures 并抑制原界证书。
- 测试文件：B_code/tests/test_q1_localization.py
- 测试入口：python -m unittest discover -s B_code/tests -p "test_*.py" -v
- 算法版本：Q1-localization-v1
- 状态：CODED=YES, TESTED=YES, VERIFIED=YES
- INDEPENDENT_VERIFICATION=PASS
- MODEL_CODE_CONSISTENCY=PASS

### Q1 -> Q3 integration contract

未来 Q3 仅可读取 Q1 输出中的：status、mec_center、mec_radius、clearable、certificate_under_original_bound、polygon、observations。

仅当 status=NORMAL 且 clearable=True 时，才具备正式集合定位清除证书。REPAIRED 暂不得自动授权 Q3 clear，等待团队后续决定。本契约不定义新的 Q3 策略，也不修改现有 baseline。

## Q2

- 对应 MODEL_SPEC 版本：Q2-robust-selection-v2.1（DERIVED）
- 源代码文件：B_code/src/q2_selection.py
- 公开主函数：solve_q2(S1, theta1_hat_deg, config=None) -> dict
- 公开构件：Q2Config、SourceScenario、CandidateResult、WorstScenario、Q2Result、CandidateCell、AreaIntegrationCell、AreaCoverageResult、RiskCandidateResult、bearing、wrap_pi、build_P1_bound、physical_filter、receive_floor、receive_violation、classify_receive_certificate_bounds、sample_receive_screen、strict_gverify_receive_status、certified_strict、make_P2、build_Gext、build_Gverify、build_Garea、build_error_grid、relchg、fim_order_score、evaluate_candidate_resolution、evaluate_candidate_nested、replay_worst_scenario、search_strict_candidates、select_from_evaluated、run_eps_rec_cert_sensitivity、integrate_qarea、classify_risk_threshold、evaluate_risk_candidate、evaluate_risk_received_subset、evaluate_risk_candidates、write_m5b_outputs，以及保留的兼容评价接口。
- 输入输出：输入第一次检测点/示向及配置；M1--M3 输出 P1 外/内近似、物理过滤、连续域严格接收证书和单场景 P2 的 status/area/diameter/MEC/一致性诊断。M4 已实现单个给定 S2 的 source-outer/error-inner 嵌套最坏评价；M5A/M5A.1 已实现 strict 候选自适应搜索及 region/objective 双细化链；M5B 已实现开发态几何风险面积证书、阈值三态和 received-subset worst。Lmin 敏感性、整体收敛与正式结果属于 M6，尚未实现。
- 依赖：Q1-localization-v1 VERIFIED；直接复用 `DEFAULT_TOLERANCES`、wedge/circle/clip/clean/classify/diameter/MEC/area/point-membership 公共实现。Q2 默认圆分辨率 1440，不改变 Q1 默认 720。
- 接收半径语义：实际物理量是固定但未知的 `rho∈[1000,1500]`；第一次在 `S1` 成功接收后，`receive_floor(G)=max(1000,||G-S1||)` 仅为条件相容的最小可能 `rho`，不是实际接收半径。
- 数值证书：严格接收的物理阈值固定为 `Vrec<=0`。Q1 `DEFAULT_TOLERANCES` 仅用于底层几何。`Q2Config.eps_rec_cert_m=1e-3 m` 的来源为 `MODEL_FROZEN_CERTIFICATION_PRECISION`，是队内数值认证精度，只用于跨零证书区间的终止判据 `U_rec-L_rec<=eps_rec_cert_m`，绝不放宽物理阈值。`eps_rec_m` 仅保留为 deprecated alias；内部与输出均使用 `eps_rec_cert_m/eps_rec_cert_source`。
- 严格证书边界：branch-and-bound 用所有已验证物理合法样本的最大 `f(G)` 维护 `L_rec`（无样本时为 `-inf`），用所有仍可能包含物理源的活动/叶单元 `f(Gc)+2h` 最大值维护 `U_rec`。状态依次为：`U_rec<=0 -> CERTIFIED_STRICT`；`L_rec>0 -> CERTIFIED_VIOLATION` 且保存物理反例；`L_rec<=0<U_rec` 且区间宽度不超过认证精度时为 `UNCERTAIN_BOUNDARY`；预算/深度耗尽且区间仍宽为 `UNRESOLVED`。后两者均 `certified=False, strict_receive=None`，不得进入 `Cstrict` 或静默作为 infeasible 排除。`S2=S1` 使用解析证书 `U_rec=0`，不依赖认证精度。
- M4 源样本：`build_Gext` 生成物理过滤后的 vertex/boundary/interior 样本，并显式按弧长步长采样 `||G||=1800`、`||G-S1||=1500` 和 `||G-S1||=5+eta(level)` 的真实物理边界；通过保留 previous 保证 20→10→5 m 嵌套。`eta=0.1*source_level` 仅为趋近开边界的实现采样量，不是官方或已验证模型参数。`build_Gverify` 使用最终步长一半的 shifted grid、错位 P1 边界及独立 1/2 相位物理圆弧采样，短弧使用 1/4、3/4 双错相位，并确定性排除最终 Gext 坐标。每个 `SourceScenario` 记录 sample_set、source_level_m、origin、near_limit_eta_m。
- M4 误差与评价：`build_error_grid` 始终包含 -1/0/+1 degree，并保证 0.1→0.05→0.025... 嵌套。`evaluate_candidate_resolution` 对 near 只评价一次，对普通场景遍历完整误差网格；`evaluate_candidate_nested` 在每一 source level 内先完成 JD/JR error convergence，再比较 source convergence，最后进入独立 Gverify。输出措辞固定为“场景加密后的收敛数值最坏值”。
- M4 最坏场景与 replay：JD/JR/JA 分别保存扩充后的 `WorstScenario`，包括 G/e2/status/theta/三项几何/MEC center/support/source level/sample set/origin；Gverify 完成后按指标分别执行 `validated=max(optimizer,verify)`，若 verify 更大则最终 CandidateResult 和 WorstScenario 均替换为 Gverify 场景，同时保留 optimizer_worst、verify_worst、validated_worst。`replay_worst_scenario` 用 Q1 容差重算最终 validated worst 并逐项核对。TQ3 移动时间仅随最坏场景记录，不参与评价或排序。
- M4 最终性：robust pass 除要求 source convergence、error convergence 和独立 Gverify 均 PASS 外，还要求 certificate 恰为 `CERTIFIED_STRICT`；`UNCERTAIN_BOUNDARY/UNRESOLVED` 均不得输出 `CONVERGED_ROBUST`。已认证 strict 候选的任何 Gverify 物理样本若 `receive_violation>0`，即使仅 `+1e-6 m`，也返回 `GVERIFY_FAIL_RECEIVE`。最终阈值仍基于 validated JR；证书结果携带实际 `eps_rec_cert_m`、来源及零物理阈值。
- M5A 候选搜索：`search_strict_candidates` 在 `Omega_move` 缺省时使用 `bbox(P1_bound)` 四周扩 1500 m 的搜索盒，并按 50→20→5 m 建立带稳定 level/ix/iy/center/bbox ID 的候选单元。Stage A 对物理合法 Gext 使用严格零阈值：`margin>0` 即为中心点真实反例；只有 `margin-r_S2>0` 才能安全排除整格。Stage B 再调用连续域 `certified_strict`。`UNCERTAIN_BOUNDARY` 与 `UNRESOLVED` 一样进入区域细化链且不进入 Cstrict。
- M5A.1 双细化链：`region_cells` 与 `objective_cells` 使用独立父单元集合。区域链中只有 `cell_exclusion_certified=True` 的整格安全违规/Lmin 排除单元可停止；point strict、UNRESOLVED、无整格证书的 point violation、Lmin boundary 和 Omega 边界相交格均继续到 5 m。目标链仍按 near-optimal strict connected branches、C20 的 T2 单元下界及无 C20 时的保守 Pareto 潜在分支细化；只有目标链中的 `CERTIFIED_STRICT` 点调用完整 M4。结果及 diagnostics 分别记录 region/objective 各级单元、certificate calls 和 M4 calls。
- M5A 选择与输出：`Cstrict` 仅含 strict certificate、M4 CONVERGED 且满足 Lmin 的 objective 候选；`C20` 使用吸收 Gverify 后的 validated JR。C20 非空按 `(T2,JR,JD,x,y)`；否则先作 tolerance-aware Pareto(JR,JD,T2)，再按 `(JR,JD,T2,x,y)`。开发输出位于 `03_results/q2/m5_dev/`；`Fstrict.geojson` 基于 region refinement 的最终 5 m 层，将 strict 中心写为 `point_certified` Point，将 boundary/unresolved/uncertain-boundary 单元另写为 `uncertainty_cell` Polygon，不把中心证书虚构为整格证书。Omega 使用保守 cell-bbox/polygon 相交判断，中心在域外的相交格只作为 uncertainty。全部标记 `DEVELOPMENT / NOT_FINAL_Q2_RESULT / MODEL_FROZEN_CERTIFICATION_PRECISION`。
- M5B 面积积分：`build_Garea/integrate_qarea` 是与 Gext/Gverify 完全分离的确定性 adaptive square-cell 面积体系，不使用点数比例或边界采样权重。矩形对 P1 凸多边形采用角点内含与安全分离，对 1800/1500/5 m 圆约束采用 box 最小/最大距离界；接收集合严格使用 `receive_violation<=0`，以 2-Lipschitz cell 上下界分类。只细化 physical/receive UNCERTAIN 单元，输出 `Aphys/Arecv` 上下界和中点估计、`Earea_phys/Earea_recv/Earea`、`EPS_Q=max(1e-6,Earea/Aphys_est)` 与 Q 比例区间。`area_step_m=40`、`area_q_tol=1e-2`、refine rounds/cell budget 均为 IMPLEMENTATION_PARAMETER，不是官方或模型冻结参数。
- M5B 风险语义：0.99/0.95 分别按 `Q_lower>=alpha`、`Q_upper<alpha` 或夹跨阈值输出 `CERTIFIED_ABOVE_ALPHA/CERTIFIED_BELOW_ALPHA/THRESHOLD_UNRESOLVED`，不得用 Qarea estimate 或 EPS_Q 放宽进入风险集。风险 JD/JR/JA 只在 `receive_violation<=0` 的 Gext/Gverify 子集上作 source/error 加密，并合并独立 Gverify worst；未接收源不生成 P2、不作为 NO_SIGNAL 有限惩罚。所有风险结果 `robust_guarantee=False`，不得进入 Cstrict；本轮只输出 C099/C095 开发 shortlist，不定义正式风险推荐排序。
- M5B 输出：`03_results/q2/m5b_dev/` 的 coverage/risk CSV、`Frisk099/095.geojson` 和两类 diagnostics 均标记 `DEVELOPMENT / NOT_FINAL_Q2_RESULT / GEOMETRIC_AREA_NOT_PROBABILITY`，且不覆盖或改变 Fstrict。
- 测试文件：B_code/tests/test_q2_selection.py
- 算法版本：Q2-selection-v2.1（开发中，当前完成 M1--M5B）
- 状态：CODED=NO, TESTED=NO, VERIFIED=NO；M1--M5B COMPLETE，strict certificate semantics=MODEL_ALIGNED；T01--T11、T13--T17 中 T13/T14/T15/T16/T17 及 M5B implementation tests 已通过；T12 保持 PARTIAL/NOT_RUN。M6、整体离散收敛、`eps_rec_cert_m=1e-4/1e-3/1e-2` 正式全域敏感性与最终交叉验证未完成，不得自行标记 VERIFIED。
- M6A validation：`B_code/src/q2_m6_validation.py` 提供 circle/candidate/eps-cert/Lmin 判定、T12 门控聚合、风险阈值未决保持和八项 validation 输出。代表性全搜索盒 `S1=(1700,0), theta1=0 degree` 的 1440 基线在 300 s 有界运行窗口内未完成；未降低任何标准，T12 与 M6A 保持 `UNRESOLVED`，M6B 不得开始。runtime profile 位于 `03_results/q2/m6_validation/`。

## Q3

- 对应 MODEL_SPEC 版本：待填写
- 源代码文件：待填写
- 函数：待填写
- 输入输出：待填写
- 测试文件：待填写
- 算法版本：待填写
- 状态：待填写

## Q4

- 对应 MODEL_SPEC 版本：待填写
- 源代码文件：待填写
- 函数：待填写
- 输入输出：待填写
- 测试文件：待填写
- 算法版本：待填写
- 状态：待填写
