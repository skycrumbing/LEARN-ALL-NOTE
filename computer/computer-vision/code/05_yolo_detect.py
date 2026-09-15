# -*- coding: utf-8 -*-
"""
目标检测学习 · 配套代码 05
现代方法实战：YOLO 检测猫/动物/人（detection-algorithms 笔记）

依赖: pip install -r requirements.txt  (需要 ultralytics)
首次运行会自动联网下载 yolov8n.pt 模型（约 6MB），之后离线可用。

输入图片优先级：
  1. samples/ 下的第一张图片（放你自己的猫/动物照片进去）
  2. ultralytics 自带的 bus.jpg（有行人、公交车）
运行后会保存画了检测框的结果到 output/ 目录。

运行：
    python 05_yolo_detect.py
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(SCRIPT_DIR, "samples")
OUT = os.path.join(SCRIPT_DIR, "output")

# COCO 数据集里和"动物"相关的类别（YOLO 预训练在 COCO 上）
ANIMAL_CLASSES = {
    "cat", "dog", "bird", "horse", "sheep", "cow", "elephant",
    "bear", "zebra", "giraffe", "pig", "cattle",
}


def find_input_image():
    exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    if os.path.isdir(SAMPLES):
        for f in sorted(os.listdir(SAMPLES)):
            if f.lower().endswith(exts):
                return os.path.join(SAMPLES, f)
    # 退回 ultralytics 自带的样例图
    import ultralytics
    assets = os.path.join(os.path.dirname(ultralytics.__file__), "assets", "bus.jpg")
    return assets if os.path.exists(assets) else None


def main():
    from ultralytics import YOLO

    os.makedirs(OUT, exist_ok=True)
    path = find_input_image()
    if path is None:
        print("没有找到输入图片。请放一张图片到", SAMPLES, "目录后重试。")
        return

    print("输入图片:", path)
    print("加载 YOLO 模型（首次会联网下载 yolov8n.pt，请稍候）...")
    model = YOLO("yolov8n.pt")   # 轻量版，追求速度

    results = model.predict(path, conf=0.4, verbose=False)
    r = results[0]
    names = model.names  # 类别编号 → 名字

    dets = []
    for box in r.boxes:
        cls_id = int(box.cls[0])
        conf = float(box.conf[0])
        x1, y1, x2, y2 = (int(v) for v in box.xyxy[0].tolist())
        dets.append((names[cls_id], conf, (x1, y1, x2, y2)))

    print(f"\n检测到 {len(dets)} 个目标:")
    animals = []
    for name, conf, (x1, y1, x2, y2) in dets:
        tag = " 🐾动物" if name in ANIMAL_CLASSES else ""
        if name in ANIMAL_CLASSES:
            animals.append(name)
        print(f"  {name:<10} 置信度={conf:.2f}  框=({x1},{y1},{x2},{y2}){tag}")

    if animals:
        print(f"\n发现动物类别: {sorted(set(animals))}  ← 这就是目标检测!")
    else:
        print("\n本图没有检测到动物（试试把你的猫/狗照片放进 samples/）。")

    # 画框保存
    img = r.plot()   # ultralytics 自动画好框
    out_path = os.path.join(OUT, "05_yolo_result.jpg")
    import cv2
    cv2.imwrite(out_path, img)
    print("\n结果已保存:", out_path)


if __name__ == "__main__":
    main()
