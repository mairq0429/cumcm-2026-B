"""在坐标 (0, 0) 依次测量频道 1 到 20，并打印汇总表。"""

import sys
from pathlib import Path


# 允许直接执行：python scripts/scan_center.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.simulator_client import SimulatorClient


ROBOT_ID = "202619001606"


def print_summary(records):
    print("\n中心点频道扫描汇总")
    print(f"{'channel':>7}  {'measure_result':<14}  {'svd_deg':>9}  {'virtual_time_s':>14}")
    print("-" * 52)
    for record in records:
        svd_text = (
            str(record["svd_deg"]) if record["svd_deg"] is not None else "-"
        )
        print(
            f"{record['channel']:>7}  "
            f"{record['measure_result']:<14}  "
            f"{svd_text:>9}  "
            f"{record['virtual_time_s']:>14}"
        )


def main():
    client = SimulatorClient(ROBOT_ID)
    records = []
    entered = False

    try:
        client.enter()
        entered = True

        for channel in range(1, 21):
            response = client.measure(0, 0, channel)
            measure_result = response["measure_result"]
            svd_deg = response["svd_deg"] if measure_result == "direction" else None
            records.append(
                {
                    "channel": channel,
                    "measure_result": measure_result,
                    "svd_deg": svd_deg,
                    "virtual_time_s": response["virtual_time_s"],
                }
            )

        print_summary(records)
    except RuntimeError as exc:
        print(f"扫描停止: {exc}")
    finally:
        if entered:
            try:
                client.exit()
            except RuntimeError as exc:
                print(f"退出失败: {exc}")


if __name__ == "__main__":
    main()
