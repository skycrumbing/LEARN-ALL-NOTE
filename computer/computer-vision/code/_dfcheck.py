# -*- coding: utf-8 -*-
"""直接验证 df（对中间特征 f 的梯度）是否准确：把 f[b] 当旋钮做有限差分。
临时脚本，用完可删。"""
import importlib.util
import math
import os
import random
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

spec = importlib.util.spec_from_file_location("cat08", "08_cat_recognizer_from_scratch.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

random.seed(42)
data = m.make_dataset(80, 80)
random.shuffle(data)
train_data = data[:128]
m.print_img(m.make_cat())
m.print_img(m.make_noncat())
m.write_png(os.path.join(m.OUT, "t1.png"), m.make_cat())
m.write_png(os.path.join(m.OUT, "t2.png"), m.make_noncat())
os.remove(os.path.join(m.OUT, "t1.png"))
os.remove(os.path.join(m.OUT, "t2.png"))
W1 = [[[random.gauss(0, 0.1) for _ in range(3)] for _ in range(3)] for _ in range(2)]
b1 = [0.0, 0.0]
W2 = [[random.gauss(0, 0.05) for _ in range(98)] for _ in range(2)]
b2 = [0.0, 0.0]
img, y = train_data[0]

probs, cache = m.forward(img, W1, b1, W2, b2)
g = m.backward(img, y, cache, W2)
f = cache[4]


def loss_with_f(fb, value):
    """正常前向，但把第 fb 个特征替换成 value，再走全连接→softmax→损失。"""
    f2 = f[:]
    f2[fb] = value
    z2 = [sum(W2[k][b] * f2[b] for b in range(98)) + b2[k] for k in range(2)]
    p = m.softmax(z2)
    return -math.log(max(p[y], 1e-12))


def num_df(fb):
    h = 1e-5
    orig = f[fb]
    Lp = loss_with_f(fb, orig + h)
    Lm = loss_with_f(fb, orig - h)
    return (Lp - Lm) / (2 * h)


print("把第 fb 个特征 f[fb] 当'旋钮'抖动 ±1e-5，重算损失，得到 df 的数值梯度：")
for fb in [0, 1, 40, 48, 97]:
    ana = g["df"][fb]
    num = num_df(fb)
    print(f"  df[{fb:>2}]  分析={ana:+.6f}  数值(直接抖f)={num:+.6f}  误差={abs(ana-num):.2e}")

print()
print("解释：df 的'数值梯度'是直接拿真实损失测的（不是靠 W2 算的），")
print("它和分析梯度对上 = df 公式本身是对的，不存在'被 dW2 带歪'的问题。")
