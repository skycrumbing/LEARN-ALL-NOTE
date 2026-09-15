# -*- coding: utf-8 -*-
"""
从 0 开始识别猫 —— 零第三方库的完整算法
================================================================
只用 Python 标准库（math / random），不用 numpy、OpenCV、任何现成模型。

▍程序在做什么（一句话）
  从无到有搭一个"迷你 CNN"：自己造数据 → 自己写卷积网络 → 自己写训练，
  训练完用它对"猫/非猫"做分类，还能在一个大场景里用滑动窗口找出猫在哪。

▍七步总览（每一步做什么，代码入口在哪个函数）
  步骤   在做什么                                    代码入口
  ────────────────────────────────────────────────────────────────
  0 造数据  程序自己"画"80 只猫 + 80 张非猫图          make_dataset   (L175)
  1 前向    卷积→ReLU→池化→全连接→softmax，把一张    forward        (L256)
            16×16 的图变成两个概率 [P(非猫), P(猫)]
  2 反向    用链式法则倒推：每个参数对这次错误         backward       (L293)
            的"责任"有多大（算出梯度）
  3 更新    每个参数朝梯度的反方向挪一小步（SGD），    update/train   (L348/361)
            让下次预测更接近正确答案
  4 评估    在没训练过的测试集上打分                  evaluate       (L395)
  5 看核    打印模型自己"长出来"的特征检测器          show_kernel    (L411)
  6 彩蛋    滑动窗口扫描 40×40 场景，定位猫在哪        find_cat_in_scene (L425)
            （这就是目标检测的雏形）

▍为什么用 16×16 小图？
  尺寸小，这三层网络几秒就能跑完；每一格、每一步都小到能拿纸笔验算，
  方便你对着公式理解。真实世界里的 CNN 只是把这张图放大了 100 倍。

运行：python 08_cat_recognizer_from_scratch.py
（生成的图片保存在 code/output/ 目录；TRACE_ALL=True 时，训练每一步的数值和
 计算过程都会同时打屏并写进 code/output/08_trace.log，只想看结果就把 TRACE_ALL 改成 False）
"""
import math        # 数学函数：exp(指数)、hypot(距离)
import os          # 路径拼接、建目录
import random      # 随机数：造数据时用来加噪声 / 随机形状
import struct      # 二进制打包：写 PNG 头时用
import sys         # 调整终端编码，让中文能显示
import time        # 计时：看训练花了多久
import zlib        # 压缩：PNG 的 IDAT 数据块要用它压缩

# 让中文在 Windows 终端正常显示（失败则忽略，不影响运行）
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 输出图片目录（和其他 01~07 脚本一致）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(SCRIPT_DIR, "output")


def write_png(path, rows):
    """把灰度图（值 0~1 的二维矩阵）写成一个 PNG 文件。返回文件路径。
    只用标准库 struct + zlib 手工编码 PNG 格式（IHDR/IDAT/IEND 块），
    不依赖任何第三方库——延续"从 0 开始"的主题。
    流程：先把 0~1 的浮点值乘 255 变成 0~255 字节，再按 PNG 规范打包。
    """
    h, w = len(rows), len(rows[0])          # 图的高、宽

    def chunk(typ, data):
        # PNG 的一个"块"= 长度(4字节) + 类型(4字节) + 数据 + CRC32 校验(4字节)
        c = struct.pack(">I", len(data)) + typ + data
        c += struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)
        return c

    # PNG 签名 + IHDR 头（8 位灰度，无交错）
    sig = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 0, 0, 0, 0)   # 8位, 灰度, 标准, 无过滤, 无交错
    # 每一行前加一个"无过滤"字节(0)，再 zlib 压缩成 IDAT 数据
    raw = b"".join(b"\x00" + bytes(int(max(0.0, min(1.0, v)) * 255) for v in row) for row in rows)
    png = sig + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)
    return path

# 想让结果可复现，去掉这一行即可每次不同
random.seed(42)

# ═══════════════════════════════════════════════════════════
# 教学开关：TRACE_ALL = True 时，训练会把每一步的数值都打印出来——
#   初始参数 / 第 1 轮第 1 张样本的完整前向+反向+更新 / 每 50 轮参数快照 / 最终参数。
# 只想看最终结果（干净输出），改成 False 即可，行为与旧版一致。
TRACE_ALL = True
# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
# 日志文件：TRACE_ALL=True 时，整个运行过程（每个步骤的数值 + 计算过程）
# 会同时打印到终端并写进 08_trace.log——对着日志文件即可逐行核对每一步怎么算。
LOG_PATH = os.path.join(OUT, "08_trace.log")
_LOG_FILE = None   # 日志文件句柄（main 里按需打开）


class _Tee:
    """stdout 代理：同一行内容同时写终端和日志文件（不重复、不乱序）。"""
    def __init__(self, stream, fh):
        self.stream, self.fh = stream, fh

    def write(self, s):
        self.stream.write(s)
        self.fh.write(s)
        self.fh.flush()
        return len(s)

    def flush(self):
        self.stream.flush()
        self.fh.flush()


# ═══════════════════════════════════════════════════════════

# ═══════════════════════════════════════════════════════════
# PART 0. 造数据：在 16×16 网格上"画"猫 / 非猫
# ═══════════════════════════════════════════════════════════
# 图像 = 二维矩阵，每个元素是 0~1 的灰度（0=黑，1=白）。
# 约定：行=y 坐标、列=x 坐标，即 img[y][x] 表示"这一格有多亮"。
SIZE = 16   # 每张图 16×16 = 256 个像素


def in_triangle(px, py, tri):
    """判断点 (px,py) 是否在三角形 tri=[(x1,y1),(x2,y2),(x3,y3)] 内部。
    数学方法：用叉积判断"点在三角形内部 ⟺ 点和三条边都在同一侧"。
       cross 叉积的符号表示两条有向边的相对转向；
       side(p,q,r) 算的是"从 p→q 看 r 在左边还是右边"。
    三条边算出的符号一致 → 点在三角形内；否则在外。
    """
    def cross(ax, ay, bx, by):
        return ax * by - ay * bx                     # 二维叉积（带符号面积×2）

    def side(p, q, r):
        # r 相对有向边 p→q 的位置：正=左边，负=右边，0=刚好在线上
        return cross(q[0] - p[0], q[1] - p[1], r[0] - p[0], r[1] - p[1])

    s1 = side(tri[0], tri[1], (px, py))
    s2 = side(tri[1], tri[2], (px, py))
    s3 = side(tri[2], tri[0], (px, py))
    # 三个符号要么都≥0（都在同侧）要么都≤0 → 在内部
    return (s1 >= 0 and s2 >= 0 and s3 >= 0) or (s1 <= 0 and s2 <= 0 and s3 <= 0)


