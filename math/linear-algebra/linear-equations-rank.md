# 线性方程组、秩与解的结构（含最小二乘）

> 上一篇讲了"矩阵 = 线性变换"。这一篇回答一个更实际的问题：**给定一个矩阵 $A$ 和向量 $b$，方程 $Ax=b$ 一定解得出来吗？解是唯一的吗？** 答案全押在一个数上——**秩（rank）**。

## 一、线性方程组 = 矩阵方程 $Ax=b$

一堆联立方程，本质上就是"列向量的线性组合等于 $b$"：

$$
Ax = x_1 a_1 + x_2 a_2 + \dots + x_n a_n = b
$$

其中 $a_1,\dots,a_n$ 是 $A$ 的 **$n$ 列**。所以：

> **"方程 $Ax=b$ 有解" 等价于 "$b$ 能写成 $A$ 的列的线性组合"。**

这一句是整个解结构的钥匙。

## 二、列空间与秩：$A$ 到底能"够到"哪些 $b$

把所有可能的 $Ax$ 收集起来，就是**列空间**：

$$
\operatorname{col}(A)=\{Ax : x\in\mathbb R^n\}
$$

它是 $A$ 的列"张成"的那个空间。**秩 = 列空间里独立列的个数 = 列空间的维数**：

$$
\operatorname{rank}(A)=\dim\operatorname{col}(A)
$$

直觉：$A$ 是一个线性变换，它把 $n$ 维输入"压"进一个 $\operatorname{rank}$ 维的子空间。**秩就是 $A$ 传递过来多少维"有效信息"。**

### 例子：线性相关的列会让秩降下去

$$
A=\begin{bmatrix}1&2\\3&6\end{bmatrix}
$$

第 2 列 $=$ 第 1 列 ×2，两列共线，所以 $\operatorname{rank}=1$。看它怎么作用：

$$
A\begin{bmatrix}x_1\\x_2\end{bmatrix}=\begin{bmatrix}x_1+2x_2\\3x_1+6x_2\end{bmatrix}=(x_1+2x_2)\begin{bmatrix}1\\3\end{bmatrix}
$$

**输出永远落在 $[1,3]^\top$ 这条直线上**——2 维输入被压成了 1 维。这就是 $\operatorname{rank}=1$ 的几何含义：$A$ 把整个平面"拍扁"到一条线。

## 三、零空间：$A$ 会把谁"压没"了

那些被 $A$ 拍成零的输入，叫**零空间**：

$$
\operatorname{null}(A)=\{x : Ax=0\}
$$

上面那个 $A$：$Ax=0 \Rightarrow x_1+2x_2=0 \Rightarrow x=t[-2,1]^\top$，是一条线，$\dim\operatorname{null}=1$。

**维数定理**把这两个空间的维数焊死在一起：

$$
\boxed{\ \operatorname{rank}(A)+\dim\operatorname{null}(A)=n\ }
$$

（$n$ = 输入维数 = 列数。）含义：**$A$ "保留"的维数 + $A$ "抹掉"的维数 = 输入的总维数**。零空间非零 ⟺ 有信息被抹掉 ⟺ $A$ 不可逆。

## 四、解的结构：秩一锤定音

把上面两条合起来，$Ax=b$ 只有四种结局：

| 条件 | 解的情况 | 什么时候 |
|------|----------|----------|
| $b\in\operatorname{col}(A)$ 且 $\operatorname{rank}=n$ | **唯一解** | $A$ 列满秩（零空间={0}） |
| $b\in\operatorname{col}(A)$ 且 $\operatorname{rank}<n$ | **无穷多解** | 零空间非零，可加任意 $x_0\in\operatorname{null}(A)$ |
| $b\notin\operatorname{col}(A)$ | **无解** | 超定（方程比未知数多，还互相矛盾） |

落到矩阵形状上：

| 形状 | 名称 | 典型结局 |
|------|------|----------|
| 方阵可逆 | $\operatorname{rank}=n$ | 唯一解 $x=A^{-1}b$ |
| 行多列少（$m>n$） | 超定 | 通常无解 → 最小二乘 |
| 列多行少（$m<n$） | 欠定 | 无穷多解 → 最小范数解 |

