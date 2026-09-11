"""测向线的二维最小二乘定位。"""

import math


def estimate_target(observations):
    """使用所有 direction 观测估计目标坐标 (x_hat, y_hat)。

    每个观测是包含 x、y、bearing（角度制）的字典。
    """
    if len(observations) < 2:
        raise ValueError("至少需要2个direction观测才能定位")

    a11 = 0.0
    a12 = 0.0
    a22 = 0.0
    b1 = 0.0
    b2 = 0.0

    for observation in observations:
        bearing_rad = math.radians(observation["bearing"])
        nx = -math.sin(bearing_rad)
        ny = math.cos(bearing_rad)
        rhs = nx * observation["x"] + ny * observation["y"]

        a11 += nx * nx
        a12 += nx * ny
        a22 += ny * ny
        b1 += nx * rhs
        b2 += ny * rhs

    determinant = a11 * a22 - a12 * a12
    scale = (a11 + a22) ** 2
    if determinant <= 1e-10 * scale:
        raise ValueError("测向线交会角过小，定位矩阵接近奇异")

    x_hat = (b1 * a22 - a12 * b2) / determinant
    y_hat = (a11 * b2 - a12 * b1) / determinant
    return x_hat, y_hat