def make_cat(sx=0, sy=0):
    """画一只猫：圆头 + 两个尖耳朵 + 两个暗色眼睛点。返回 16×16 灰度矩阵。
    sx, sy 是整体平移（取 -1/0/1），制造"猫出现在不同位置"的多样性——
    让模型学会"猫挪一点还是猫"，而不是死记某个固定位置的模板。
    """
    img = [[0.0] * SIZE for _ in range(SIZE)]        # 全黑画布（背景=0）

    def ok(x, y):
        return 0 <= x < SIZE and 0 <= y < SIZE       # 越界的像素直接忽略

    # 头：一个圆。数学判定："点(x,y) 到圆心 (cxc,cyc) 的距离 ≤ 半径 4" 就在圆内
    cxc, cyc = 8 + sx, 9 + sy
    for y in range(SIZE):
        for x in range(SIZE):
            if (x - cxc) ** 2 + (y - cyc) ** 2 <= 4 ** 2:
                img[y][x] = 0.85                     # 圆内全部涂成浅灰（猫身）

    # 耳朵：两个三角形（都在头顶，尖顶朝上）
    ears = [
        [(4 + sx, 7 + sy), (6 + sx, 7 + sy), (4 + sx, 2 + sy)],    # 左耳
        [(10 + sx, 7 + sy), (12 + sx, 7 + sy), (12 + sx, 2 + sy)], # 右耳
    ]
    for tri in ears:
        for y in range(SIZE):
            for x in range(SIZE):
                if in_triangle(x, y, tri):
                    img[y][x] = 0.85                 # 三角形内的格子也涂浅灰

    # 眼睛：两个暗色"十字菱形"。每个眼睛在 (ex,ey) 周围曼哈顿距离 ≤1
    # 的 5 个格子都涂深灰——16×16 的小图上这样才像一个"黑眼点"
    for (ex, ey) in [(6 + sx, 8 + sy), (10 + sx, 8 + sy)]:
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if abs(dx) + abs(dy) <= 1 and ok(ex + dx, ey + dy):
                    img[ey + dy][ex + dx] = 0.15
    return img


def print_img(img):
    """把一张灰度图打印成 ASCII 字符图，方便肉眼看到模型在学什么。
    0~1 的灰度值映射到 10 个字符：" .:-=+*#%@"（越靠右越亮）。
    """
    chars = " .:-=+*#%@"
    for row in img:
        print("  " + "".join(chars[min(9, int(v * 10))] for v in row))


def add_noise(img, brightness=1.0, noise=0.15):
    """亮度抖动 + 随机噪声：让同一只猫的每张"照片"都略有不同。
    brightness：整张图统一乘一个亮度系数（模拟光线明暗）；
    noise     ：每个像素独立加一个随机扰动（模拟相机噪点）。
    这相当于数据增强——给模型更多样的样本，防止过拟合。
    """
    out = []
    for row in img:
        r = []
        for v in row:
            v = v * brightness + (random.random() - 0.5) * noise   # 亮度→抖动→加噪
            r.append(max(0.0, min(1.0, v)))                        # 钳制回 0~1
        out.append(r)
    return out


def make_noncat():
    """画一张"不是猫"的图：随机圆形 / 随机矩形 / 随机噪声块，三选一。
    目的：让模型不能靠"图里有没有亮块"这种偷懒特征过关，
    必须真的学到"猫的轮廓（圆头+双耳+双眼）"才分得清。
    """
    img = [[0.0] * SIZE for _ in range(SIZE)]
    kind = random.randrange(3)
    if kind == 0:
        # 随机位置、随机大小的一个圆
        cx, cy = random.random() * SIZE, random.random() * SIZE
        r = 2 + random.random() * 4
        for y in range(SIZE):
            for x in range(SIZE):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    img[y][x] = 0.8
    elif kind == 1:
        # 随机位置、随机大小的一个矩形
        x0 = random.randrange(SIZE - 6)
        y0 = random.randrange(SIZE - 6)
        x1 = x0 + 2 + random.randrange(4)
        y1 = y0 + 2 + random.randrange(4)
        for y in range(y0, y1):
            for x in range(x0, x1):
                img[y][x] = 0.8
    else:
        # 三个小圆块（看起来像"碎屑"）
        for _ in range(3):
            cx, cy = random.random() * SIZE, random.random() * SIZE
            r = 1 + random.random() * 1.5
            for y in range(SIZE):
                for x in range(SIZE):
                    if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                        img[y][x] = 0.8
    return add_noise(img, noise=0.15)


def make_dataset(n_cat, n_noncat):
    """造出一个完整的数据集（第 0 步）。返回 [(img, label)]：
       img   = 16×16 灰度矩阵（0~1）
       label = 1 表示猫，0 表示非猫
    做法：
      1. 画 n_cat 只猫：每只随机平移 (±1) + 随机亮度抖动 + 噪声；
      2. 画 n_noncat 张随机形状，同样加噪声；
      3. 全部打乱顺序，返回。
    这就是监督学习的"训练数据"——连数据都是程序自己造的，不借任何现成数据集。
    """
    data = []
    for _ in range(n_cat):
        # 每只猫整体随机平移一点，再叠亮度抖动 + 噪声 → 同一只猫的"不同照片"
        sx, sy = random.choice([-1, 0, 1]), random.choice([-1, 0, 1])
        img = add_noise(make_cat(sx, sy), brightness=0.9 + 0.2 * random.random())
        data.append((img, 1))                        # 标签 1 = 猫
    for _ in range(n_noncat):
        data.append((make_noncat(), 0))              # 标签 0 = 非猫
    random.shuffle(data)                             # 打乱，别让猫全在前面
    return data


# ═══════════════════════════════════════════════════════════
# PART 1. 网络前向：卷积 → ReLU → 池化 → 全连接 → softmax
# ═══════════════════════════════════════════════════════════
# 网络结构（数据从下往上流）：
#   16×16 输入
#   → 卷积层1（2 个 3×3 核）→ 2×14×14
#   → ReLU（把负响应清零）
#   → 最大池化 2×2 → 2×7×7 = 98 个特征
#   → 全连接（98 → 2）→ softmax → [P(非猫), P(猫)]
#
# 参数规模：
#   W1: 2 个 3×3 核 = 18 个权重 + 2 个偏置
#   W2: 98×2 = 196 个权重 + 2 个偏置
#   一共 218 个参数 —— 模型要"学"的就是这 218 个数。


