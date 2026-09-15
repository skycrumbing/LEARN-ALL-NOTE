# -*- coding: utf-8 -*-
"""
目标检测学习 · 配套代码 02
纯 numpy 手动实现卷积：边缘检测 / 模糊
用到的例子就是 cnn-basics.md 笔记里的手算题，输出应该完全一致。
离线可跑，不需要网络。

运行：
    python 02_convolution.py
"""
import os
import sys
import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def conv2d(x, kernel, padding=0, stride=1):
    """最朴素的卷积实现：循环滑动小窗口，对应相乘再全部相加。

    参数
    ----
    x       : 2 维输入矩阵（单通道灰度图）
    kernel  : 2 维卷积核
    padding : 边缘补 0 的圈数
    stride  : 每次滑动的步长

    返回输出尺寸公式: floor((H + 2p - k) / s) + 1
    """
    if padding > 0:
        x = np.pad(x, padding, mode="constant")
    H, W = x.shape
    kh, kw = kernel.shape
    out_h = (H - kh) // stride + 1
    out_w = (W - kw) // stride + 1
    out = np.zeros((out_h, out_w), dtype=float)
    for i in range(out_h):
        for j in range(out_w):
            region = x[i * stride:i * stride + kh, j * stride:j * stride + kw]
            out[i, j] = np.sum(region * kernel)
    return out


def main():
    # ── 1. 复现笔记里的手算题（应输出完全一致）────────────────
    print("=" * 60)
    print("1. 复现 cnn-basics 笔记手算题：5x5 输入 x 3x3 边缘核")
    print("=" * 60)
    X = np.array([
        [1, 1, 1, 0, 0],
        [0, 1, 1, 1, 0],
        [0, 0, 1, 1, 1],
        [0, 0, 1, 1, 0],
        [0, 1, 1, 0, 0],
    ], dtype=float)
    edge_kernel = np.array([
        [1, 0, -1],
        [1, 0, -1],
        [1, 0, -1],
    ], dtype=float)  # 竖直边缘检测核

    feat = conv2d(X, edge_kernel)
    print("输入 X:\n", X.astype(int))
    print("核 W（竖直边缘）:\n", edge_kernel.astype(int))
    print("输出特征图（3x3）:\n", feat)
    print("验证: 输出(0,0) 应为 -2，笔记里手算过 ✅")
    print()

    # ── 2. 边缘检测核 vs 模糊核：在合成图上对比效果 ────────────
    print("=" * 60)
    print("2. 不同卷积核 = 不同特征检测器（边缘 vs 模糊）")
    print("=" * 60)
    # 合成一张 64x64 的方块图：左半边亮、右半边暗，中间是竖直边缘
    img = np.zeros((64, 64), dtype=float)
    img[:, :32] = 200.0
    img[:, 32:] = 40.0

    blur_kernel = np.ones((3, 3), dtype=float) / 9.0   # 平均模糊核

    edge_out = conv2d(img, edge_kernel)
    blur_out = conv2d(img, blur_kernel)

    # 打印第 30 行中"边缘附近"的列（x≈31 是明暗分界），观察数值变化
    row = 30
    lo, hi = 24, 42
    print(f"原图第 30 行 第{lo}~{hi}列（左 200=亮，右 40=暗，分界在 x≈31）:")
    print("  ", img[row, lo:hi].astype(int))
    print(f"边缘核输出第 30 行（分界处数值剧烈跳变 → 找到了竖直边缘）:")
    print("  ", edge_out[row, lo:hi].round(1))
    print(f"模糊核输出第 30 行（突变被抹平成缓坡）:")
    print("  ", blur_out[row, lo:hi].round(1))
    print()
    print("结论: 边缘核找'变化剧烈处'(数值大); 模糊核把突变抹平(数值缓和)。")
    print("      CNN 就是靠一堆这样的核(可学习)自动提取特征。")


if __name__ == "__main__":
    main()
