"""问题3演练测试 baseline：侦察并尝试清除程序发现的全部干扰源。

仅用于新的“问题3演练测试”，不要用于正式测试或问题4。
"""

import argparse
import math
import sys
from collections import defaultdict
from pathlib import Path


# 允许直接执行：python scripts/baseline_q3_all.py --robot-id XXXXX
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.geometry import estimate_target
from src.simulator_client import SimulatorClient


MAX_CLEAR_ATTEMPTS_PER_CHANNEL = 3
MAX_DIRECTION_OBSERVATIONS_PER_CHANNEL = 5


def parse_args():
    parser = argparse.ArgumentParser(
        description="问题3演练测试：7点侦察并清除程序发现的干扰源"
    )
    parser.add_argument(
        "--robot-id",
        required=True,
        help="当前登录模拟器的参赛队号",
    )
    return parser.parse_args()


def regular_hexagon_points(radius=1200.0):
    points = [(0.0, 0.0)]
    for k in range(6):
        angle_rad = math.radians(k * 60.0)
        points.append(
            (radius * math.cos(angle_rad), radius * math.sin(angle_rad))
        )
    return points


def offset_point(x, y, distance, bearing_deg):
    angle_rad = math.radians(bearing_deg)
    return (
        x + distance * math.cos(angle_rad),
        y + distance * math.sin(angle_rad),
    )


def distance(point_a, point_b):
    return math.hypot(point_a[0] - point_b[0], point_a[1] - point_b[1])


def update_state(state, response, position=None):
    state["virtual_time_s"] = response["virtual_time_s"]
    if position is not None:
        state["current_position"] = position


def measure_at(client, state, x, y, channel):
    response = client.measure(x, y, channel)
    update_state(state, response, (x, y))
    return response


def clear_at(client, state, x, y, channel):
    response = client.clear(x, y, channel)
    update_state(state, response, (x, y))
    return response


def run_reconnaissance(
    client,
    state,
    observations,
    near_positions,
    discovered_channels,
):
    """在中心和正六边形顶点完成固定7×20次串行侦察。"""
    recon_results = []

    for point_index, (x, y) in enumerate(regular_hexagon_points()):
        channels = range(1, 21) if point_index % 2 == 0 else range(20, 0, -1)
        print(f"\n侦察点 P{point_index}: ({x:.3f}, {y:.3f})")

        for channel in channels:
            response = measure_at(client, state, x, y, channel)
            measure_result = response["measure_result"]
            recon_results.append(
                {
                    "x": x,
                    "y": y,
                    "channel": channel,
                    "measure_result": measure_result,
                    "svd_deg": (
                        response["svd_deg"]
                        if measure_result == "direction"
                        else None
                    ),
                    "virtual_time_s": response["virtual_time_s"],
                }
            )

            if measure_result == "direction":
                if (
                    len(observations[channel])
                    < MAX_DIRECTION_OBSERVATIONS_PER_CHANNEL
                ):
                    observations[channel].append(
                        {"x": x, "y": y, "bearing": response["svd_deg"]}
                    )
                discovered_channels.add(channel)
                print(
                    f"  channel={channel:2d} direction "
                    f"svd_deg={response['svd_deg']}"
                )
            elif measure_result == "near":
                near_positions[channel] = (x, y)
                discovered_channels.add(channel)
                print(f"  channel={channel:2d} near")

    return recon_results


def print_reconnaissance_summary(
    discovered_channels, observations, near_positions, state
):
    print("\n===== 侦察阶段汇总 =====")
    print("discovered_channels:", sorted(discovered_channels))
    for channel in range(1, 21):
        print(
            f"channel={channel:2d} direction_observations="
            f"{len(observations[channel])}"
        )
    print("near_channels:", sorted(near_positions))
    print("recon_virtual_time_s:", state["virtual_time_s"])


def estimate_available_targets(discovered_channels, observations):
    estimated_targets = {}
    for channel in sorted(discovered_channels):
        if len(observations[channel]) < 2:
            continue
        try:
            estimated_targets[channel] = estimate_target(observations[channel])
        except ValueError as exc:
            print(f"channel={channel} 初始定位失败: {exc}")
    return estimated_targets