def conv2d(x, w, b, stride=1):
    """二维卷积（第 1 步之第一层）——用一个小窗口扫描全图找局部特征。
    数学：输出 (i,j) = Σ_{u,v} w[u,v]·x[i+u, j+v] + b
    直觉：3×3 的"检测窗" w 在 16×16 大图上逐像素滑动，
          每停一处就把窗内 9 个像素加权求和（再加偏置 b），
          写进输出的一个格子。w 里哪些位置是正、哪些是负，
          决定了它在"找什么模式"（正负对比强烈 = 在找亮度突变/边缘）。
    输出尺寸 = (H - k + 1) × (W - k + 1) = (16-3+1)² = 14×14
    """
    H, W = len(x), len(x[0])                         # 输入图高、宽
    k = len(w)                                       # 卷积核边长（这里=3）
    out_h, out_w = H - k + 1, W - k + 1              # 输出图尺寸
    out = [[0.0] * out_w for _ in range(out_h)]
    for i in range(out_h):
        for j in range(out_w):
            s = b                                    # 先加上偏置
            for u in range(k):
                row = x[i + u]                       # 取输入的第 i+u 行
                for v in range(k):
                    s += row[j + v] * w[u][v]        # 窗内每个像素 × 对应权重
            out[i][j] = s
    return out


def relu(a):
    """ReLU 激活（第 1 步之第二层）——保留正响应，消灭负响应。
    数学：max(0, x)。负的卷积响应没有意义（等于"没检测到该特征"），
    直接归零；这样也保证了梯度在正区间不会消失（见 PART 2 的 ReLU 反向）。
    """
    return [[max(0.0, v) for v in row] for row in a]


def maxpool2x2(a):
    """最大池化 2×2（第 1 步之第三层）——压缩尺寸，只留"最强"的响应。
    数学：输出 = 每个 2×2 窗口里最大的那个值。
    直觉：窗口里"最明显的特征"才值得保留，模糊的细节丢掉；
          尺寸 14×14 → 7×7，计算量减半，还让模型对微小位移更不敏感。
    额外返回 mask：记录每个最大值来自原图的哪个坐标，反向传播要用它
    "把梯度还给最大值"（见 backward 第 4 步）。
    """
    H, W = len(a), len(a[0])
    ph, pw = H // 2, W // 2                          # 输出尺寸
    p = [[0.0] * pw for _ in range(ph)]
    mask = [[None] * pw for _ in range(ph)]
    for i in range(ph):
        for j in range(pw):
            best, bi, bj = -1e18, 2 * i, 2 * j       # best 取一个极小的初值
            for di in range(2):
                for dj in range(2):
                    v = a[2 * i + di][2 * j + dj]
                    if v > best:
                        best, bi, bj = v, 2 * i + di, 2 * j + dj
            p[i][j] = best                           # 窗口最大值 = 输出
            mask[i][j] = (bi, bj)                    # 记下它在哪
    return p, mask


def softmax(z):
    """softmax（第 1 步之最后一层）——把 2 个实数变成"和为 1"的概率。
    数学：p_k = e^{z_k} / Σ_j e^{z_j}
    直觉：先算每个数的指数（拉大差距），再除以总和做归一化，
          这样大的 z 对应大的概率，且两个概率加起来恒等于 1。
    先减去最大值 m 再取指数：e^{z-m} 不会溢出（这是标准做法）。
    """
    m = max(z)
    e = [math.exp(v - m) for v in z]
    s = sum(e)
    return [v / s for v in e]


def forward(img, W1, b1, W2, b2):
    """前向传播（第 1 步）——把一张 16×16 的图算成两个概率。
    输入：img(16×16 灰度) + 全部参数 (W1,b1,W2,b2)
    输出：probs = [P(非猫), P(猫)]，以及 cache——
          反向传播要用的所有中间结果，一次前向全记下来，避免重算。
    数据流转：16×16 → 卷积 → 2×14×14 → ReLU → 池化 → 2×7×7
            → 摊平成 98 维 → 全连接 → 2 维 → softmax → 概率。
    """
    # 卷积：用 2 个不同的核各扫一遍，得到 2 张 14×14 特征图
    z1 = [conv2d(img, W1[0], b1[0]), conv2d(img, W1[1], b1[1])]
    a1 = [relu(z1[0]), relu(z1[1])]                       # ReLU：负响应清零
    p0, m0 = maxpool2x2(a1[0])                            # 池化 → 7×7（每通道一张）
    p1_, m1_ = maxpool2x2(a1[1])
    p1 = (p0, p1_)
    masks = (m0, m1_)                                     # 每个最大值的来源坐标

    # 摊平：把 2×7×7=98 个特征按"通道→行→列"的顺序排成一根 98 维向量 f
    f = []
    for k in range(2):
        for i in range(7):
            for j in range(7):
                f.append(p1[k][i][j])

    # 全连接：z2 = W2·f + b2 → 2 个实数。
    # 每个输出 = 98 个特征各自加权求和 + 偏置；W2 是"哪些特征指向猫"的依据
    z2 = [sum(W2[k][b] * f[b] for b in range(len(f))) + b2[k] for k in range(2)]
    probs = softmax(z2)                                   # 归一化成概率
    cache = (z1, a1, p1, masks, f, z2, probs)             # 全部中间结果留给反向
    return probs, cache


# ═══════════════════════════════════════════════════════════
# PART 2. 反向传播：链式法则算每个参数的"责任"
# ═══════════════════════════════════════════════════════════
# 损失 L = -ln p_y（交叉熵，y 是这张图的真实类别）。
#   p_y 越大（模型越自信且猜对）→ L 越小。目标是让 L 尽量小。
#
# 反向传播就是从损失"倒着流回去"，逐层用链式法则问：
#   "L 变大一点，每个参数要背多大的锅？" 这个"锅"就是梯度。
# 梯度公式一览（从后往前）：
#   dL/dz2 = p - onehot(y)                     softmax+交叉熵的解析梯度
#   dL/dW2 = dL/dz2 ⊗ fᵀ                       全连接权重的梯度
#   dL/df  = W2ᵀ · dL/dz2                      传给池化输出的梯度
#   池化反向：梯度只回传给 2×2 窗口里"最大的那个"像素，其余为 0
#   ReLU 反向：z>0 处梯度原样通过，z≤0 处梯度归 0
#   卷积反向：dL/dw[u][v] = Σ_{i,j} (dL/dz1[i][j]) · x[i+u][j+v]
#
# 一句话直觉：前向是从图→概率，反向就是沿着同一条路，把"错误"倒着
# 分摊给每一步（每层都有自己的"分锅公式"），最终算出每个参数的梯度。


