# 特征值、特征向量与对角化：找"变换里不变的方向"

> 前三篇：矩阵=变换、秩=信息维数、行列式=体积缩放。这一篇问一个新问题：**这个变换里，有没有"方向不变"的向量？** 答案就是特征向量，它把一大堆难懂的变换问题（幂、微分方程、卷积、振动）一次性"解耦"。

## 一、特征向量 = 变换后方向不变的向量

普通向量送进 $A$，方向会变。但有些特殊方向 $x$，送进去后**方向不变，只被拉伸/压缩 $\lambda$ 倍**：

$$
\boxed{\ Ax = \lambda x\ }
$$

- $\lambda$ = **特征值**（沿该方向的缩放倍数）
- $x$ = **特征向量**（那个不变的方向）

注意 $x$ 是"方向"不是"某个点"：若 $x$ 是特征向量，任意倍数 $cx$ 也是（同一条线）。

## 二、先看例子，建立直觉

| 变换 | 特征向量 | 特征值 | 直觉 |
|------|----------|--------|------|
| 缩放 $\begin{bmatrix}s_x&0\\0&s_y\end{bmatrix}$ | $e_1,\ e_2$ | $s_x,\ s_y$ | 两条轴，各自拉伸 |
| 旋转 $\theta$（非 0、$\pi$） | **无实特征向量** | — | 所有方向都被转走，没方向不动 |
| 剪切 $\begin{bmatrix}1&k\\0&1\end{bmatrix}$ | 只有 $[1,0]^\top$ | $1$ | 只剩 x 轴一个不变方向 |
| 镜像 $\begin{bmatrix}-1&0\\0&1\end{bmatrix}$ | $e_1,\ e_2$ | $-1,\ 1$ | x 轴翻转（$\lambda=-1$）、y 轴不动 |

## 三、怎么求：特征多项式

$$
Ax=\lambda x\ \Rightarrow\ (A-\lambda I)x=0
$$

要有非零解 $x$，方程组必须退化——**这正是第三篇讲的 $\det=0$**：

$$
\boxed{\ \det(A-\lambda I)=0\ }
$$

手算 $A=\begin{bmatrix}2&1\\1&2\end{bmatrix}$：

$$
\det(A-\lambda I)=\begin{vmatrix}2-\lambda&1\\1&2-\lambda\end{vmatrix}=(2-\lambda)^2-1=\lambda^2-4\lambda+3=(\lambda-3)(\lambda-1)=0
$$

得 $\lambda=3,\ 1$。回代求向量：

- $\lambda=3$：$(A-3I)x=0 \Rightarrow x=[1,1]^\top$
- $\lambda=1$：$x=[1,-1]^\top$

```python
import numpy as np
A = np.array([[2,1],[1,2]])
np.linalg.eig(A)    # 特征值 [3, 1]；特征向量 [1,1]ᵀ/√2、[1,-1]ᵀ/√2（已归一化）
```

## 四、对角化：换到特征基，变换变"纯缩放"

**这句话怎么来的？** 把 $n$ 个特征方程 $Av_i=\lambda_i v_i$ 并排写成一个矩阵方程。记 $V=[v_1,\dots,v_n]$（列是特征向量）、$\Lambda=\operatorname{diag}(\lambda_1,\dots,\lambda_n)$：

$$
AV = A[v_1,\dots,v_n] = [Av_1,\dots,Av_n] = [\lambda_1v_1,\dots,\lambda_nv_n] = V\Lambda
$$

（最后一步：$V\Lambda$ 的第 $i$ 列 $=$ 第 $i$ 列 $v_i$ 乘 $\lambda_i$。）于是 $AV=V\Lambda$。若 $V$ 可逆（$n$ 个特征向量线性无关，即 $A$ 可对角化），两边右乘 $V^{-1}$：

$$
\boxed{\ A = V\Lambda V^{-1}\ },\qquad\text{等价地}\quad V^{-1}AV=\Lambda
$$

**换基视角（为什么叫"解耦"）**：$V^{-1}AV=\Lambda$ 读作"先把 $x$ 换成特征基坐标 $y=V^{-1}x$，在这个基里 $A$ 变成对角 $\Lambda$（每个坐标独立缩放），再换回来"。原来互相耦合的各维，在特征基下被拆成互不干扰的 $n$ 份。

两个超高价值的好处：

1. **幂根**：$A^k$ 好算了，因为中间的 $V^{-1}V$ 抵消：

$$
A^k = \underbrace{(V\Lambda V^{-1})(V\Lambda V^{-1})\cdots}_{k\ \text{次}} = V\Lambda^k V^{-1},\qquad \Lambda^k=\operatorname{diag}(\lambda_1^k,\dots,\lambda_n^k)
$$

→ 递推方程、马尔可夫链稳态、PageRank 收敛。

2. **解微分/差分方程**：把耦合的一阶系统沿特征方向拆成 $n$ 个独立的 $e^{\lambda_i t}$。

**拿第三篇那个 $A=\begin{bmatrix}2&1\\1&2\end{bmatrix}$ 验一遍。** $\lambda=3,1$，$v_1=[1,1]^\top$、$v_2=[1,-1]^\top$：

