# -*- coding: utf-8 -*-
"""验证"参数一起按梯度更新，损失下降 ≈ 各自单独更新之和"。
并展示：学习率越小，可加性误差越小（二阶项越小）。
临时脚本，用完可删。"""
import copy
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


def L_of(W1c, b1c, W2c, b2c):
    p, _ = m.forward(img, W1c, b1c, W2c, b2c)
    return -math.log(max(p[y], 1e-12))


A = copy.deepcopy([W1, b1])
W = copy.deepcopy(W2)
b = copy.deepcopy(b2)
L0 = L_of(A[0], A[1], W, b)

p, cache = m.forward(img, A[0], A[1], W, b)
g = m.backward(img, y, cache, W)
dW1, db1, dW2, db2 = g["dW1"], g["db1"], g["dW2"], g["db2"]


def upd(Ac, Wc, bc, lr, which):
    A2, W2b, b2b = copy.deepcopy(Ac), copy.deepcopy(Wc), copy.deepcopy(bc)
    if which in ("A", "all"):
        for k in range(2):
            for u in range(3):
                for v in range(3):
                    A2[0][k][u][v] -= lr * dW1[k][u][v]
            A2[1][k] -= lr * db1[k]
    if which in ("W", "all"):
        for a in range(2):
            for j in range(98):
                W2b[a][j] -= lr * dW2[a][j]
    if which in ("b", "all"):
        b2b[0] -= lr * db2[0]
        b2b[1] -= lr * db2[1]
    return A2, W2b, b2b


print(f"初始损失 L0 = {L0:.6f}\n")
for lr in (0.3, 0.03, 0.003):
    def L_upd(which):
        A2, W2b, b2b = upd(A, W, b, lr, which)
        return L_of(A2[0], A2[1], W2b, b2b)

    d_b = L0 - L_upd("b")
    d_W = L0 - L_upd("W")
    d_A = L0 - L_upd("A")
    d_all = L0 - L_upd("all")
    err = abs((d_b + d_W + d_A) - d_all)
    rel = err / max(abs(d_all), 1e-12) * 100
    print(f"lr = {lr:<6}  Δb={d_b:+.6f}  ΔW={d_W:+.6f}  ΔA={d_A:+.6f}  "
          f"一起Δ总={d_all:+.6f}  |Δ总-(Δb+ΔW+ΔA)|={err:.2e}  相对误差={rel:.2f}%")
