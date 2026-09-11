"""按附件2官方 Python 示例验证模拟器通信流程。

运行前，请先在模拟器界面开始一次测试，并等待界面提示通信接口已经开放。
本脚本只使用 POST /enter、/measure、/clear、/exit 四个接口。
"""

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# 修改为当前登录模拟器的参赛队号。
ROBOT_ID = "202619001606"

BASE_URL = "http://127.0.0.1:2026"
TIMEOUT_S = 5


def _print_response(path, payload, http_status, response):
    """统一打印一次请求的检查信息。"""
    print(f"\n{path}")
    print("HTTP状态码:", http_status)
    print("请求JSON:", json.dumps(payload, ensure_ascii=False))
    print(
        "响应JSON:",
        json.dumps(response, ensure_ascii=False) if response is not None else None,
    )
    print("accepted:", response.get("accepted") if response is not None else None)
    print(
        "virtual_time_s:",
        response.get("virtual_time_s") if response is not None else None,
    )


def post(path, payload):
    """发送官方格式的 POST 请求，并检查 HTTP 状态和 accepted。"""
    request = Request(
        BASE_URL + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    http_status = None
    response = None
    try:
        with urlopen(request, timeout=TIMEOUT_S) as http_response:
            http_status = http_response.status
            response = json.loads(http_response.read().decode("utf-8"))
    except HTTPError as exc:
        http_status = exc.code
        try:
            response = json.loads(exc.read().decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            response = None
        _print_response(path, payload, http_status, response)
        print("检查失败: HTTP状态码不是200")
        return None
    except (URLError, socket.timeout, TimeoutError) as exc:
        _print_response(path, payload, http_status, response)
        print(f"请求异常: {exc}")
        return None
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _print_response(path, payload, http_status, response)
        print(f"响应JSON解析失败: {exc}")
        return None

    _print_response(path, payload, http_status, response)

    if http_status != 200:
        print("检查失败: HTTP状态码不是200")
        return None
    if response.get("accepted") is not True:
        print("检查失败: accepted不是true，指令未执行")
        return None

    return response


def base(request_id):
    return {
        "arena_id": "default",
        "robot_id": ROBOT_ID,
        "request_id": request_id,
    }


def action(request_id, x, y, channel):
    payload = base(request_id)
    payload["position"] = {"x": x, "y": y}
    payload["channel"] = channel
    return payload


def main():
    if ROBOT_ID == "这里填写参赛队号":
        print("请先在程序顶部把 ROBOT_ID 修改为当前登录模拟器的参赛队号。")
        return

    enter_response = post("/enter", base("enter-1"))
    if enter_response is None:
        print("进入失败，停止后续请求。")
        return

    print("本场可用真实时间:", enter_response["remaining_real_duration_s"], "秒")

    # 与附件2第10节计时示例及第11节 Python 示例完全相同的四个动作。
    actions = [
        ("/measure", action("measure-1", 300, 400, 1)),
        ("/measure", action("measure-2", 300, 400, 2)),
        ("/clear", action("clear-1", 300, 0, 3)),
        ("/measure", action("measure-3", 300, 0, 2)),
    ]

    for path, payload in actions:
        response = post(path, payload)
        if response is None:
            print("动作未执行，停止后续请求。")
            return

        if path == "/measure":
            measure_result = response["measure_result"]
            if measure_result == "direction":
                # 只有 direction 响应才包含并读取 svd_deg。
                print("示方度:", response["svd_deg"], "度")
            elif measure_result == "near":
                print("距离过近，没有示方度")
            else:
                print("未检测到信号")
        else:
            if response["clear_result"] == "success":
                print("清除成功")
            else:
                print("该位置附近没有目标")

    exit_response = post("/exit", base("exit-1"))
    if exit_response is not None:
        print("退出原因:", exit_response["exit_reason"])


if __name__ == "__main__":
    main()
