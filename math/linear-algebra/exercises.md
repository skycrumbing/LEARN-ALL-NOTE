# 线性代数自测题（覆盖「向量～正交/酉」6 篇）

> 规矩：先自己动手做，做完再翻到文末「参考答案」对账。能手算的手算，顺手用 numpy 复核。

## A. 向量与线性变换

1.（概念）矩阵的「列」有什么几何含义？据此说明 $\begin{bmatrix}2&0\\0&3\end{bmatrix}$ 对单位方块做了什么。

2.（概念）矩阵乘法一般 $AB\ne BA$。用「先旋转再剪切 vs 先剪切再旋转」解释为什么顺序不能换。

## B. 方程组、秩与解的结构

3.（手算）$A=\begin{bmatrix}1&2\\3&6\end{bmatrix}$。求 (a) 秩；(b) 列空间；(c) 零空间；(d) $Ax=b$ 在什么 $b$ 下有解？

4.（概念）用恒等式 $\operatorname{rank}(A)+\dim\operatorname{null}(A)=n$ 解释：为什么「有非零向量被 $A$ 拍成 0」等价于「$A$ 丢了一维信息」？

## C. 行列式与逆

5.（手算）$A=\begin{bmatrix}1&2\\3&4\end{bmatrix}$。求 $\det A$、$A^{-1}$，并验证 $AA^{-1}=I$。

6.（概念）$\det(AB)=\det A\cdot\det B$ 的几何含义是什么？$\det A=0$ 又意味着什么？

## D. 特征值与对角化

7.（手算）$A=\begin{bmatrix}2&1\\1&2\end{bmatrix}$。求特征值、特征向量，写出 $A=V\Lambda V^{-1}$，并由此算 $A^3$。

8.（概念）旋转矩阵（非 0、$\pi$）为什么**没有实特征向量**？这和「它把所有方向都转走」怎么对应？

## E. SVD

9.（手算，本章主菜）$A=\begin{bmatrix}0&-3\\1&0\end{bmatrix}$。按「求 $A^\top A$ → 谱定理给 $V,\sigma$ → 造 $u_i$ → 拼回」四步求 $U,\Sigma,V$，并验证 $A=U\Sigma V^\top$。

10.（概念）为什么 SVD 对**任意** $m\times n$ 矩阵都成立，而特征值分解不行？（一句点题：包袱甩给了谁？）

## F. 正交 / 酉

11.（手算）验证旋转矩阵 $R(\theta)=\begin{bmatrix}\cos\theta&-\sin\theta\\\sin\theta&\cos\theta\end{bmatrix}$ 保长度，即证 $R^\top R=I$。

12.（概念）用「$W_N$ 是酉矩阵（$W_NW_N^*=NI$）」推出 Parseval：$\sum_n|x[n]|^2=\dfrac1N\sum_k|X[k]|^2$。

---

# 参考答案

## A

**1.** 矩阵的列是基向量 $e_i$ 作用后的像（$Ae_i=$ 第 $i$ 列）。$\begin{bmatrix}2&0\\0&3\end{bmatrix}$ 把 $e_1\to[2,0]$、$e_2\to[0,3]$，即 x 轴拉 2 倍、y 轴拉 3 倍：单位方块（面积 1）变成 $2\times3$ 矩形（面积 6，正好 $\det=6$）。

**2.** 复合变换对应「从右往左依次作用」，顺序不可交换。先转 90° 再剪切 ≠ 先剪切再转 90°，两个结果不一样，所以 $AB\ne BA$。

## B

**3.** 第二列 $=2\times$ 第一列，故 (a) $\operatorname{rank}=1$。(b) $\operatorname{col}(A)=\operatorname{span}\{[1,3]^\top\}$（一条沿 $[1,3]$ 的直线）。(c) $Ax=0\Rightarrow x_1+2x_2=0$，$\operatorname{null}(A)=\operatorname{span}\{[-2,1]^\top\}$。(d) $Ax=b$ 有解 ⟺ $b$ 是 $[1,3]^\top$ 的倍数（$b\in\operatorname{col}(A)$）。

**4.** 零空间非零 ⟺ $\dim\operatorname{null}>0$ ⟺ $\operatorname{rank}=n-\dim\operatorname{null}<n$ ⟺ 输出维数小于输入维数 ⟺ 丢维。那个被拍成 0 的非零向量所指的方向，就是"被抹掉的一维"。

## C

