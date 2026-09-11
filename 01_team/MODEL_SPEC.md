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
