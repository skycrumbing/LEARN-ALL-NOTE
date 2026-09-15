# -*- coding: utf-8 -*-
"""
目标检测学习 · 配套代码 06
深度方法实战：OpenCV DNN 的 YuNet 人脸检测（face-recognition 笔记）
比 Haar 强：抗侧脸/遮挡，还输出 5 个关键点（左右眼、鼻尖、左右嘴角）。

模型：首次运行自动从 opencv_zoo 下载 face_detection_yunet_2023mar.onnx（约 220KB），
      之后离线可用。若下载失败，请按提示手动放到 models/ 目录。

输入图片优先级：
  1. samples/ 下的第一张图片
  2. ultralytics 自带的 zidane.jpg（含人脸）
运行后保存结果到 output/ 目录。

运行：
    python 06_yunet_face_detect.py
"""
import os
import sys
import urllib.request
import cv2

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLES = os.path.join(SCRIPT_DIR, "samples")
MODELS = os.path.join(SCRIPT_DIR, "models")
OUT = os.path.join(SCRIPT_DIR, "output")

MODEL_URL = ("https://github.com/opencv/opencv_zoo/raw/main/models/"
             "face_detection_yunet/face_detection_yunet_2023mar.onnx")
MODEL_PATH = os.path.join(MODELS, "face_detection_yunet.onnx")

LANDMARK_NAMES = ["左眼", "右眼", "鼻尖", "左嘴角", "右嘴角"]


def ensure_model():
    """模型不存在时自动下载；失败则提示手动放置。"""
    if os.path.exists(MODEL_PATH):
        return True
    os.makedirs(MODELS, exist_ok=True)
    print("首次运行，正在下载 YuNet 模型...")
    try:
        urllib.request.urlretrieve(MODEL_URL, MODEL_PATH)
        print("下载完成:", MODEL_PATH)
        return True
    except Exception as e:
        print("自动下载失败:", e)
        print(f"请手动下载该文件放到 {MODELS}/face_detection_yunet.onnx ：")
        print("  ", MODEL_URL)
        return False


def find_input_image():
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
    if not ensure_model():
        return
    os.makedirs(OUT, exist_ok=True)

    path = find_input_image()
    if path is None:
        print("没有找到输入图片。请放一张含人脸的图片到", SAMPLES, "目录后重试。")
        return
    print("输入图片:", path)

    img = cv2.imread(path)
    h, w = img.shape[:2]
    # 创建 YuNet 检测器，输入尺寸需要是 32 的倍数，我们直接用原图尺寸
    detector = cv2.FaceDetectorYN.create(
        MODEL_PATH, "", (w, h), score_threshold=0.7, nms_threshold=0.3, top_k=20)

    retval, faces = detector.detect(img)
    # faces: (N, 15)，前 4 个是框 (x,y,w,h)，后 5 组是 (x,y) 关键点
    if retval < 1:
        print("\n没有检测到人脸。试试正面、光线充足的照片。")
        return

    print(f"\n检测到 {len(faces)} 张人脸（YuNet，深度模型）:")
    for i, f in enumerate(faces, 1):
        x, y, fw, fh = (int(v) for v in f[:4])
        print(f"  第{i}张: 框=({x},{y},{fw},{fh})")
        for k, name in enumerate(LANDMARK_NAMES):
            lx, ly = f[4 + 2 * k], f[5 + 2 * k]
            print(f"      {name}: ({lx:.0f},{ly:.0f})")
        cv2.rectangle(img, (x, y), (x + fw, y + fh), (0, 255, 0), 2)
        # 画 5 个关键点
        for k in range(5):
            cx, cy = int(f[4 + 2 * k]), int(f[5 + 2 * k])
            cv2.circle(img, (cx, cy), 3, (0, 0, 255), -1)

    out_path = os.path.join(OUT, "06_yunet_result.png")
    cv2.imwrite(out_path, img)
    print("\n结果已保存:", out_path)
    print("说明: 关键点用于人脸对齐——把歪的脸转正，是识别(这是谁)的前置步骤。")


if __name__ == "__main__":
    main()