def backward(img, y, cache, W2):
    """反向传播（第 2 步）——算出一整套梯度。
    输入：img(前向用的原图)、y(真实标签)、cache(前向存的中间结果)、W2
    输出：一个 dict，装着每一处的梯度（不止参数梯度，还有各中间量的梯度），
         形状和对应的量一一对应。训练更新只用 dW1/db1/dW2/db2；
         其余（dz2/df/dp1/da1/dz1）是为了教学追踪时把每一步数值都打印出来。
    顺序正好和前向相反：softmax→全连接→还原形状→池化→ReLU→卷积。
    """
    z1, a1, p1, masks, f, z2, probs = cache        # 把前向存的东西全部取出来

    # ── 1. softmax+交叉熵梯度：dz2 = p - onehot(y) ──────────────
    # 这是整个反向的"源头"：对真实类别的概率期望是 1（onehot），
    # 实际给了 probs[k]，差值就是梯度。猜对了→≈0，猜错了→方向指向正确类。
    dz2 = [probs[k] - (1.0 if k == y else 0.0) for k in range(2)]

    # ── 2. 全连接层梯度 ──────────────────────────────────────
    # dW2[a][b] = dz2[a]·f[b]：误差 × 那个输入特征
    dW2 = [[dz2[a] * f[b] for b in range(len(f))] for a in range(2)]
    db2 = dz2[:]                                    # 偏置的梯度就是误差本身
    # df[b] = Σ_a W2[a][b]·dz2[a]：把误差通过权重"分给"每个输入特征
    df = [sum(W2[a][b] * dz2[a] for a in range(2)) for b in range(len(f))]

    # ── 3. 摊平 → 还原成 2×7×7（和 forward 的摊平顺序一致）──
    # 池化输出 p1 是 2×7×7，刚才被摊平成 98 维向量 f；
    # 现在 df 也是 98 维，按同样顺序塞回 2×7×7 的形状 dp1，才能继续往上传
    dp1 = [[[0.0] * 7 for _ in range(7)] for _ in range(2)]
    idx = 0
    for k in range(2):
        for i in range(7):
            for j in range(7):
                dp1[k][i][j] = df[idx]
                idx += 1

    # ── 4. 池化反向：梯度还给每个窗口里"最大的那个"像素 ─────
    # 前向时 2×2 窗口只有最大值传了下去，其余 3 个"死了"；
    # 所以反向时梯度也只还给最大值（记在 masks 里），其余 3 个分到 0
    da1 = [[[0.0] * 14 for _ in range(14)] for _ in range(2)]
    for k in range(2):
        for i in range(7):
            for j in range(7):
                bi, bj = masks[k][i][j]
                da1[k][bi][bj] += dp1[k][i][j]

    # ── 5. ReLU 反向：z>0 才通过 ─────────────────────────────
    # ReLU 在前向把 z≤0 的杀成 0，那些位置没参与输出，梯度也归 0；
    # z>0 的梯度原样通过（这就是为什么 ReLU 不容易梯度消失）
    dz1 = [[[0.0] * 14 for _ in range(14)] for _ in range(2)]
    for k in range(2):
        for i in range(14):
            for j in range(14):
                if z1[k][i][j] > 0:
                    dz1[k][i][j] = da1[k][i][j]

    # ── 6. 卷积核梯度：dL/dw[u][v] = Σ dz1[i][j]·x[i+u][j+v] ──
    # 卷积的权重被"滑过的每个位置共用"，所以梯度要把所有位置累加；
    # 每个位置的贡献 = 那个位置的误差 dz1[i][j] × 它对应的输入像素
    dW1 = [[[0.0] * 3 for _ in range(3)] for _ in range(2)]
    db1 = [0.0, 0.0]
    for k in range(2):
        for i in range(14):
            for j in range(14):
                g = dz1[k][i][j]
                db1[k] += g                          # 偏置梯度 = 所有位置误差之和
                for u in range(3):
                    for v in range(3):
                        dW1[k][u][v] += g * img[i + u][j + v]

    return {"dW1": dW1, "db1": db1, "dW2": dW2, "db2": db2,
            "dz2": dz2, "df": df, "dp1": dp1, "da1": da1, "dz1": dz1}


# ═══════════════════════════════════════════════════════════
# PART 3.5. 教学追踪：把每一步的参数/数值打印出来
# ═══════════════════════════════════════════════════════════
# TRACE_ALL=True 时，train() 会调用下面这些打印函数，把每一步的数值
# 原样打给你看：初始参数 → 第 1 张样本的完整前向+反向+更新 → 每 50 轮参数快照 → 最终参数。
# 这样你能亲眼看到"每个数是怎么被算出来的、又是怎么被 SGD 一步步改小的"。

def _f(v):
    """单个数值 → 固定宽度字符串（3 位小数，带正负号，方便对位阅读）。"""
    return f"{v:+7.3f}"

def _fmt_vec(vec):
    """一维数组 → 一行字符串。"""
    return " ".join(_f(v) for v in vec)

def _fmt_vec_wrapped(vec, per_line=24):
    """一维数组 → 多行字符串（每行最多 per_line 个，避免一行太长）。"""
    lines = []
    for i in range(0, len(vec), per_line):
        lines.append("  " + " ".join(_f(v) for v in vec[i:i + per_line]))
    return "\n".join(lines)

def _fmt_mat(mat):
    """二维数组 → 多行字符串（每行一个数组行，逐列对齐）。"""
    return "\n".join("    " + " ".join(_f(v) for v in row) for row in mat)

def _fmt_cube(cube):
    """三维数组 → 按通道分块打印。"""
    return "\n".join(f"   通道{k}:\n{_fmt_mat(m)}" for k, m in enumerate(cube))

def print_params(W1, b1, W2, b2):
    """把全部 218 个参数完整打印出来（初始/快照/最终都会用到）。"""
    print("  W1（2 个 3×3 卷积核）:")
    print(_fmt_cube(W1))
    print("  b1（卷积偏置）:", _fmt_vec(b1))
    print("  W2（全连接权重，2 行 × 98 列）:")
    for a in range(2):
        print(f"    [{a}]")
        print(_fmt_vec_wrapped(W2[a], per_line=20))
    print("  b2（全连接偏置）:", _fmt_vec(b2))

