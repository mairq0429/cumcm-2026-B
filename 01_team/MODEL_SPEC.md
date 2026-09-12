# 模型规格

允许的状态：`IDEA`、`DERIVED`、`CODED`、`TESTED`、`VERIFIED`。

## Q1

- Status：VERIFIED
- Version：Q1-set-membership-v1（2026-09-11）
- Inputs：观测序列 S_i=(x_i,y_i)、测得示向角 theta_i（角度制）。
- Outputs：目标可行区域 P_m、区域类型、面积、直径及端点、指定直径圆覆盖结果、最小包围圆（MEC）、光学保证与带安全裕度的可清除判定，以及异常诊断。
- Assumptions：每次示向误差满足 |epsilon_i| <= 1 degree；目标位于 x^2+y^2 <= 1800^2。
- Mathematical Model：P_m = D ∩ W_1 ∩ ... ∩ W_m；W_i 为 [theta_i-1 degree, theta_i+1 degree] 对应的角楔。原误差条件成立时 X_true ∈ P_m。
- Parameters：ANGLE_ERROR_DEG=1.0；TARGET_RADIUS_M=1800.0；CIRCLE_POLYGON_SIDES=720；OPTICAL_RADIUS_M=20.0；SAFETY_MARGIN_M=3.0；CLEAR_RADIUS_THRESHOLD_M=17.0。正式实现容差：EPS_GEO=1.8e-6、EPS_MERGE=1.8e-5、EPS_COLLINEAR=1.8e-5、EPS_PARALLEL=1.8e-9、EPS_AREA=3.24e-4、EPS_CONVEX=3.24e-4、EPS_AREA2=3.24e-4、EPS_COVER=1.8e-4、EPS_MEC=1.8e-4、EPS_DIAMETER_REL=1e-7、EPS_ANGLE_DEG=1e-6。
- Algorithm：用两个线性半平面表示每个角楔；用外切正 720 边形保守表示目标圆；逐半平面 Sutherland-Hodgman 裁剪；确定性增量算法求 MEC。共线点按点到直线距离不超过 EPS_COLLINEAR 且位于线段之间删除；裁剪近似平行判据使用 EPS_PARALLEL；旋转卡壳面积比较使用 EPS_AREA2，并以暴力法按 EPS_DIAMETER_REL 交叉验证。clearable=(R_MEC+EPS_MEC<=17 m)，within_optical_guarantee=(R_MEC+EPS_MEC<=20 m)，exists_diameter_cover_circle=|R_MEC-U_D/2|<=EPS_MEC。原始区域为空时，在半角小于 90 degree 的范围内二分搜索最小统一角松弛。
- Validation：角楔边界/跨 0 degree、外切目标域、正常/近平行/退化/异常案例、直径双算法、直径圆反例、MEC/Jung 界、1000 组 Monte Carlo 真源包含、逐观测单调收缩、N=360/720/1440 收敛与容差敏感性试验。
- References：本轮收到的“Q1 有界角误差集合成员定位模型”最终实现规格；官方来源仍按 SOURCE_OF_TRUTH.md 的优先级由团队后续交叉核验。
- Last Verified By：M + C（model-code consistency review, 2026-09-11）

## Q2