def supplement_single_observation(
    client,
    state,
    channel,
    observations,
    near_positions,
    estimated_targets,
):
    """只有一次direction时，最多在theta±60度方向各补测一次。"""
    first = observations[channel][0]

    for offset_deg in (60.0, -60.0):
        qx, qy = offset_point(
            first["x"],
            first["y"],
            600.0,
            first["bearing"] + offset_deg,
        )
        response = measure_at(client, state, qx, qy, channel)
        measure_result = response["measure_result"]
        print(
            f"channel={channel} 补测 ({qx:.3f}, {qy:.3f}): "
            f"{measure_result}"
        )

        if measure_result == "direction":
            observations[channel].append(
                {"x": qx, "y": qy, "bearing": response["svd_deg"]}
            )
            try:
                estimated_targets[channel] = estimate_target(
                    observations[channel]
                )
            except ValueError as exc:
                print(f"channel={channel} 补测后定位失败: {exc}")
            return

        if measure_result == "near":
            near_positions[channel] = (qx, qy)
            return

        # no_signal时不否定频道存在；第一次失败后再试另一侧。


def target_position(channel, near_positions, estimated_targets):
    if channel in near_positions:
        return near_positions[channel]
    return estimated_targets.get(channel)


def choose_fallback_measure_position(
    estimated_position,
    bearing_deg,
    channel_observations,
    previous_fallback_position,
):
    """按±90度、300/500米的优先级选择未用过的新补测点。"""
    gx, gy = estimated_position
    previous_points = [
        (observation["x"], observation["y"])
        for observation in channel_observations
    ]

    for fallback_distance in (300.0, 500.0):
        for offset_deg in (90.0, -90.0):
            qx, qy = offset_point(
                gx,
                gy,
                fallback_distance,
                bearing_deg + offset_deg,
            )
            candidate = (qx, qy)
            distances = [distance(candidate, point) for point in previous_points]
            too_close_to_observation = any(value < 50.0 for value in distances)
            repeats_previous_fallback = (
                previous_fallback_position is not None
                and distance(candidate, previous_fallback_position) < 1e-6
            )
            if not too_close_to_observation and not repeats_previous_fallback:
                return candidate, distances

    raise ValueError("无法构造与已有观测点相距至少50米的新补测点")


def clear_one_channel(
    client,
    state,
    channel,
    observations,
    near_positions,
    estimated_targets,
    clear_counts,
):
    """有限次清除；失败后换到新的空间位置补测并重新定位。"""
    position = target_position(channel, near_positions, estimated_targets)
    if position is None:
        print(f"channel={channel} 没有可用清除位置")
        return False

    previous_fallback_position = None

    while clear_counts[channel] < MAX_CLEAR_ATTEMPTS_PER_CHANNEL:
        x, y = position
        response = clear_at(client, state, x, y, channel)
        clear_counts[channel] += 1
        clear_result = response["clear_result"]
        print(
            f"channel={channel} clear#{clear_counts[channel]} "
            f"position=({x:.3f}, {y:.3f}) result={clear_result} "
            f"virtual_time_s={response['virtual_time_s']}"
        )

        if clear_result == "success":
            print(f"***** CHANNEL {channel} CLEAR SUCCESS *****")
            return True

        if clear_counts[channel] >= MAX_CLEAR_ATTEMPTS_PER_CHANNEL:
            break

        old_estimate = estimated_targets.get(channel)
        if old_estimate is None or not observations[channel]:
            print(f"channel={channel} 缺少估计位置或direction观测，无法构造补测点")
            break

        latest_bearing = observations[channel][-1]["bearing"]
        try:
            fallback_position, distances = choose_fallback_measure_position(
                old_estimate,
                latest_bearing,
                observations[channel],
                previous_fallback_position,
            )
        except ValueError as exc:
            print(f"channel={channel} 构造补测点失败: {exc}")
            break

        print("fallback_measure_position:", fallback_position)
        print(
            "distance_to_previous_points:",
            [round(value, 3) for value in distances],
        )
        previous_fallback_position = fallback_position

        qx, qy = fallback_position
        response = measure_at(client, state, qx, qy, channel)
        measure_result = response["measure_result"]
        print(
            f"channel={channel} 新位置补测: {measure_result}, "
            f"virtual_time_s={response['virtual_time_s']}"
        )

        if measure_result == "near":
            near_positions[channel] = fallback_position
            position = fallback_position
            continue

        if measure_result == "direction":
            if len(observations[channel]) >= MAX_DIRECTION_OBSERVATIONS_PER_CHANNEL:
                print(f"channel={channel} 已达到direction观测上限")
                break
            observations[channel].append(
                {"x": qx, "y": qy, "bearing": response["svd_deg"]}
            )
            try:
                new_estimate = estimate_target(observations[channel])
            except ValueError as exc:
                print(f"channel={channel} 重新定位失败: {exc}")
                break
            estimate_shift = distance(old_estimate, new_estimate)
            print("old_estimate:", old_estimate)
            print("new_estimate:", new_estimate)
            print("estimate_shift_distance:", estimate_shift)
            estimated_targets[channel] = new_estimate
            if estimate_shift < 1e-6:
                print(f"channel={channel} 新观测未改变估计，禁止在旧坐标重复clear")
                break
            position = new_estimate
            continue

        # no_signal只记录；没有新定位依据时停止该频道的清除尝试。
        break

    return False


