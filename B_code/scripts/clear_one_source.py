"""自动检测、定位并尝试清除一个真实干扰源。"""

import json
import math
import sys
from pathlib import Path


# 允许直接执行：python scripts/clear_one_source.py
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.geometry import estimate_target
from src.simulator_client import SimulatorClient


ROBOT_ID = "202619001606"
MAX_DIRECTION_OBSERVATIONS = 4
MAX_CLEAR_ATTEMPTS = 3


def point_from_bearing(distance, bearing_deg):
    """按角度制方位生成坐标；Python三角函数内部使用弧度。"""
    bearing_rad = math.radians(bearing_deg)
    return distance * math.cos(bearing_rad), distance * math.sin(bearing_rad)


def add_direction_observation(observations, x, y, response):
    """仅在 direction 时读取 svd_deg 并加入观测。"""
    if response["measure_result"] != "direction":
        return False
    if len(observations) >= MAX_DIRECTION_OBSERVATIONS:
        return False

    observations.append(
        {"x": x, "y": y, "bearing": response["svd_deg"]}
    )
    return True


def print_clear_report(
    target_channel, observations, estimated_position, clear_response
):
    print("\ntarget_channel:", target_channel)
    print("observations:", json.dumps(observations, ensure_ascii=False))
    print("estimated_position:", estimated_position)
    print("clear_result:", clear_response["clear_result"])
    print("virtual_time_s:", clear_response["virtual_time_s"])


def attempt_clear(
    client,
    x,
    y,
    target_channel,
    observations,
    clear_attempts,
):
    """执行一次有依据的清除，返回（是否成功，新的清除次数）。"""
    if clear_attempts >= MAX_CLEAR_ATTEMPTS:
        print("已达到clear最多3次的限制")
        return False, clear_attempts

    clear_response = client.clear(x, y, target_channel)
    clear_attempts += 1
    print_clear_report(
        target_channel,
        observations,
        (x, y),
        clear_response,
    )

    if clear_response["clear_result"] == "success":
        print("***** CLEAR SUCCESS *****")
        return True, clear_attempts
    return False, clear_attempts


def measure_candidate(
    client,
    x,
    y,
    target_channel,
    observations,
    clear_attempts,
):
    """测量候选点，返回（成功、清除次数、是否新增direction）。"""
    response = client.measure(x, y, target_channel)
    measure_result = response["measure_result"]
    print(
        f"measure ({x:.3f}, {y:.3f}), channel={target_channel}: "
        f"{measure_result}, virtual_time_s={response['virtual_time_s']}"
    )

    if measure_result == "direction":
        added_direction = add_direction_observation(observations, x, y, response)
        print("svd_deg:", response["svd_deg"])
        return False, clear_attempts, added_direction

    if measure_result == "near":
        success, clear_attempts = attempt_clear(
            client,
            x,
            y,
            target_channel,
            observations,
            clear_attempts,
        )
        return success, clear_attempts, False

    # no_signal只记录结果，不读取svd_deg，也不中断程序。
    return False, clear_attempts, False


def estimate_and_clear(
    client, target_channel, observations, clear_attempts
):
    """观测充分且矩阵可解时定位并清除。"""
    if len(observations) < 2:
        print("direction观测不足2次，暂不能定位")
        return False, clear_attempts

    try:
        estimated_position = estimate_target(observations)
    except ValueError as exc:
        print("定位暂不可用:", exc)
        return False, clear_attempts

    print("estimated_position:", estimated_position)
    return attempt_clear(
        client,
        estimated_position[0],
        estimated_position[1],
        target_channel,
        observations,
        clear_attempts,
    )


def main():
    client = SimulatorClient(ROBOT_ID)
    entered = False
    observations = []
    clear_attempts = 0

    try:
        client.enter()
        entered = True

        target_channel = None
        theta1 = None

        # 在原点从频道1开始，找到第一个direction后立即停止扫描。
        for channel in range(1, 21):
            response = client.measure(0, 0, channel)
            measure_result = response["measure_result"]
            print(
                f"origin channel={channel}: {measure_result}, "
                f"virtual_time_s={response['virtual_time_s']}"
            )
            if measure_result == "direction":
                target_channel = channel
                theta1 = response["svd_deg"]
                observations.append({"x": 0, "y": 0, "bearing": theta1})
                print("target_channel:", target_channel)
                print("theta1:", theta1)
                break

        if target_channel is None:
            print("原点扫描未发现direction目标")
            return

        # 按题定构造S2和S3，角度转弧度后计算。
        s2 = point_from_bearing(600, theta1 + 60)
        s3 = point_from_bearing(600, theta1 - 60)

        for x, y in (s2, s3):
            success, clear_attempts, _ = measure_candidate(
                client,
                x,
                y,
                target_channel,
                observations,
                clear_attempts,
            )
            if success:
                return

        # 至少两次direction时进行第一次最小二乘定位和清除。
        success, clear_attempts = estimate_and_clear(
            client, target_channel, observations, clear_attempts
        )
        if success:
            return

        # 失败兜底：在原点外800米、相对theta1约±90度处补充测向。
        for offset_deg in (90, -90):
            if len(observations) >= MAX_DIRECTION_OBSERVATIONS:
                break
            if clear_attempts >= MAX_CLEAR_ATTEMPTS:
                break

            x, y = point_from_bearing(800, theta1 + offset_deg)
            success, clear_attempts, added_direction = measure_candidate(
                client,
                x,
                y,
                target_channel,
                observations,
                clear_attempts,
            )
            if success:
                return

            # 只有新获得direction观测后才重新定位和清除。
            if added_direction:
                success, clear_attempts = estimate_and_clear(
                    client, target_channel, observations, clear_attempts
                )
                if success:
                    return

        print(
            "未能清除目标；",
            f"direction观测={len(observations)}, clear次数={clear_attempts}",
        )
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        print("演练中止:", exc)
    finally:
        if entered:
            try:
                exit_response = client.exit()
                print(
                    "exit_reason:",
                    exit_response["exit_reason"],
                    "virtual_time_s:",
                    exit_response["virtual_time_s"],
                )
            except RuntimeError as exc:
                print("退出失败:", exc)


if __name__ == "__main__":
    main()
