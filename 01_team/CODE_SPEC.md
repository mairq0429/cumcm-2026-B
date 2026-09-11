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

- 对应 MODEL_SPEC 版本：待填写
- 源代码文件：待填写
- 函数：待填写
- 输入输出：待填写
- 测试文件：待填写
- 算法版本：待填写
- 状态：待填写

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
