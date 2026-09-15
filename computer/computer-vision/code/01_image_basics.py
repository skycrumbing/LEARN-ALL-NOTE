# -*- coding: utf-8 -*-
"""
目标检测学习 · 配套代码 01
图像如何变成数字：像素矩阵、BGR 通道、灰度、缩放
离线可跑，不需要网络。

运行：
    python 01_image_basics.py
"""
import os
import sys
import numpy as np
import cv2

# 让中文在 Windows 终端能正常打印
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def make_dir(name):
    d = os.path.join(os.path.dirname(os.path.abspath(__file__)), name)
    os.makedirs(d, exist_ok=True)
    return d


def main():
    out = make_dir("output")

    # ── 1. 灰度图 = 二维数字矩阵 ──────────────────────────────
    print("=" * 60)
    print("1. 灰度图 = 二维数字矩阵（0=黑，255=白）")
    print("=" * 60)
    gray = np.array([
        [0, 255, 255, 0],
        [0, 255, 255, 0],
        [255, 0, 0, 255],
    ], dtype=np.uint8)
    print("shape:", gray.shape, " dtype:", gray.dtype)
    print("矩阵内容:\n", gray)
    print()

    # ── 2. 彩色图 = 三通道叠加 ────────────────────────────────
    print("=" * 60)
    print("2. 彩色图 = 3 个通道叠加，每个像素存 (B,G,R)")
    print("=" * 60)
    color = np.zeros((2, 2, 3), dtype=np.uint8)
    color[0, 0] = (255, 0, 0)     # OpenCV 顺序 (B,G,R) → 纯蓝
    color[0, 1] = (0, 255, 0)     # 纯绿
    color[1, 0] = (0, 0, 255)     # 纯红
    color[1, 1] = (255, 255, 255)  # 白
    print("shape:", color.shape, " (高, 宽, 通道数)")
    print("像素值 (B,G,R):\n", color)
    print()

    # ── 3. BGR 陷阱：OpenCV 用 BGR，不是 RGB ──────────────────
    print("=" * 60)
    print("3. BGR 陷阱：OpenCV 读图得到 BGR，红蓝互换")
    print("=" * 60)
    bgr = np.array([[[255, 0, 0]]], dtype=np.uint8)   # 你想的"红色"?
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    print("OpenCV 里的 (255,0,0) 其实是蓝色:  BGR =", bgr[0, 0].tolist())
    print("转成 RGB 后:                     RGB =", rgb[0, 0].tolist())
    print()

    # ── 4. 生成一张渐变合成图，做灰度/缩放演示 ────────────────
    print("=" * 60)
    print("4. 合成一张 200x300 渐变图，练习灰度化与缩放")
    print("=" * 60)
    h, w = 200, 300
    grad = np.tile(np.linspace(0, 255, w, dtype=np.uint8), (h, 1))
    img = np.stack([grad, grad, grad], axis=-1)   # 3 通道合成，形状 (h, w, 3)
    print("合成图 shape:", img.shape, " 类型:", img.dtype)

    gray_img = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    print("灰度化后 shape:", gray_img.shape, "（从 3 通道变成 1 通道）")

    resized = cv2.resize(gray_img, (150, 100))
    print("缩放后 shape:", resized.shape, "（宽高各缩一半）")
    print("原图左上角 5x5 像素值:\n", gray_img[:5, :5])
    print("缩放后左上角 5x5 像素值:\n", resized[:5, :5])

    cv2.imwrite(os.path.join(out, "01_synthetic.png"), img)
    cv2.imwrite(os.path.join(out, "01_gray.png"), gray_img)
    print("\n结果已保存到:", out)
    print()
    print("结论: 图像 = 数字矩阵; 灰度 1 通道; 彩色 3 通道 (OpenCV 为 BGR); 预处理常做灰度化+缩放。")


if __name__ == "__main__":
    main()
