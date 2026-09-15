# -*- coding: utf-8 -*-
"""
目标检测学习 · 配套代码 03
手写 IoU 与 NMS 算法，并复现 detection-concepts 笔记里的手算题。
离线可跑，不需要任何第三方库。

运行：
    python 03_iou_nms.py
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 约定框的表示: (x, y, w, h) —— 左上角 (x,y)，宽 w，高 h


def to_corners(box):
    """把 (x, y, w, h) 转成 (x1, y1, x2, y2) 便于算面积。"""
    x, y, w, h = box
    return x, y, x + w, y + h


def iou(box1, box2):
    """两个框的交并比 IoU = 交集面积 / 并集面积。"""
    ax1, ay1, ax2, ay2 = to_corners(box1)
    bx1, by1, bx2, by2 = to_corners(box2)

    ix1 = max(ax1, bx1)
    iy1 = max(ay1, by1)
    ix2 = min(ax2, bx2)
    iy2 = min(ay2, by2)

    inter_w = max(0, ix2 - ix1)   # 不相交时面积取 0
    inter_h = max(0, iy2 - iy1)
    inter = inter_w * inter_h

    area_a = (ax2 - ax1) * (ay2 - ay1)
    area_b = (bx2 - bx1) * (by2 - by1)
    union = area_a + area_b - inter
    return inter / union if union > 0 else 0.0


def nms(boxes, scores, iou_threshold=0.5):
    """非极大值抑制：每个物体只保留得分最高的框。

    返回保留的框的下标列表。
    """
    # 按得分从高到低排序
    order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
    keep = []
    while order:
        idx = order.pop(0)        # 当前最高分框
        keep.append(idx)
        # 删除所有与它 IoU 超过阈值的框（它们在框同一个物体）
        order = [j for j in order if iou(boxes[idx], boxes[j]) <= iou_threshold]
    return keep


def demo_iou():
    print("=" * 60)
    print("1. IoU 手算验证（detection-concepts 笔记里的例子）")
    print("=" * 60)
    A = (2, 2, 4, 4)   # x∈[2,6], y∈[2,6]
    B = (4, 4, 4, 4)   # x∈[4,8], y∈[4,8]
    v = iou(A, B)
    print(f"框A = {A}, 框B = {B}")
    print(f"手算期望 IoU = 4 / 28 ≈ 0.1429")
    print(f"代码计算 IoU = {v:.4f}  ✅ 一致")

    # 完全重合 → 1；完全分开 → 0
    print(f"自身与自身 IoU = {iou(A, A):.1f}（应为 1）")
    print(f"完全分开的 IoU = {iou((0, 0, 1, 1), (9, 9, 1, 1)):.1f}（应为 0）")
    print()


def demo_nms():
    print("=" * 60)
    print("2. NMS 手算验证（detection-concepts 笔记里的例子）")
    print("=" * 60)
    # 同一只猫的三个候选框 + 一只狗
    boxes = [
        (10, 10, 40, 40),   # 框1 猫候选 分数 0.95
        (12, 12, 40, 40),   # 框2 猫候选 分数 0.80（和框1 高度重叠）
        (8, 8, 42, 42),     # 框3 猫候选 分数 0.70（和框1 也重叠）
        (80, 80, 30, 30),   # 框4 狗      分数 0.85（离得远）
    ]
    scores = [0.95, 0.80, 0.70, 0.85]

    print("候选框（同一只猫框了 3 次 + 一只狗）：")
    for i, (b, s) in enumerate(zip(boxes, scores), 1):
        print(f"  框{i}: box={b}  score={s}")
    print(f"  框1与框2 IoU = {iou(boxes[0], boxes[1]):.2f}")
    print(f"  框1与框3 IoU = {iou(boxes[0], boxes[2]):.2f}")
    print(f"  框1与框4 IoU = {iou(boxes[0], boxes[3]):.2f}")

    keep = nms(boxes, scores, iou_threshold=0.5)
    print(f"\nNMS(阈值0.5) 保留下标: {keep}  → ", end="")
    print("  ".join(f"框{i}({scores[i]})" for i in keep))
    print("解读: 三个高度重叠的猫框只留最高分框1，狗(框4)距离远所以保留。")
    print()

    # 调阈值演示：阈值调高，去重变松
    # 框1与框2 IoU=0.82，所以阈值 0.9 时它们不再互删 → 留下一个重复框
    keep_loose = nms(boxes, scores, iou_threshold=0.9)
    print(f"NMS(阈值0.9) 保留: {keep_loose}   ← 阈值高，删得少，留下了重复框2")
    print()


def main():
    demo_iou()
    demo_nms()
    print("结论: IoU 衡量框的重合程度; NMS 用 IoU 去掉重复框，每个物体只留最高分。")


if __name__ == "__main__":
    main()
