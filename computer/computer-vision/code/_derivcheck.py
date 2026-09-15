# -*- coding: utf-8 -*-
"""验证公式 ΔL ≈ -lr·Σg²（一阶泰勒/全微分）在真实网络上成立。
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


A, W, b = copy.deepcopy([W1, b1]), copy.deepcopy(W2), copy.deepcopy(b2)
L0 = L_of(A[0], A[1], W, b)

p, cache = m.forward(img, A[0], A[1], W, b)
g = m.backward(img, y, cache, W)
dW1, db1, dW2, db2 = g["dW1"], g["db1"], g["dW2"], g["db2"]

# Σg² 对全部 218 个参数求和
S = 0.0
nparams = 0
for k in range(2):
    for u in range(3):
        for v in range(3):
            S += dW1[k][u][v] ** 2; nparams += 1
for k in range(2):
    S += db1[k] ** 2; nparams += 1
for a in range(2):
    for j in range(98):
        S += dW2[a][j] ** 2; nparams += 1
for a in range(2):
    S += db2[a] ** 2; nparams += 1

print(f"全部 {nparams} 个参数的梯度平方和 Σg² = {S:.6f}")
print(f"初始损失 L0 = {L0:.6f}\n")

for lr in (0.3, 0.03, 0.003):
    A2, W2b, b2b = copy.deepcopy(A), copy.deepcopy(W), copy.deepcopy(b)
    for k in range(2):
        for u in range(3):
            for v in range(3):
                A2[0][k][u][v] -= lr * dW1[k][u][v]
        A2[1][k] -= lr * db1[k]
    for a in range(2):
        for j in range(98):
            W2b[a][j] -= lr * dW2[a][j]
    b2b[0] -= lr * db2[0]; b2b[1] -= lr * db2[1]
    exact = L0 - L_of(A2[0], A2[1], W2b, b2b)      # 实际下降（真实测量）
    pred = lr * S                                    # 一阶公式预测：-ΔL = lr·Σg²
    print(f"lr={lr:<6} 公式预测下降 lr·Σg² = {pred:+.6f}  实际下降(测量) = {exact:+.6f}  "
          f"差(二阶余项) = {abs(pred-exact):.2e}")