def clear_discovered_targets(
    client,
    state,
    discovered_channels,
    observations,
    near_positions,
    estimated_targets,
    clear_counts,
):
    """从当前位置开始，以最近邻顺序处理所有有候选位置的频道。"""
    cleared_channels = set()
    pending = set(discovered_channels)

    while pending:
        candidates = {
            channel: target_position(channel, near_positions, estimated_targets)
            for channel in pending
        }
        candidates = {
            channel: position
            for channel, position in candidates.items()
            if position is not None
        }
        if not candidates:
            break

        channel = min(
            candidates,
            key=lambda item: distance(
                state["current_position"], candidates[item]
            ),
        )
        pending.remove(channel)

        if clear_one_channel(
            client,
            state,
            channel,
            observations,
            near_positions,
            estimated_targets,
            clear_counts,
        ):
            cleared_channels.add(channel)

    return cleared_channels


def print_final_summary(
    discovered_channels,
    cleared_channels,
    observations,
    clear_counts,
    virtual_time_s,
):
    discovered_count = len(discovered_channels)
    cleared_count = len(cleared_channels)
    ratio = cleared_count / discovered_count if discovered_count else 0.0

    print("\n===== 最终汇总 =====")
    print("发现频道数量:", discovered_count)
    print("成功清除数量:", cleared_count)
    print("清除比例:", f"{ratio:.2%}")
    print("总virtual_time_s:", virtual_time_s)
    print("cleared_channels:", sorted(cleared_channels))
    for channel in sorted(discovered_channels):
        print(
            f"channel={channel:2d} "
            f"定位观测数={len(observations[channel])} "
            f"clear次数={clear_counts[channel]}"
        )


def main():
    args = parse_args()
    client = SimulatorClient(args.robot_id)
    state = {"current_position": (0.0, 0.0), "virtual_time_s": 0}
    observations = defaultdict(list)
    near_positions = {}
    discovered_channels = set()
    estimated_targets = {}
    clear_counts = defaultdict(int)
    cleared_channels = set()
    entered = False

    try:
        enter_response = client.enter()
        entered = True
        update_state(state, enter_response)

        recon_results = run_reconnaissance(
            client,
            state,
            observations,
            near_positions,
            discovered_channels,
        )
        print("侦察记录数:", len(recon_results))
        print_reconnaissance_summary(
            discovered_channels, observations, near_positions, state
        )

        estimated_targets = estimate_available_targets(
            discovered_channels, observations
        )

        for channel in sorted(discovered_channels):
            if len(observations[channel]) == 1 and channel not in near_positions:
                supplement_single_observation(
                    client,
                    state,
                    channel,
                    observations,
                    near_positions,
                    estimated_targets,
                )

        cleared_channels = clear_discovered_targets(
            client,
            state,
            discovered_channels,
            observations,
            near_positions,
            estimated_targets,
            clear_counts,
        )

        if cleared_channels == discovered_channels:
            print("程序发现的频道已全部清除")
        else:
            unresolved = discovered_channels - cleared_channels
            print("未清除频道:", sorted(unresolved))
    except (RuntimeError, KeyError, TypeError, ValueError) as exc:
        print("baseline执行中止:", exc)
    finally:
        if entered:
            try:
                exit_response = client.exit()
                update_state(state, exit_response)
                print("exit_reason:", exit_response["exit_reason"])
            except RuntimeError as exc:
                print("退出失败:", exc)

    print_final_summary(
        discovered_channels,
        cleared_channels,
        observations,
        clear_counts,
        state["virtual_time_s"],
    )


if __name__ == "__main__":
    main()