def show_sample_trace(img, y, W1, b1, W2, b2, cache, g, lr, loss):
    """把"第 1 轮第 1 张样本"从输入到更新【完整地】讲清楚——
    每一步都给出：公式 → 代入数字的算例 → 结果值，全程一步一数可对账。
    cache = 前向存的中间结果；g = backward 返回的全部梯度 dict。
    """
    z1, a1, p1, masks, f, z2, probs = cache
    cu = lambda v: f"{v:.3f}"          # 紧凑格式（乘积项用，不带强制正号）
    cs = lambda v: f"{v:+.3f}"         # 带正负号（值用）

    print("\n" + "═" * 70)
    print("【全量数值演示】epoch 1 · 第 1 张样本 —— 每一步：公式 → 代入 → 结果")
    print("═" * 70)

    # ── ① 输入 ──────────────────────────────────────────────
    print("\n① 输入 img（16×16 灰度，0=黑 1=白）:")
    print(_fmt_mat(img))
    print(f"   真实标签 y = {y}（1=猫，0=非猫）—— 模型任务：看到这张图，输出 P(猫) 尽量接近 1")

    # ── ② 卷积层 ────────────────────────────────────────────
    print("\n② 卷积层（第 1 层）· 用 2 个 3×3 的核扫描全图，找局部特征")
    print("   公式: z1[k][i][j] = b1[k] + Σ_{u,v=0..2} W1[k][u][v]·x[i+u][j+v]")
    print("   当前 W1（2 个 3×3 核）:")
    print(_fmt_cube(W1))
    print("   b1:", _fmt_vec(b1))
    for k in range(2):
        prods = [W1[k][u][v] * img[u][v] for u in range(3) for v in range(3)]
        total = b1[k] + sum(prods)
        print(f"   算例·z1[{k}][0][0]（窗口盖住左上角 9 个像素）:")
        print("      Σ乘积 = " + " + ".join(cu(p) for p in prods))
        print(f"      z1[{k}][0][0] = {cs(b1[k])} + Σ乘积 = {cs(total)}")
        prods2 = [W1[k][u][v] * img[2 + u][2 + v] for u in range(3) for v in range(3)]
        total2 = b1[k] + sum(prods2)
        print(f"   算例·z1[{k}][2][2]（窗口滑到猫头顶附近）:")
        print("      Σ乘积 = " + " + ".join(cu(p) for p in prods2))
        print(f"      z1[{k}][2][2] = {cs(b1[k])} + Σ乘积 = {cs(total2)}")
    print("   结果 z1（14×14，未激活）:")
    for k in range(2):
        print(f"     z1[{k}]:")
        print(_fmt_mat(z1[k]))

    # ── ③ ReLU ──────────────────────────────────────────────
    print("\n③ ReLU（第 2 层）· 把负响应清零，只留正的")
    print("   公式: a1[k][i][j] = max(0, z1[k][i][j])")
    for k in range(2):
        neg = next(((i, j, z1[k][i][j]) for i in range(14) for j in range(14)
                    if z1[k][i][j] < 0), None)
        pos = next(((i, j, z1[k][i][j]) for i in range(14) for j in range(14)
                    if z1[k][i][j] > 0), None)
        if neg:
            i, j, z = neg
            print(f"   算例·a1[{k}][{i}][{j}] = max(0, {cs(z)}) = 0.000（<0，清零='没检测到该特征'）")
        if pos:
            i, j, z = pos
            print(f"   算例·a1[{k}][{i}][{j}] = max(0, {cs(z)}) = {cu(z)}（>0，保留='检测到该特征'）")
    print("   结果 a1（14×14）:")
    for k in range(2):
        print(f"     a1[{k}]:")
        print(_fmt_mat(a1[k]))

    # ── ④ 池化 ──────────────────────────────────────────────
    print("\n④ 最大池化（第 3 层）· 每 2×2 窗口只留最大的值（14×14 → 7×7）")
    print("   公式: p1[k][i][j] = max(2×2 窗口 a1[k][2i:2i+2][2j:2j+2])")
    print("   同时记住最大值来自哪个坐标（mask）——反向传播时把梯度只还给那里")
    for k in range(2):
        win = [a1[k][di][dj] for di in range(2) for dj in range(2)]
        mval = max(win)
        print(f"   算例·p1[{k}][0][0] = max({', '.join(cu(v) for v in win)}) = {cu(mval)}"
              f"（最大值来自坐标 {masks[k][0][0]}）")
    print("   结果 p1（7×7）:")
    for k in range(2):
        print(f"     p1[{k}]:")
        print(_fmt_mat(p1[k]))

    # ── ⑤ 摊平 ──────────────────────────────────────────────
    print("\n⑤ 摊平 · 把 2×7×7=98 个值按'通道→行→列'排成一根 98 维向量 f")
    print("   规则: f[idx] 依次取 p1[通道][行][列]")
    print(f"   f[0]=p1[0][0][0]={cu(f[0])}  f[1]=p1[0][0][1]={cu(f[1])}  "
          f"…  f[48]=p1[1][0][0]={cu(f[48])}  f[49]=p1[1][0][1]={cu(f[49])}  …  f[97]=p1[1][6][6]={cu(f[97])}")
    print("   结果 f（98 维）:")
    print("   " + _fmt_vec_wrapped(f))

    # ── ⑥ 全连接 ────────────────────────────────────────────
    print("\n⑥ 全连接（第 4 层）· 98 个特征 → 2 个实数（每个类别的'得分'）")
    print("   公式: z2[k] = b2[k] + Σ_{b=0..97} W2[k][b]·f[b]")
    print("   当前 W2（2×98）:")
    for a in range(2):
        print(f"     [{a}]")
        print(_fmt_vec_wrapped(W2[a]))
    print("   b2:", _fmt_vec(b2))
    for k in range(2):
        head = " + ".join(f"{cu(W2[k][b])}×{cu(f[b])}" for b in range(5))
        total = b2[k] + sum(W2[k][b] * f[b] for b in range(98))
        print(f"   算例·z2[{k}] = {cs(b2[k])} + {head} + …(共98项) = {cs(total)}")
    print("   z2 =", _fmt_vec(z2))

    # ── ⑦ softmax ───────────────────────────────────────────
    print("\n⑦ softmax（输出层）· 把 2 个得分变成'和为 1'的概率")
    print("   公式: p_k = e^(z_k − m) / Σ_j e^(z_j − m)，其中 m = max(z)（先减 m 防止 e 溢出）")
    m = max(z2)
    e = [math.exp(v - m) for v in z2]
    s = sum(e)
    for k in range(2):
        print(f"   算例·e^(z{k}−m) = e^({cs(z2[k])} − {cs(m)}) = e^({cs(z2[k] - m)}) = {e[k]:.4f}")
    print(f"   算例·分母（所有 e 之和）Σ = {s:.4f}")
    for k in range(2):
        print(f"   算例·probs[{k}] = {e[k]:.4f} / {s:.4f} = {probs[k]:.4f}")
    print("   结果 probs = [P(非猫), P(猫)] =", _fmt_vec(probs))
    print(f"   交叉熵损失 L = −ln(P(y={y})) = −ln({probs[y]:.4f}) = {loss:.4f}  ← 训练要最小化的就是它")

    # ── ⑧ 反向传播 ──────────────────────────────────────────
    print("\n⑧ 反向传播 · 顺着前向的路，把'错误 L'倒着分给每个参数（链式法则）")
    print("   每个梯度 = 上游传来的误差 × 本步的局部关系，方向都指向让 L 变小")
    print()
    print("   ⑧-1 softmax+交叉熵的梯度（整个反向的源头）")
    print("       公式: dz2[k] = probs[k] − onehot(y)[k]")
    print(f"       dz2 = [{cs(g['dz2'][0])}, {cs(g['dz2'][1])}]")
    print(f"       解释: 对真实类 y={y}，期望概率是 1，实际只给到 {probs[y]:.3f}，")
    print(f"            差 {probs[y]-1:+.3f} 是负的 → 推动网络下次把'猫'的概率抬上去")
    print()
    print("   ⑧-2 全连接权重梯度 dW2（误差 × 对应的输入特征）")
    print("       公式: dW2[a][b] = dz2[a] × f[b]")
    print(f"       算例·dW2[0][0] = {cs(g['dz2'][0])} × {cu(f[0])} = {cs(g['dW2'][0][0])}")
    print(f"       算例·dW2[1][0] = {cs(g['dz2'][1])} × {cu(f[0])} = {cs(g['dW2'][1][0])}")
    print("       结果 dW2（2×98）:")
    for a in range(2):
        print(f"         [{a}]")
        print(_fmt_vec_wrapped(g["dW2"][a], per_line=20))
    print("       db2（偏置的梯度就是误差本身）:", _fmt_vec(g["db2"]))
    print()
    print("   ⑧-3 梯度继续往上传给池化输出 df（误差经过权重分摊回去）")
    print("       公式: df[b] = Σ_a W2[a][b] × dz2[a]")
    print(f"       算例·df[0] = {cs(W2[0][0])}×{cs(g['dz2'][0])} + {cs(W2[1][0])}×{cs(g['dz2'][1])}"
          f" = {cs(g['df'][0])}")
    print("       结果 df（98 维）:")
    print("       " + _fmt_vec_wrapped(g["df"]))
    print("       dp1（把 df 按摊平的逆序还原回 2×7×7 形状）:")
    for k in range(2):
        print(f"         [{k}]")
        print(_fmt_mat(g["dp1"][k]))
    print()
    print("   ⑧-4 池化反向：梯度只还给每个窗口里'最大的那个'像素，其余 3 个分到 0")
    print("       规则: da1[k][最大值坐标] += dp1[k][i][j]（mask 记录的就是最大值坐标）")
    bi, bj = masks[0][0][0]
    print(f"       算例·dp1[0][0][0]={cs(g['dp1'][0][0][0])} 只给坐标 {masks[0][0][0]}"
          f" → da1[0][{bi}][{bj}] += {cs(g['dp1'][0][0][0])}")
    print("       结果 da1（14×14，绝大多数是 0）:")
    for k in range(2):
        print(f"         [{k}]")
        print(_fmt_mat(g["da1"][k]))
    print()
    print("   ⑧-5 ReLU 反向：z>0 处梯度原样通过，z≤0 处梯度归 0")
    print(f"       算例·da1[0][0][0]={cs(g['da1'][0][0][0])}，z1[0][0][0]={cs(z1[0][0][0])}>0"
          f" → dz1[0][0][0] = {cs(g['dz1'][0][0][0])}")
    print("       结果 dz1（14×14）:")
    for k in range(2):
        print(f"         [{k}]")
        print(_fmt_mat(g["dz1"][k]))
    print()
    print("   ⑧-6 卷积核梯度 dW1（误差 × 输入像素，滑过的所有位置累加）")
    print("       公式: dW1[k][u][v] = Σ_{i,j} dz1[k][i][j] × x[i+u][j+v]（196 个位置累加）")
    head_dw = " + ".join(f"{cs(g['dz1'][0][i][j])}×{cu(img[i][j])}" for i in range(3) for j in range(3))
    print(f"       算例·dW1[0][0][0] 展开前 9 项: {head_dw} + …")
    print(f"       = {cs(g['dW1'][0][0][0])}")
    print("       结果 dW1（2×3×3）:")
    print(_fmt_cube(g["dW1"]))
    print("       db1（卷积偏置梯度 = 所有位置误差之和）:", _fmt_vec(g["db1"]))

    # ── ⑨ 更新 ──────────────────────────────────────────────
    print("\n⑨ 更新参数（SGD 一步）· 每个参数往梯度的反方向挪 lr 一小步")
    print(f"   公式: 新 = 旧 − lr × 梯度，lr = {cu(lr)}")
    print(f"   算例·W1[0][0][0]: {cs(W1[0][0][0])} − {cu(lr)}×({cs(g['dW1'][0][0][0])}) = "
          f"{cs(W1[0][0][0] - lr * g['dW1'][0][0][0])}")
    print(f"   算例·b1[0]     : {cs(b1[0])} − {cu(lr)}×({cs(g['db1'][0])}) = "
          f"{cs(b1[0] - lr * g['db1'][0])}")
    print(f"   算例·W2[0][0]  : {cs(W2[0][0])} − {cu(lr)}×({cs(g['dW2'][0][0])}) = "
          f"{cs(W2[0][0] - lr * g['dW2'][0][0])}")
    print(f"   算例·b2[0]     : {cs(b2[0])} − {cu(lr)}×({cs(g['db2'][0])}) = "
          f"{cs(b2[0] - lr * g['db2'][0])}")