## 五、应用 1：超定无解 → 最小二乘

现实中方程数往往**多于**未知数，且测量带噪声，$b$ 永远不在 $\operatorname{col}(A)$ 里。这时退而求其次，找"离 $b$ 最近的一个 $Ax$"：

$$
\min_x \|Ax-b\|^2
$$

几何上就是**把 $b$ 垂直投影到列空间**（残差 $b-A\hat x$ 与列空间垂直 $\Rightarrow A^\top(b-A\hat x)=0$），得到**正规方程**：

$$
\boxed{\ A^\top A\,\hat x = A^\top b\ }\ \Rightarrow\ \hat x = \underbrace{(A^\top A)^{-1}A^\top}_{A^{+}\ (\text{伪逆})}\,b
$$

**这一套你已经在 `physics/mechanical/nanometer-precision-math.md` 第三节完整手算过了**（3×2 超定系统、正规方程、伪逆 $A^+$、残差垂直于列空间、以及 21 项几何误差标定）。这里不再重复，只点出它在"秩"视角下的意义：

> **最小二乘 = 承认"$b\notin\operatorname{col}(A)$ 所以无解"，然后退到"在列空间里找离 $b$ 最近的点"**——秩的视角让"为什么无解、为什么这么做"一步到位说清楚。

## 六、应用 2：直线拟合（线性回归）

最小二乘最日常的用法就是**拟合一条直线穿过一堆带噪声的点**。模型 $y=kx+c$，未知数是斜率 $k$ 和截距 $c$，每个点给一条方程：

$$
k\,x_i + c = y_i \quad\Rightarrow\quad
\underbrace{\begin{bmatrix}x_1&1\\x_2&1\\x_3&1\end{bmatrix}}_{A}
\underbrace{\begin{bmatrix}k\\c\end{bmatrix}}_{x}
=\underbrace{\begin{bmatrix}y_1\\y_2\\y_3\end{bmatrix}}_{b}
$$

三个点 (1,2)、(2,4)、(3,5)，手算一次：

$$
A^\top A=\begin{bmatrix}14&6\\6&3\end{bmatrix},\qquad A^\top b=\begin{bmatrix}25\\11\end{bmatrix}
$$

解 $\begin{bmatrix}14&6\\6&3\end{bmatrix}\begin{bmatrix}k\\c\end{bmatrix}=\begin{bmatrix}25\\11\end{bmatrix}$：

$$
k=\tfrac32=1.5,\qquad c=\tfrac23\approx0.667
$$

拟合出的直线是 $y=1.5x+0.667$。numpy 一键复核：

```python
import numpy as np
A = np.array([[1,1],[2,1],[3,1]])
b = np.array([2,4,5])
k, c = np.linalg.lstsq(A, b, rcond=None)[0]   # → k=1.5, c=0.6667
```

> 本质一模一样：**超定无解 → 正规方程 → 伪逆解**。机器学习里 90% 的"拟合"（线性回归、多项式拟合、甚至神经网络的最后一层）都是这个 $A^\top A\hat x=A^\top b$ 的老套路换了件衣服。

## 七、小结与速查

| 概念 | 一句话 | 应用钩子 |
|------|--------|----------|
| 列空间 $\operatorname{col}(A)$ | $A$ 能"够到"的所有输出 | 解存在 ⟺ $b$ 在其中 |
| 秩 $\operatorname{rank}$ | 独立列数 = 有效信息维数 | 一锤定音解的结构 |
| 零空间 $\operatorname{null}(A)$ | 被 $A$ 压成零的输入 | 非零 ⟹ 不可逆 / 无穷解 |
| 维数定理 | rank + dim(null) = n | 输入维数的守恒 |
| 最小二乘 | 把 $b$ 垂直投影到列空间 | 直线拟合、误差标定 |

---

**下一步**：`determinant-inverse.md` —— 行列式=体积缩放、逆矩阵=逆变换（补齐"方阵可逆"那一格的故事）。