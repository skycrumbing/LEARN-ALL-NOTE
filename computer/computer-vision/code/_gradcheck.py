# -*- coding: utf-8 -*-
"""数值梯度校验：分析梯度 vs 有限差分。临时脚本，用完可删。"""
import importlib.util
import math
import os
import random
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

spec = importlib.util.spec_from_file_location("cat08", "08_cat_recognizer_from_scratch.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

# 精确复现 main() 的随机序列，得到与 08_trace.log 完全相同的参数
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


def loss():
    probs, _ = m.forward(img, W1, b1, W2, b2)
    return -math.log(max(probs[y], 1e-12))


probs, cache = m.forward(img, W1, b1, W2, b2)
g = m.backward(img, y, cache, W2)


def loc(nested, idxs):
    """返回 (get, set)，对嵌套列表的某个元素取值/赋值。"""
    def get():
        c = nested
        for i in idxs[:-1]:
            c = c[i]
        return c[idxs[-1]]

    def set(v):
        c = nested
        for i in idxs[:-1]:
            c = c[i]
        c[idxs[-1]] = v
    return get, set


def num_grad(get, set):
    h = 1e-5
    orig = get()
    set(orig + h)
    Lp = loss()
    set(orig - h)
    Lm = loss()
    set(orig)
    return (Lp - Lm) / (2 * h)


def check(name, analytic, get, set):
    ng = num_grad(get, set)
    ok = abs(analytic - ng) < 1e-4
    print(f"  {name:<16} 分析={analytic:+.6f}  数值={ng:+.6f}  误差={abs(analytic-ng):.2e}  {'✓' if ok else '✗ 不一致！'}")


print(f"样本损失 L = {loss():.6f}，h = 1e-5，分析梯度应≈数值梯度：")
gW1, sW1 = loc(W1, (0, 0, 0))
check("dW1[0][0][0]", g["dW1"][0][0][0], gW1, sW1)
gW1b, sW1b = loc(W1, (1, 2, 1))
check("dW1[1][2][1]", g["dW1"][1][2][1], gW1b, sW1b)
gb1, sb1 = loc(b1, (0,))
check("db1[0]", g["db1"][0], gb1, sb1)
gW2a, sW2a = loc(W2, (0, 0))
check("dW2[0][0]", g["dW2"][0][0], gW2a, sW2a)
gW2b, sW2b = loc(W2, (1, 50))
check("dW2[1][50]", g["dW2"][1][50], gW2b, sW2b)
gb2, sb2 = loc(b2, (1,))
check("db2[1]", g["db2"][1], gb2, sb2)