# ═══════════════════════════════════════════════════════════
# PART 3. SGD 训练：w ← w - lr · dL/dw
# ═══════════════════════════════════════════════════════════
# 有了梯度，训练就只剩一件事：让每个参数往"让损失变小的方向"挪。
# 梯度指向损失增加最快的方向，所以往它的反方向迈一小步：
#   w_new = w_old - lr × gradient
# lr（学习率）控制步子大小——太小学得慢，太大一步跨过头（见下方注释）。


def update(W1, b1, W2, b2, dW1, db1, dW2, db2, lr):
    """梯度下降一步（第 3 步）——每个参数减去 学习率×梯度。
    四组参数各减各的梯度：w -= lr·dL/dw，b -= lr·dL/db。
    """
    for k in range(2):                               # 卷积核 2 个
        for u in range(3):
            for v in range(3):
                W1[k][u][v] -= lr * dW1[k][u][v]
        b1[k] -= lr * db1[k]
    for a in range(2):                               # 全连接输出 2 个
        for b in range(len(W2[0])):
            W2[a][b] -= lr * dW2[a][b]
        b2[a] -= lr * db2[a]


def train(data, epochs=150, lr=0.03, trace=TRACE_ALL):
    """训练主循环（第 3 步的完整循环）——反复"前向→反向→更新"。
    每一个 epoch 做一遍：跑完所有训练样本，每跑一张就立即更新一次参数。
    打印每轮的平均损失和准确率：损失下降、准确率上升 = 在学东西。
    返回训练好的参数 (W1, b1, W2, b2)。

    trace=True 时额外打印每一步的数值（见 PART 3.5）：
      初始参数 → 第 1 轮第 1 张样本的完整前向+反向+更新 → 每 50 轮参数快照 → 最终参数。

    学习率为什么取 0.03 而不是更大的值？
    梯度数量级约 0.1~1，lr 太大会让卷积核一步跨进"所有输出≤0"的
    ReLU 死亡区，梯度变成 0，模型再也学不动（这就是著名的 dying ReLU）。
    调小 lr 是最直接的解法。
    """
    # 随机初始化（小值高斯，模仿真实框架做法）——在学之前参数一无所知
    W1 = [[[random.gauss(0, 0.1) for _ in range(3)] for _ in range(3)] for _ in range(2)]
    b1 = [0.0, 0.0]
    W2 = [[random.gauss(0, 0.05) for _ in range(98)] for _ in range(2)]
    b2 = [0.0, 0.0]

    n = len(data)
    if trace:
        print("\n── 初始参数（训练前，纯随机噪声，还没学过任何东西）──")
        print_params(W1, b1, W2, b2)

    for epoch in range(1, epochs + 1):
        total_loss = 0.0
        correct = 0
        for idx, (img, y) in enumerate(data):
            probs, cache = forward(img, W1, b1, W2, b2)         # ① 前向：算出概率
            this_loss = -math.log(max(probs[y], 1e-12))         # 交叉熵 L = -ln p_y（加个极小值防 log0）
            total_loss += this_loss
            pred = 0 if probs[0] >= probs[1] else 1             # 谁概率大猜谁
            correct += (pred == y)                              # 猜对就记一分
            g = backward(img, y, cache, W2)                     # ② 反向：算梯度（dict）
            if trace and epoch == 1 and idx == 0:
                # 全程追踪：每步"公式 → 代入 → 结果"，含 softmax 归一化与反向每一层的计算过程
                show_sample_trace(img, y, W1, b1, W2, b2, cache, g, lr, this_loss)
            update(W1, b1, W2, b2, g["dW1"], g["db1"], g["dW2"], g["db2"], lr)   # ③ 更新：挪一小步
        if epoch % 10 == 0 or epoch == 1:
            acc = 100.0 * correct / n
            print(f"  epoch {epoch:>3} | 平均损失 {total_loss/n:.4f} | 训练准确率 {acc:.1f}%")
        if trace and epoch % 50 == 0 and epoch < epochs:
            print(f"\n── 参数快照 @ epoch {epoch}（训练中，看看参数被 SGD 改成了什么样）──")
            print_params(W1, b1, W2, b2)
    if trace:
        print("\n── 最终参数（训练完成）──")
        print_params(W1, b1, W2, b2)
    return W1, b1, W2, b2