**5.** $\det A=1\cdot4-2\cdot3=-2$。$A^{-1}=\dfrac1{-2}\begin{bmatrix}4&-2\\-3&1\end{bmatrix}=\begin{bmatrix}-2&1\\\tfrac32&-\tfrac12\end{bmatrix}$。验证 $AA^{-1}=I$ ✓。

```python
import numpy as np
A = np.array([[1,2],[3,4]])
np.linalg.det(A), np.linalg.inv(A)   # → -2.0, [[-2,1],[1.5,-0.5]]
```

**6.** $\det(AB)=\det A\cdot\det B$：复合变换的体积缩放 = 两个缩放因子的乘积。$\det A=0$：空间被压扁（体积 0）、丢维、不可逆。

## D

**7.** 特征多项式 $(\lambda-3)(\lambda-1)=0$，$\lambda=3,1$；对应 $v_1=[1,1]^\top$、$v_2=[1,-1]^\top$。

$$
V=\begin{bmatrix}1&1\\1&-1\end{bmatrix},\quad \Lambda=\begin{bmatrix}3&0\\0&1\end{bmatrix},\quad V^{-1}=\begin{bmatrix}\tfrac12&\tfrac12\\\tfrac12&-\tfrac12\end{bmatrix}
$$

$$
A^3=V\operatorname{diag}(27,1)V^{-1}=\begin{bmatrix}1&1\\1&-1\end{bmatrix}\begin{bmatrix}27&0\\0&1\end{bmatrix}\begin{bmatrix}\tfrac12&\tfrac12\\\tfrac12&-\tfrac12\end{bmatrix}=\begin{bmatrix}14&13\\13&14\end{bmatrix}
$$

**8.** 旋转（$\theta\ne0,\pi$）把每个非零向量都转过一个非零角度，没有任何方向保持原方向，故 $Ax=\lambda x$ 无实解——「没有不变方向」，自然没有实特征向量。

## E

**9.**

$$
A^\top A=\begin{bmatrix}0&1\\-3&0\end{bmatrix}\begin{bmatrix}0&-3\\1&0\end{bmatrix}=\begin{bmatrix}1&0\\0&9\end{bmatrix}
$$

特征值 $\lambda_1=9,\ \lambda_2=1$，所以 $\sigma_1=3,\ \sigma_2=1$。特征向量：$v_1=[0,1]^\top$、$v_2=[1,0]^\top$，故 $V=\begin{bmatrix}0&1\\1&0\end{bmatrix}$。

$$
u_1=\frac{Av_1}{\sigma_1}=\frac{A[0,1]^\top}{3}=\frac{[-3,0]^\top}{3}=[-1,0]^\top,\qquad
u_2=\frac{Av_2}{\sigma_2}=A[1,0]^\top=[0,1]^\top
$$

所以 $U=\begin{bmatrix}-1&0\\0&1\end{bmatrix}$、$\Sigma=\begin{bmatrix}3&0\\0&1\end{bmatrix}$。拼回：

$$
U\Sigma V^\top=\begin{bmatrix}-1&0\\0&1\end{bmatrix}\begin{bmatrix}3&0\\0&1\end{bmatrix}\begin{bmatrix}0&1\\1&0\end{bmatrix}=\begin{bmatrix}0&-3\\1&0\end{bmatrix}=A\ \checkmark
$$

```python
A = np.array([[0,-3],[1,0]])
U, s, Vt = np.linalg.svd(A)   # s = [3, 1]
U @ np.diag(s) @ Vt           # → 回到 A
```

**10.** SVD 把包袱甩给 $A^\top A$——它**永远对称半正定**，谱定理保证一定能正交对角化，所以构造永不卡壳；而特征值分解要求 $A$ **本身**方阵且可对角化。

## F

**11.**

$$
R^\top R=\begin{bmatrix}\cos\theta&\sin\theta\\-\sin\theta&\cos\theta\end{bmatrix}\begin{bmatrix}\cos\theta&-\sin\theta\\\sin\theta&\cos\theta\end{bmatrix}
=\begin{bmatrix}\cos^2\theta+\sin^2\theta&0\\0&\sin^2\theta+\cos^2\theta\end{bmatrix}=I\ \checkmark
$$

**12.** $X=W_Nx$，取共轭转置平方：

$$
\|X\|^2=X^*X=x^*W_N^*W_Nx=N\,x^*x=N\|x\|^2
\ \Rightarrow\ \frac1N\sum_k|X[k]|^2=\sum_n|x[n]|^2\ \checkmark
$$

（DFT 是酉变换 → 保长度 → 能量不丢。）