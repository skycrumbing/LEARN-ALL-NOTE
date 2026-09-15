# -*- coding: utf-8 -*-
"""
目标检测学习 · 配套代码 07
传统方法实战：颜色 + 轮廓法定位车牌（license-plate 笔记）

思路（不需要深度学习）：
  1. 转 HSV，用颜色范围筛出蓝色（中国蓝牌是蓝底白字）
  2. 形态学膨胀，把字符区域连成一块
  3. 找轮廓，按"宽高比 ≈ 3~5 的扁长矩形"过滤 → 车牌区域

输入图片优先级：
  1. samples/ 下的第一张图片（放一张有车牌的车照片进去）
  2. 内置合成图：画一个简易车身 + 蓝色车牌，保证离线可演示
运行后保存定位结果到 output/ 目录。

运行：
    python 07_license_plate.py
"""
import os
import sys
import numpy as np
import cv2

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(SCRIPT_DIR, "samples")
OUT = os.path.join(SCRIPT_DIR, "output")


def make_synthetic_car():
    """生成一张带蓝色车牌的合成车图（演示用）。"""
    img = np.zeros((400, 600, 3), dtype=np.uint8)
    img[:] = (120, 120, 120)                       # 灰色背景

    # 车身（深色矩形）+ 车头下方留白放车牌
    cv2.rectangle(img, (120, 140), (480, 320), (40, 40, 40), -1)
    cv2.rectangle(img, (160, 110), (220, 150), (30, 30, 30), -1)   # 车窗1
    cv2.rectangle(img, (240, 110), (300, 150), (30, 30, 30), -1)   # 车窗2
    cv2.rectangle(img, (320, 110), (380, 150), (30, 30, 30), -1)   # 车窗3
    cv2.rectangle(img, (400, 110), (440, 150), (30, 30, 30), -1)   # 车窗4

    # 蓝色车牌（BGR: (200, 0, 0) 偏蓝），扁长矩形，宽高比≈4
    plate = (250, 330, 140, 36)
    x, y, w, h = plate
    cv2.rectangle(img, (x, y), (x + w, y + h), (180, 0, 0), -1)
    # 车牌上的"白色字符"（用小白块模拟文字）
    for i in range(6):
        cv2.rectangle(img, (x + 8 + i * 20, y + 6), (x + 8 + i * 20 + 10, y + 30), (255, 255, 255), -1)

    return img


def find_input_image():
    """有用户图片用用户的，否则用内置合成图。"""
    exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    if os.path.isdir(SAMPLES):
        for f in sorted(os.listdir(SAMPLES)):
            if f.lower().endswith(exts):
                return os.path.join(SAMPLES, f)
    return None


def main():
    os.makedirs(OUT, exist_ok=True)

    path = find_input_image()
    if path is not None:
        print("输入图片:", path)
        img = cv2.imread(path)
        if img is None:
            print("读取失败，退回合成图。")
            img = make_synthetic_car()
    else:
        print("samples/ 里没有图片，使用内置合成车图演示。")
        print("提示: 放一张真实车牌照片到 samples/ 再运行，效果更真实。")
        img = make_synthetic_car()

    # ── 1. 颜色筛选：HSV 里找蓝色区域 ────────────────────────
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    # 蓝色的 H 通道约在 90~130（OpenCV 里 H 范围是 0~180）
    lower_blue = np.array([90, 100, 100])
    upper_blue = np.array([130, 255, 255])
    mask = cv2.inRange(hsv, lower_blue, upper_blue)
    print(f"1. 颜色筛选: 蓝色像素数 = {int((mask > 0).sum())}")

    # ── 2. 形态学：膨胀把字符和底色连成一块 ──────────────────
    kernel = np.ones((5, 15), np.uint8)   # 横向长条，贴合扁长车牌
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)

    # ── 3. 找轮廓 + 宽高比过滤 ───────────────────────────────
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    print(f"2. 找到 {len(contours)} 个蓝色连通区域")

    result = img.copy()
    found = False
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w < 40 or h < 15:          # 太小直接跳过
            continue
        aspect = w / h if h > 0 else 0
        # 车牌宽高比 ≈ 3~5，且面积不能太小
        if 2.0 <= aspect <= 6.0:
            print(f"3. 命中车牌候选: ({x},{y},{w},{h})  宽高比={aspect:.2f}")
            cv2.rectangle(result, (x, y), (x + w, y + h), (0, 255, 0), 3)
            cv2.putText(result, "PLATE", (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)
            found = True

    if not found:
        print("3. 没有找到符合宽高比的车牌区域。真实图片可能需要调颜色范围/阈值。")

    out_path = os.path.join(OUT, "07_plate_result.png")
    cv2.imwrite(out_path, result)
    cv2.imwrite(os.path.join(OUT, "07_plate_mask.png"), mask)
    print("\n结果已保存:", out_path, "（另存了二值掩码 07_plate_mask.png）")
    print("说明: 这只是'定位'；读出号码还需字符识别(CNN/LPRNet)——见 license-plate.md。")


if __name__ == "__main__":
    main()