# ═══════════════════════════════════════════════════════════
# PART 4. 评估
# ═══════════════════════════════════════════════════════════
# 训练时模型"见过"训练集，所以要用从没见过的测试集来打分，
# 才知道它是不是真的学会了"猫长什么样"，而不是死记硬背。


def evaluate(data, W1, b1, W2, b2):
    """在测试集上打分（第 4 步）——统计四个数并打印准确率。
    TP/TN/FP/FN（真正例/真负例/假正例/假负例）是最基本的分类指标：
      TP=猫判成猫，TN=非猫判成非猫，FP=非猫误判成猫，FN=猫漏判成非猫。
    """
    tp = fp = tn = fn = 0
    for img, y in data:
        probs, _ = forward(img, W1, b1, W2, b2)      # 只用前向，不更新参数
        pred = 0 if probs[0] >= probs[1] else 1
        if pred == 1 and y == 1: tp += 1
        elif pred == 1 and y == 0: fp += 1
        elif pred == 0 and y == 0: tn += 1
        else: fn += 1
    acc = 100.0 * (tp + tn) / max(1, len(data))
    print(f"  测试集: 猫{len([1 for _,y in data if y==1])}张 非猫{len([1 for _,y in data if y==0])}张")
    print(f"  准确率 {acc:.1f}%  |  猫→猫(TP)={tp}  非猫→非猫(TN)={tn}  "
          f"误报(FP)={fp}  漏检(FN)={fn}")
    return acc


def show_kernel(W1):
    """打印学到的卷积核（第 5 步）——把训练结果"解剖"给你看。
    W1 是 2 个 3×3 数字矩阵，训练前是随机噪声，训练后变成了"特征检测器"：
    数字有正有负 → 它在找"亮度突变"（边缘/轮廓）。
    这就是 CNN 不靠人设计、自己学会的特征——和 YOLO 内部的卷积核是同一类东西。
    """
    print("\n学到的卷积核（每个 3×3 数字矩阵 = 一个特征检测器）:")
    for k in range(2):
        print(f"  核{k}:")
        for row in W1[k]:
            print("    " + "  ".join(f"{v:+.3f}" for v in row))
    print("  解读: 正值+负值并存的模式 = 它在找'亮度变化'（边缘/轮廓）。")
    print("  这就是 CNN 不靠人设计、自己学会的特征——和 YOLO 内部的卷积核是同一类东西。")


# ═══════════════════════════════════════════════════════════
# PART 5. 彩蛋：在场景里"找到猫"（目标检测）
# ═══════════════════════════════════════════════════════════
# 分类只能答"是猫/不是猫"；这里更进一步：在一张大图里"猫在哪"。
# 做法就是最朴素的滑动窗口：把整张图切成很多 16×16 的窗口，
# 每个窗口都喂给同一个分类模型，谁的"猫概率"最高，猫就大概在哪。
# 现代检测算法（YOLO / 滑窗 R-CNN）思路与此同源，只是把滑动改成了一次算完。


