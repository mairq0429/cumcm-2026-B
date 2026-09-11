"""附件2四个官方 HTTP 接口的最小 Python 客户端。"""

import json
import socket
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SimulatorClient:
    """串行调用 /enter、/measure、/clear 和 /exit。"""

    def __init__(self, robot_id, base_url="http://127.0.0.1:2026", timeout=5):
        self.robot_id = robot_id
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._request_number = 0

    def _next_request_id(self, action):
        self._request_number += 1
        return f"{action}-{self._request_number:04d}"

    def _base_payload(self, action):
        return {
            "arena_id": "default",
            "robot_id": self.robot_id,
            "request_id": self._next_request_id(action),
        }

    def _post(self, path, payload):
        request = Request(
            self.base_url + path,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urlopen(request, timeout=self.timeout) as http_response:
                http_status = http_response.status
                response = json.loads(http_response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                error_body = exc.read().decode("utf-8")
            except UnicodeDecodeError:
                error_body = "<响应体不是有效的 UTF-8>"
            raise RuntimeError(
                f"{path} HTTP错误: 状态码={exc.code}, 响应={error_body}"
            ) from exc
        except (URLError, socket.timeout, TimeoutError) as exc:
            raise RuntimeError(f"{path} 网络连接或超时错误: {exc}") from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"{path} 响应不是有效的 UTF-8 JSON: {exc}") from exc

        if http_status != 200:
            raise RuntimeError(f"{path} HTTP状态码不是200: {http_status}")
        if response.get("accepted") is not True:
            raise RuntimeError(f"{path} accepted不是true: {response}")

        return response

    def enter(self):
        return self._post("/enter", self._base_payload("enter"))

    def measure(self, x, y, channel):
        payload = self._base_payload("measure")
        payload["position"] = {"x": x, "y": y}
        payload["channel"] = channel
        return self._post("/measure", payload)

    def clear(self, x, y, channel):
        payload = self._base_payload("clear")
        payload["position"] = {"x": x, "y": y}
        payload["channel"] = channel
        return self._post("/clear", payload)

    def exit(self):
        return self._post("/exit", self._base_payload("exit"))