- Status：DERIVED
- Version：Q2-robust-selection-v2.1
- Inputs：第一次检测点 `S1`、第一次测得方位 `theta1_hat`、可选活动域 `Omega_move` 与队内数值配置。
- Outputs：`P1_bound/P1_phys` 元数据、连续域严格接收证书、各候选的 `JD/JR/JA/T2` 及分别对应的最坏场景、20 m 官方保证、17 m 队内操作判据、风险候选、Pareto 集、收敛与敏感性记录，以及可复核 `Fstrict` 区域。
- Assumptions：真实源位于半径 1800 m 圆域；两次示向误差各自位于 `[-1 degree,+1 degree]`；第一次已收到信号；近端阈值 5 m；真实固定接收半径为 `rho∈[1000,1500]`。给定物理源 `G` 且第一次在 `S1` 成功接收后，条件相容范围为 `rho∈[max(1000,||G-S1||),1500]`。
- Mathematical Model：`P1_bound=D∩W(S1,theta1_hat,1 degree)∩B(S1,1500)`；`P1_phys={G∈P1_bound: ||G||<=1800, 5<||G-S1||<=1500}`；`receive_floor(G)=max(1000,||G-S1||)` 仅表示与第一次成功接收相容的最小可能 `rho`，不是实际物理接收半径。定义 `Vrec(S2)=max_{G∈P1_phys}[||G-S2||-receive_floor(G)]`，严格鲁棒接收的物理条件固定为 `Vrec<=0`。程序通过 branch-and-bound 维护 `L_rec<=Vrec<=U_rec`：`U_rec<=0` 为 `CERTIFIED_STRICT`；`L_rec>0` 为 `CERTIFIED_VIOLATION` 并保留物理反例；`L_rec<=0<U_rec` 且 `U_rec-L_rec<=EPS_REC_CERT_M` 为 `UNCERTAIN_BOUNDARY`；其余在深度或单元预算耗尽时为 `UNRESOLVED`。只有 `CERTIFIED_STRICT` 令 `strict_receive=True` 并进入 `Cstrict`；后两种不确定状态均为 `None`，禁止静默排除。禁止以 `Q==1` 定义严格集。
- Second Observation：若 `||G-S2||<=5+Q1 EPS_GEO`，则 `NEAR_TERMINAL` 且 `P2=P1_bound∩B(S2,5)`，仍真实计算面积、直径与 MEC；否则 `theta2_hat=bearing(S2,G)+e2`、`e2∈[-1 degree,+1 degree]`，`P2=P1_bound∩W(S2,theta2_hat,1 degree)`，不得重新枚举第一次误差。通用评价器在已知 `rho` 且 `||G-S2||>rho` 时返回 `NO_SIGNAL`、`P2=P1_bound`。
- Objectives：`JD=max D(P2)`、`JR=max R_MEC(P2)`、`JA=max Area(P2)`，三个最坏场景分别保存；一致性要求 `D/2<=R_MEC<=D/sqrt(3)+tol`，并报告 `cover_by_diameter_circle=abs(2R_MEC-D)<=tol` 与 `gap=2R_MEC-D`。`official20=(JR+EPS_MEC<=20)`；`operational17=(JR+EPS_MEC<=17)`，正式 Q2 推荐仅使用 `official20`。`T2=||S2-S1||/5`，不加入完整 Q3 路径。
- Search and Selection：`Omega_move` 默认 `None`；无额外边界时搜索盒为 `bbox(P1_bound)` 四周各扩 1500 m。`Cstrict={certificate.status==CERTIFIED_STRICT and ||S2-S1||>=Lmin}`，默认 `Lmin=50 m`。`CERTIFIED_VIOLATION` 排除；`UNCERTAIN_BOUNDARY/UNRESOLVED` 必须继续细分、增加预算或显式报告，禁止静默作为 infeasible 丢弃。若 `C20` 非空按 `(T2,JR,JD,x,y)` 字典序选择；否则若 `Cstrict` 非空，先对 `(JR,JD,T2)` 作 tolerance-aware Pareto，再按 `(JR,JD,T2,x,y)` 选择；严格集为空时正式推荐为 `None`，风险点不得升级。
- Risk Area：`Qarea` 仅为 `P1_phys` 几何面积覆盖比例，不是概率且不定义严格集。`EPS_Q=max(1e-6,Earea/Area(P1_phys))`，`Earea` 必须来自真实面积积分或网格夹逼误差；可分别报告 `Q>=0.99/0.95` 风险点，但必须标记 `robust_guarantee=False`，其 `JD/JR` 只针对可再次接收子集。
- Frozen Requirements R1--R18：R1 上述 `P1_bound/P1_phys`；R2 严格物理过滤；R3 条件接收半径与严格不等式；R4 无目标圆 S2 限制及可配置 `Omega_move`；R5 全部基础几何和容差复用 Q1 VERIFIED；R6 `P1_out/P1_in` 双近似且正式结果用外包；R7 `Gext/Garea/Gverify` 分离；R8 2-Lipschitz 三角单元连续域证书且不把物理非法点当反例；R9 near 与普通第二观测定义；R10 `NO_SIGNAL` 语义；R11 `JD/JR/JA`、独立最坏场景与 MEC 一致性；R12 官方 20 m 与队内 17 m 分离；R13 `T2` 定义及 Q3 集成时间仅诊断；R14 第二误差 0.1→0.05 degree 自适应收敛；R15 source 20→10→5 m 与独立 `Gverify`；R16 candidate 50→20→5 m、所有近优连通分支、FIM 只排序；R17 `Qarea/Earea`、风险候选及真正区域形式 `Fstrict.geojson`；R18 tolerance-aware Pareto、`Lmin=20/50/100/150 m` 敏感性、1440→2880 圆近似收敛、规定输出与 T01--T17。
- Parameters：官方参数为 1800 m、示向误差 `+/-1 degree`、接收半径 1000--1500 m、near `<=5 m`、测量 5 s、速度 5 m/s、清除 `<=20 m`。队内数值认证参数 `EPS_REC_CERT_M=1e-3 m` 已由建模手冻结，仅控制证书区间终止精度，不是物理容差、接收半径放宽、Q1 几何容差或官方参数。其余队内参数为 `circle_sides=1440`、`source_step=20 m`、`error_step=0.1 degree`、candidate grid 50/20/5 m、`Lmin=50 m`、17 m、0.99/0.95 及 Q1 `DEFAULT_TOLERANCES`；均不得写成官方参数。
- Algorithm：圆盘正式用外切正 1440 边形，并同时算内接多边形夹逼；检查 1440→2880 的 area、JD、JR、Fstrict 与选点坐标。严格证书采用三角单元 branch-and-bound：物理合法确定性样本给出 `L_rec`，仍可能与 `P1_phys` 相交的活动/叶单元以 `f(Gc)+2h` 给出上界并聚合为 `U_rec`；`EPS_REC_CERT_M` 只用于判断跨零区间宽度是否已达到认证精度，不改变零物理阈值。性能实现利用 `V_rec` 对 S2 的 1-Lipschitz 性传播多个已认证 anchor 的上下界，并惰性共享仅依赖 P1/S1 的物理三角树；传播与共享树均为严格等价证书，不改变四态判据。误差、源样本和候选网格分别加密；只称“场景加密后的收敛数值最坏值”，不称连续解析全局最大值。
- Validation：T01--T11 已覆盖 M1--M3；M4 的 T13 独立 `Gverify`、T14 最坏场景 replay、T17 source/error convergence 已覆盖并通过；M5A 的 T15 选择规则与 T16 全链路物理过滤已覆盖并通过；M5B 已完成面积上下界、阈值三态、确定性稠密 oracle、received-subset worst 与独立 Gverify implementation tests。严格证书零阈值专项覆盖微小正反例、微小负上界、跨零窄区间、预算耗尽、M5A 点/整格排除及 Gverify 微小正违反；M6A.1 另以 30 个 deterministic S2 检查 legacy/accelerated 无相反确定结论，并覆盖传播代数、整格传播、oracle bound consistency、tree reuse 与三精度零阈值不变性。50 m acceleration benchmark 已通过，但正式 M6A 尚未重跑。正式计算前仍须对 `EPS_REC_CERT_M=1e-4/1e-3/1e-2 m` 做敏感性检查。T12 仍为 UNRESOLVED；最终仍需圆盘、source、error、candidate 四类收敛及 `Lmin=20/50/100/150 m` 敏感性。
- References：《B题第二问鲁棒选点模型编程规格书 v2.1 建模确认清单冻结版》。
- Last Verified By：尚未验证；当前实现已完成 M1--M5B，严格接收证书语义已 MODEL_ALIGNED；M6A 判定框架已实现，但代表性全域 1440 基线因有界运行窗口耗尽而保持 UNRESOLVED，M6 及最终交叉验证未完成。

## Q3

- Status：IDEA
- Version：待填写
- Inputs：待填写
- Outputs：待填写
- Assumptions：待填写
- Mathematical Model：待填写
- Parameters：待填写
- Algorithm：待填写
- Validation：待填写
- References：待填写
- Last Verified By：待填写

## Q4

- Status：IDEA
- Version：待填写
- Inputs：待填写
- Outputs：待填写
- Assumptions：待填写
- Mathematical Model：待填写
- Parameters：待填写
- Algorithm：待填写
- Validation：待填写
- References：待填写
- Last Verified By：待填写