def find_cat_in_scene(W1, b1, W2, b2):
    """第 6 步·彩蛋：生成一张 40×40 大图，用训练好的模型在里面找猫。
    流程：
      1. 造场景：浅噪声背景 + 4 个随机块，再把一只猫放进已知位置 (10,10)；
      2. 滑动窗口：stride=2，每个 16×16 窗口过一遍模型，记下 P(猫)；
      3. 取最高概率窗口 = 模型认为猫在的地方，和真实位置比距离；
      4. 在图上画白色方框标出预测位置，存成 PNG。
    返回 (probs_map, best, 真实中心坐标)——probs_map 就是一张"热力图"数据。
    """
    SC = 40                                             # 场景边长 40×40
    scene = [[0.0] * SC for _ in range(SC)]
    # 背景：浅噪声 + 几个随机块（制造"干扰物"，让它没那么容易）
    for y in range(SC):
        for x in range(SC):
            scene[y][x] = 0.15 + 0.1 * random.random()
    for _ in range(4):
        cx, cy = random.random() * SC, random.random() * SC
        r = 2 + random.random() * 3
        for y in range(SC):
            for x in range(SC):
                if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                    scene[y][x] = 0.6 + 0.2 * random.random()
    # 把一只猫"贴"进场景的左上角 (true_x, true_y)
    cat = make_cat()
    true_x, true_y = 10, 10
    for yy in range(SIZE):
        for xx in range(SIZE):
            scene[true_y + yy][true_x + xx] = cat[yy][xx]

    # 滑动窗口扫描：窗口 = 16×16，每次移动 2 格（stride=2）
    stride = 2
    probs_map = [[0.0] * ((SC - SIZE) // stride + 1) for _ in range((SC - SIZE) // stride + 1)]
    best = (-1.0, None, None)
    for wy in range(0, SC - SIZE + 1, stride):
        for wx in range(0, SC - SIZE + 1, stride):
            win = [row[wx:wx + SIZE] for row in scene[wy:wy + SIZE]]  # 切出窗口
            probs, _ = forward(win, W1, b1, W2, b2)                   # 过一遍模型
            p = probs[1]                                              # 取 P(猫)
            probs_map[wy // stride][wx // stride] = p
            if p > best[0]:
                best = (p, wx, wy)                     # 记录当前最高概率窗口

    p, bx, by = best
    tx = true_x + SIZE // 2                            # 猫真实中心的像素坐标
    ty = true_y + SIZE // 2
    dist = math.hypot(bx + SIZE // 2 - tx, by + SIZE // 2 - ty)   # 预测中心与真实中心距离
    print(f"\n彩蛋·在场景里找猫：")
    print(f"  猫真实位置: ({tx},{ty})  模型预测窗口: ({bx},{by})  中心距 = {dist:.1f} 像素")
    print(f"  最高 P(猫) = {p:.2f}" + ("  → 找到了!🎯" if dist <= 8 else "  → 位置略偏（模型更关心'是不是猫'而非'精确在哪'）"))

    # 在场景的副本上画一个白色方框（四条边框线 = 纯白），存成 PNG 给你看
    scene_box = [row[:] for row in scene]           # 复制一份，别改原图
    for yy in range(by, by + SIZE):
        for xx in range(bx, bx + SIZE):
            if yy in (by, by + SIZE - 1) or xx in (bx, bx + SIZE - 1):
                scene_box[yy][xx] = 1.0              # 框线 = 纯白
    os.makedirs(OUT, exist_ok=True)
    path = write_png(os.path.join(OUT, "08_scene_detected.png"), scene_box)
    print(f"  已保存定位结果图: {path}")
    return probs_map, best, (tx, ty)


# ═══════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════
# 把上面的七步按顺序串起来跑一遍。每一步调用了哪些函数，请看下方注释。
def main():
    # TRACE_ALL=True 时，把整个运行过程（每个步骤数值 + 计算过程）同时打屏并写进日志文件
    if TRACE_ALL:
        global _LOG_FILE
        _LOG_FILE = open(LOG_PATH, "w", encoding="utf-8")
        sys.stdout = _Tee(sys.__stdout__, _LOG_FILE)
        print(f"▶ 完整日志（含每一步计算过程）: {LOG_PATH}")

    print("=" * 64)
    print("从 0 开始识别猫：零第三方库的迷你 CNN")
    print("=" * 64)

    # ── 第 0 步：造数据 ──────────────────────────────────────
    # make_dataset(80, 80) 生成 160 张图（80 猫 + 80 非猫）。
    print("\n[0/7] 造数据（程序自己画 80 只猫 + 80 张非猫图）...")
    data = make_dataset(80, 80)
    random.shuffle(data)
    train_data = data[:128]          # 前 128 张做训练（模型要"背"这些图）
    test_data = data[128:]           # 后 32 张做测试（模型从没见过，用来真实打分）
    print(f"  训练集 {len(train_data)} 张，测试集 {len(test_data)} 张，每张 {SIZE}×{SIZE} 灰度")
    print("\n  一只'猫'长这样（0~1 灰度渲染成字符）:")
    print_img(make_cat())            # 用字符画出来，肉眼看看数据长啥样
    print("  一张'非猫'长这样（随机形状）:")
    print_img(make_noncat())
    # 落盘两张"样板图"，方便直接打开图片看
    os.makedirs(OUT, exist_ok=True)
    print("\n  已保存样本图: "
          f"{write_png(os.path.join(OUT, '08_cat_sample.png'), make_cat())}")
    print("               "
          f"{write_png(os.path.join(OUT, '08_noncat_sample.png'), make_noncat())}")

    # 把造出来的真实数据集也落盘成 PNG——上面那 2 张是"样板"，
    # 这里的才是模型真正吃到的 160 张（抽样各 12 张，肉眼可查多样性）
    dump_dir = os.path.join(OUT, "08_dataset")
    os.makedirs(dump_dir, exist_ok=True)
    saved_c = saved_n = 0
    for img, label in data:
        if label == 1 and saved_c < 12:
            write_png(os.path.join(dump_dir, f"cat_{saved_c:02d}.png"), img)
            saved_c += 1
        elif label == 0 and saved_n < 12:
            write_png(os.path.join(dump_dir, f"noncat_{saved_n:02d}.png"), img)
            saved_n += 1
        if saved_c == 12 and saved_n == 12:
            break
    print(f"  已把造出来的数据集落盘成 24 张真实 PNG: {dump_dir}")

    # ── 第 1~3 步：训练 ─────────────────────────────────────
    # train() 内部循环跑"前向(1)→反向(2)→更新(3)" 150 轮。
    # TRACE_ALL=True 时，训练中会把每一步的参数/数值都打印出来（见 PART 3.5）。
    print("\n[1~7/7] 训练：卷积+ReLU+池化+全连接+softmax → 反向传播 → SGD")
    t0 = time.time()
    W1, b1, W2, b2 = train(train_data, epochs=150, lr=0.03, trace=TRACE_ALL)
    print(f"  训练用时 {time.time()-t0:.1f} 秒")

    # ── 第 4 步：评估；第 5 步：看核；第 6 步：彩蛋找猫 ─────
    print("\n评估：")
    evaluate(test_data, W1, b1, W2, b2)     # 在没见过的测试集上打分
    show_kernel(W1)                          # 打印模型自己学到的特征检测器
    find_cat_in_scene(W1, b1, W2, b2)        # 在 40×40 场景里滑动窗口找猫

    # 关闭日志：恢复标准输出，日志文件保留在磁盘上
    if TRACE_ALL:
        sys.stdout.flush()
        _LOG_FILE.close()
        _LOG_FILE = None
        sys.stdout = sys.__stdout__
        print(f"▶ 日志已写入: {LOG_PATH}")


if __name__ == "__main__":
    main()
