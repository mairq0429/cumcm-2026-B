# Q1 Independent Verification Report

- Verification version：Q1-independent-v1
- Result：VERIFICATION_PASS
- Project status：CODED=YES, TESTED=YES, VERIFIED=NO

## True-source independent test

- 1000 cases，0 failures，first_failure_seed=None。
- Oracle 在验证脚本内独立计算角楔叉积、1800 m 圆域约束和返回 CCW 多边形边叉积，不调用 Q1 内部 containment/wedge helper。

## Brute-force MEC comparison

- 人工几何 5 组：triangle、rectangle、obtuse triangle、acute triangle、equilateral triangle。
- 随机凸多边形 100 组（3--10 顶点）。
- 105 组全部通过；最大半径误差 1.4210854715202004e-14 m，最大圆心误差 7.136584070361083e-15 m。

## Clearable and optical boundaries

- clearable 在 R=16.9990、16.9997、16.99981、16.99982 m 为 True；在 R=16.99983、16.9999、17.0000、17.001 m 为 False。
- within_optical_guarantee 在 R=19.9990、19.9997、19.99981、19.99982 m 为 True；在 R=19.99983、19.9999、20.0000、20.001 m 为 False。
- 均与 R+EPS_MEC<=threshold 的保守公式一致。

## Diameter-cover tests

| Case | diameter_circle_covers | exists_diameter_cover_circle |
| --- | --- | --- |
| line segment | True | True |
| rectangle | True | True |
| equilateral triangle | False | False |
| obtuse triangle | True | True |

旧字段 diameter_length_cover_exists 与正式字段 alias 一致。

## Outer-circle containment

- 独立检查 20000 个 r=1800 m 边界点和 10000 个内部点，0 failures。
- 理论与 diagnostics 径向超出均为 0.017134865789447673 m，误差 0。

## REPAIRED semantics

- 独立解析得到原 1 degree 案例需 x>=2864.4980815379713 m 才可能相交，故在目标圆内为空。
- 返回 status=REPAIRED、relaxation_deg=0.5926278837492986、certificate_under_original_bound=False，语义通过。

## Frozen diff

- git diff --exit-code -- B_code/frozen/q3_baseline_v1：exit 0，输出为空。

## Unresolved issues

- 未发现实现 bug 或可疑数值偏差。
- VERIFIED 仍为 NO，留待团队人工确认。
- REPAIRED 暂不自动授权未来 Q3 clear。
