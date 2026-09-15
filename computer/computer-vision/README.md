# 计算机视觉 · 目标检测 (Computer Vision / Object Detection)

> 学习目标：理解计算机如何"看"图像，并识别出**人脸、猫、动物、车牌**。

## 这四件事为什么是同一个问题？

"识别到人脸、猫、动物、车牌"看起来是四件事，但它们共享同一个底层任务——**目标检测 (Object Detection)**：

| 你想做的事 | 在计算机视觉里叫什么 | 本质上要回答的两个问题 |
|-----------|---------------------|----------------------|
| 找出猫 / 动物在哪 | 通用目标检测 | ① 在哪（bounding box）② 是什么（类别） |
| 找出人脸在哪 | 人脸检测 | ① 在哪 ② 是不是脸 |
| 认出这是谁 | 人脸识别 | ① 在哪 ② 是谁（更精细的分类） |
| 读出车牌号码 | 车牌识别 (LPR) | ① 车牌在哪 ② 号码是什么（字符分类） |

> **目标检测 = 定位（在哪里）+ 分类（是什么）。** 学会这一套，猫、狗、人脸、车牌、行人……全是同一道题的不同马甲。

## 学习内容

- [x] 图像如何变成数字（像素、通道、预处理）
- [x] 卷积神经网络 CNN（为什么深度学习会"看"图像）
- [x] 目标检测核心概念（边界框、IoU、NMS、评估指标）
- [x] 检测算法演进（Haar → R-CNN 系 → YOLO/SSD → DETR）
- [x] 人脸专项：检测 vs 识别、MTCNN、FaceNet、ArcFace
- [x] 车牌识别专项：LPR 全流程、LPRNet、CTC、中国车牌结构
- [x] **从 0 手写识别猫**：零第三方库的迷你 CNN，含全部数学推导
- [x] 动手：8 个可运行代码示例，把笔记里的概念跑一遍

## 笔记文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `image-basics.md` | 图像如何变成数字：像素矩阵、RGB/BGR、灰度、预处理 | ✅ |
| `cnn-basics.md` | 卷积神经网络：卷积核、特征图、池化、感受野、手算、CNN 简史 | ✅ |
| `detection-concepts.md` | 检测核心概念：bbox、IoU、NMS、置信度、mAP | ✅ |
| `detection-algorithms.md` | 算法演进：滑动窗口+Haar → R-CNN 系 → YOLO/SSD → DETR | ✅ |
| `face-recognition.md` | 人脸专项：检测 vs 识别、MTCNN、FaceNet、ArcFace | ✅ |
| `license-plate.md` | 车牌专项：LPR 流程、LPRNet、CTC、中国车牌结构 | ✅ |
| `cat-from-scratch.md` | **从 0 手写识别猫**：7 步全流程 + 每步数学公式 + 手算数值示例 + dying ReLU 实战坑 | ✅ |
| `backprop-worked-example.md` | **反向传播全程工作示例**：用 `08_trace.log` 真实运行数字，前向→反向→更新一步一数算到底 + 数值梯度校验 | ✅ |
| `gradient-coordination.md` | **参数一起更新会互相干扰吗？**：梯度可加性（一起动≈各自之和）的公式推导 + 玩具手算 + 真实网络三档学习率验证 | ✅ |
| `exercises.md` | 自测习题（含答案） | ✅ |

## 代码示例（放在 `code/`，可真实运行）

| 脚本 | 对应笔记 | 演示内容 | 是否离线可跑 |
|------|---------|---------|-------------|
| `01_image_basics.py` | image-basics | 读取图像、看像素矩阵、BGR→灰度/转换、缩放 | ✅ 离线 |
| `02_convolution.py` | cnn-basics | 纯 numpy 手写卷积：边缘检测 / 模糊 | ✅ 离线 |
| `03_iou_nms.py` | detection-concepts | 手写 IoU 与 NMS 算法并打印演示 | ✅ 离线 |
| `04_haar_face_detect.py` | detection-algorithms | 传统方法实战：Haar 级联检测人脸 | ✅ 离线 |
| `05_yolo_detect.py` | detection-algorithms | 现代方法实战：YOLO 检测猫/动物/人 | ⚠️ 首次需联网下模型 |
| `06_yunet_face_detect.py` | face-recognition | OpenCV DNN YuNet 人脸检测（比 Haar 强） | ⚠️ 首次需联网下模型 |
| `07_license_plate.py` | license-plate | 颜色+轮廓法车牌定位 | ✅ 离线 |
| `08_cat_recognizer_from_scratch.py` | cat-from-scratch | **从 0 手写识别猫**：造数据→卷积→池化→softmax→反向传播→SGD，零第三方库 | ✅ 离线 |

**怎么跑**：

```bash
cd computer/computer-vision/code
pip install -r requirements.txt
python 01_image_basics.py      # 依次运行 01~07
```

> 💡 所有脚本都从 `samples/` 目录读取输入图片。你可以把自己的猫照片、自拍照、车辆照片放进去，脚本会自动使用；没有图片时脚本会用内置合成图 / OpenCV 样例图兜底，保证能跑。

## 学习进度

| 阶段 | 内容 | 完成 |
|------|------|------|
| 1 | 理解图像在计算机里就是一堆数字矩阵 | ✅ |
| 2 | 理解卷积如何"提取特征"、为什么 CNN 适合图像 | ✅ |
| 3 | 掌握 IoU / NMS 并能手算 | ✅ |
| 4 | 讲清两阶段 vs 单阶段检测的演进主线 | ✅ |
| 5 | 分清人脸检测与识别，理解 embedding 比对 | ✅ |
| 6 | 讲清车牌识别全流程与 CTC | ✅ |
| 7 | 跑通全部代码示例，理解每个输出 | ✅ |

## 建议学习顺序

```
image-basics → cnn-basics → detection-concepts → detection-algorithms
    → face-recognition → license-plate
    → cat-from-scratch（把前面的数学全部串起来手写一遍）
    → backprop-worked-example（拿真实日志，把前向/反向的每个数字亲手算一遍）
    → gradient-coordination（为什么参数一起更新不会互相干扰：可加性）
    → exercises
```

读完每一篇笔记，立刻跑对应的代码脚本，把概念和输出对上号，最后用 `exercises.md` 自测。

> 🏆 学完整套后，跑一遍 `code/08_cat_recognizer_from_scratch.py`——零第三方库、约 25 秒，你会亲眼看一个"会认猫的算法"从白纸开始学出来，损失一路下降、测试集 94%~100% 准确率、还能在场景里定位到猫。