$$
V=\begin{bmatrix}1&1\\1&-1\end{bmatrix},\quad \Lambda=\begin{bmatrix}3&0\\0&1\end{bmatrix},\quad V^{-1}=\begin{bmatrix}\tfrac12&\tfrac12\\\tfrac12&-\tfrac12\end{bmatrix}
$$

拼回：

$$
V\Lambda V^{-1}
=\begin{bmatrix}1&1\\1&-1\end{bmatrix}\begin{bmatrix}3&0\\0&1\end{bmatrix}\begin{bmatrix}\tfrac12&\tfrac12\\\tfrac12&-\tfrac12\end{bmatrix}
=\begin{bmatrix}3&1\\3&-1\end{bmatrix}\begin{bmatrix}\tfrac12&\tfrac12\\\tfrac12&-\tfrac12\end{bmatrix}
=\begin{bmatrix}2&1\\1&2\end{bmatrix}=A\ \checkmark
$$

看幂的威力：$A^2=V\operatorname{diag}(9,1)V^{-1}=\begin{bmatrix}5&4\\4&5\end{bmatrix}$，和直接算 $A^2$ 一模一样——但只需把 $3$ 平方成 $9$。

## 五、应用 1（最漂亮）：卷积/循环矩阵被 DFT 对角化

这是线性代数**照亮你通信笔记**的高光时刻。

循环卷积（你 `convolution-theorem.md` 里的"循环卷积"）写成一个**循环矩阵** $C$——每一行是上一行右移一位。设滤波器 $h=[c_0,c_1]$（周期 2）：

$$
C=\begin{bmatrix}c_0&c_1\\c_1&c_0\end{bmatrix}
$$

它的特征向量正是 **DFT 矩阵的行（正弦波）**，特征值正是**频率响应 $H[k]$**：

$$
C\begin{bmatrix}1\\1\end{bmatrix}=(c_0+c_1)\begin{bmatrix}1\\1\end{bmatrix}=H[0]\begin{bmatrix}1\\1\end{bmatrix},\qquad
C\begin{bmatrix}1\\-1\end{bmatrix}=(c_0-c_1)\begin{bmatrix}1\\-1\end{bmatrix}=H[1]\begin{bmatrix}1\\-1\end{bmatrix}
$$

于是

$$
\mathbf W C \mathbf W^{-1} = \operatorname{diag}\big(H[k]\big)
$$

> **一句话：卷积算子的特征向量是正弦波，特征值是频率响应。** 换到"频率基"里（就是做一次 DFT），卷积这个原本是"矩阵乘法"的算子，变成了对角阵的操作 = **逐点相乘**。

这正是你卷积定理笔记里"**时域卷积 = 频域相乘**"的线性代数本质：同一个算子（卷积），在时间基里是矩阵乘法，换到它的特征基（频率）里就变成对角、变成逐点乘。FFT 就是"最快换到特征基"的办法。

## 六、应用 2：模态分析（直连纳米精度 $K\phi=\omega^2M\phi$）

质量-弹簧振动系统 $M\ddot x+Kx=0$，代入简谐解 $x=\phi e^{j\omega t}$ 得到**广义特征值问题**：

$$
K\phi = \omega^2 M\phi
$$

- $\phi$ = **振型**（特征向量：各质点的振动幅度比例）
- $\omega^2$ = 固有频率的平方（广义特征值）

用振型当基 → 各模态**解耦** → 每个模态独立震荡。**这就是"对角化"在物理里的名字**——你在 `physics/mechanical/nanometer-precision-math.md` 里已经写过这个式子，现在是它背后的线性代数含义。

## 七、应用 3（前瞻）：对称矩阵 → 正交对角化 → PCA

若 $A=A^\top$（对称），则特征值**全为实数**、特征向量可互相正交归一化，于是

$$
A = Q\Lambda Q^\top \quad(\text{$Q$ 正交})
$$

协方差矩阵（对称、半正定）正是这类：**特征值 = 各方向的方差，特征向量 = 主方向**。最大的特征值方向就是"数据铺得最开"的方向——这是 **PCA（主成分分析）降维**的核心，留到下一步 `svd.md` 一起说（SVD 是 PCA 的通用实现）。

> 你纳米精度笔记里那句"对称时求导公式最简、特征值全实数、可正交对角化"——就是这里的结论。

## 八、小结与速查

| 概念 | 一句话 | 应用钩子 |
|------|--------|----------|
| 特征向量 | 变换后方向不变的向量 | 振型、主方向 |
| 特征值 | 沿不变方向的缩放倍数 | 固有频率、方差 |
| 对角化 $A=V\Lambda V^{-1}$ | 换到特征基变纯缩放 | 解耦、$A^k$、解微分方程 |
| $\det(A-\lambda I)=0$ | 求特征值的方程 | — |
| 对称矩阵 | 特征值全实、可正交对角化 | 协方差、PCA |

---

**下一步**：`svd.md` —— SVD = 任意矩阵的"旋转-缩放-旋转"分解，PCA / Kabsch / 图像压缩一把抓。