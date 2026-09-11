# Q3 baseline v1 压力测试

## 测试版本

- algorithm: Q3-baseline-v1
- git commit: `2a9ec32258ca6ed366503503bf273c77cf313df0`
- freeze manifest SHA256: `AE1C40A6A1A923D87BCC7CE592A6639C8BFBC29ABDBE3F65EEF5E63FB7A19358`
- frozen `baseline_q3_all.py` SHA256: `42263FF64E21C8D2358DF249E86C19975C96877A9CAE5193B3DE8D568EC68111`
- frozen `simulator_client.py` SHA256: `C4BB13E11F9DB34FB0B349D7AB8C9A5503A84CCD001BF22651974272AA6B8208`
- frozen `geometry.py` SHA256: `793B2217CA3B3CA6D0B3E2E67CBEE2C3AE4A2B1B4192885A37A85AA3AC145DF4`

## 测试时间

2026-09-11 11:19:12 至 2026-09-11 11:42:26（UTC+08:00）。

## 5局明细

| run_id | actual | discovered | cleared | discovery_rate | clear_rate | virtual_time_s | mean_clear_time_s | clear_failures | crashed | case_code | log_file | notes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | --- | --- | --- |
| Q3-S-001 | missing | 12 | 12 | missing | missing | 3823.317224 | 318.609769 | 0 | NO | SZQJ-5JPR-B2DV-K249 | `03_results/stress_test/q3/Q3-S-001/console_output.txt` | `actual_sources` 无官方证据，保持缺失。 |
| Q3-S-002 | 12 | 12 | 12 | 1.000000 | 1.000000 | 4929.760366 | 410.813364 | 0 | NO | TNE3-BQJ8-U65W-TE2J | `03_results/stress_test/q3/Q3-S-002/console_output.txt` | 官方页面人工核实：omni=12，directional=0。 |
| Q3-S-003 | 11 | 11 | 11 | 1.000000 | 1.000000 | 4163.748193 | 378.522563 | 0 | NO | PU5X-KHAW-GPQR-CETB | `03_results/stress_test/q3/Q3-S-003/console_output.txt` | 官方页面人工核实：actual=11, omni=11, directional=0。|
| Q3-S-004 | 14 | 14 | 14 | 1.000000 | 1.000000 | 5186.088329 | 370.434881 | 2 | NO | S4GV-JDPH-39RX-3YWG | `03_results/stress_test/q3/Q3-S-004/console_output.txt` | SUCCESS_WITH_RECOVERY. Channel 1 had two failed clear attempts; recovered after additional measurement/localization and was ultimately cleared successfully. |
| Q3-S-005 | 16 | 16 | 16 | 1.000000 | 1.000000 | 5604.841475 | 350.302592 | 1 | NO | 9D37-EFR4-D45X-P3RV | `03_results/stress_test/q3/Q3-S-005/console_output.txt` | SUCCESS_WITH_RECOVERY. Channel 11 had one failed clear attempt and was later successfully cleared. |

## 总体统计

- 总案例数：5
- 官方 `actual_sources` 已知案例数：4
- 已确认完整发现案例数：4；仅 Q3-S-001 因 `actual_sources` 缺失无法判定
- 已确认完整清除案例数：4；仅 Q3-S-001 因 `actual_sources` 缺失无法判定
- 五局总真实源数：missing（仅 Q3-S-001 缺少官方 `actual_sources` 数据）
- 已有官方证据的 4 局真实源总数：53
- 五局总体发现率：missing（Q3-S-001 缺少官方 `actual_sources`，不作猜测）
- 五局总体清除率：missing（Q3-S-001 缺少官方 `actual_sources`，不作猜测）
- 已有官方总源数证据的 4 局：53/53 被发现，53/53 被最终清除，发现率=100%，最终清除率=100%
- 总发现源数：65
- 总清除源数：65
- crash 数量：0

### virtual_time_s

| mean | median | min | max | sample std |
| ---: | ---: | ---: | ---: | ---: |
| 4741.551117 | 4929.760366 | 3823.317224 | 5604.841475 | 734.049725 |

### mean_clear_time_s

| mean | median | min | max | sample std |
| ---: | ---: | ---: | ---: | ---: |
| 365.736634 | 370.434881 | 318.609769 | 410.813364 | 34.192895 |

## 失败案例

最终未完成清除的失败案例：无。

恢复性异常必须保留：

- Q3-S-004：channel 1 前两次 clear 失败，额外测量/定位后最终清除成功。状态为 `SUCCESS_WITH_RECOVERY`。
- Q3-S-005：channel 11 有一次 clear 失败，后续最终清除成功。状态为 `SUCCESS_WITH_RECOVERY`。

所有 crash：无。

缺失字段：

- Q3-S-001：`actual_sources`、`omni_sources`、`directional_sources`、`discovery_rate`、`clear_rate`、`move_distance_m`。
- Q3-S-002、Q3-S-003、Q3-S-004、Q3-S-005：`move_distance_m`。

## 官方原始日志

- Q3-S-001: `practice-p3-1617059620572471216-SZQJ-5JPR-B2DV-K249.jlog`
- Q3-S-002: `practice-p3-1398409275993220088-TNE3-BQJ8-U65W-TE2J.jlog`
- Q3-S-003: `practice-p3-197443961168551633-PU5X-KHAW-GPQR-CETB.jlog`
- Q3-S-004: `practice-p3-7468962560785716735-S4GV-JDPH-39RX-3YWG.jlog`
- Q3-S-005: `practice-p3-4574264698397515695-9D37-EFR4-D45X-P3RV.jlog`

上述日志均在各自案例目录中按官方原文件名保存。

## 当前证据状态

- CODED: YES
- TESTED: YES
- VERIFIED: NO

当前 Q3-baseline-v1 已完成代码实现和 5 局官方模拟器压力测试，
但尚未完成团队交叉审查、模型—代码一致性检查、消融实验与敏感性分析，
因此不得标记为 VERIFIED。

## 下一步

1. 提交建模手进行模型合理性与假设审查；
2. 核查 Q1/Q2 模型与 Q3 当前实现之间的差异；
3. 对 Q3-S-004、Q3-S-005 的 clear failure 进行原因分类；
4. 确定 Q3-improved-v1 只修改一个核心模块；
5. 对改进版与 baseline 做同条件 A/B 演练；
6. 完成六层核查后，再决定是否升级为 VERIFIED。
