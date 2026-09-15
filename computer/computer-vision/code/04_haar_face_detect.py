# -*- coding: utf-8 -*-
"""
目标检测学习 · 配套代码 04
传统方法实战：Haar 级联检测人脸（detection-algorithms 笔记）
OpenCV 自带级联模型文件，离线可跑。

输入图片优先级：
  1. samples/ 下的第一张图片（放你自己的照片进去）
  2. ultralytics 自带的 zidane.jpg（含人脸）
运行后会保存画了人脸框的结果到 output/ 目录。

运行：
    python 04_haar_face_detect.py
"""
import os
import sys
import cv2

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(SCRIPT_DIR, "samples")
OUT = os.path.join(SCRIPT_DIR, "output")


def find_input_image():
    """在 samples/ 里找第一张可用图片；否则退回 ultralytics 的 zidane.jpg。"""
    os.makedirs(SAMPLES, exist_ok=True)
    exts = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
    if os.path.isdir(SAMPLES):
        for f in sorted(os.listdir(SAMPLES)):
            if f.lower().endswith(exts):
                return os.path.join(SAMPLES, f)
    try:
        import ultralytics
        assets = os.path.join(os.path.dirname(ultralytics.__file__), "assets", "zidane.jpg")
        return assets if os.path.exists(assets) else None
    except ImportError:
        return None


def main():
    os.makedirs(OUT, exist_ok=True)
    path = find_input_image()
    if path is None:
        print("没有找到输入图片。")
        print(f"请放一张含人脸的图片到 {SAMPLES}/ 目录后重试。")
        return

    print("输入图片:", path)
    img = cv2.imread(path)
    if img is None:
        print("读取图片失败。")
        return
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # 加载 Haar 级联（OpenCV 内置，无需下载）
    cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    cascade = cv2.CascadeClassifier(cascade_path)
    if cascade.empty():
        print("级联文件加载失败:", cascade_path)
        return
    print("级联模型:", cascade_path)

    # detectMultiScale 参数：
    #   scaleFactor=1.1 每次放大小窗口的比例（越大越快但可能漏检）
    #   minNeighbors=5  邻居窗口数量，越大越严格（误报少、漏检多）
    #   minSize         最小人脸尺寸，越小越慢但能发现小脸
    faces = cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))

    print(f"\n检测到 {len(faces)} 张人脸:")
    for i, (x, y, w, h) in enumerate(faces, 1):
        print(f"  第{i}张: 左上角({x},{y}) 宽{w} 高{h}  → 框 = ({x},{y},{w},{h})")
        cv2.rectangle(img, (x, y), (x + w, y + h), (0, 255, 0), 2)
        cv2.putText(img, f"face{i}", (x, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)

    out_path = os.path.join(OUT, "04_haar_result.png")
    cv2.imwrite(out_path, img)
    print("\n结果已保存:", out_path)
    if len(faces) == 0:
        print("提示: Haar 对侧脸/光线差的图容易漏检，试试换成正面、光线充足的照片；")
        print("      对比 06_yunet_face_detect.py 看深度模型的效果。")


if __name__ == "__main__":
    main()
