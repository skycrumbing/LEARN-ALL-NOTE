# SVD：任意矩阵的"旋转-缩放-旋转"

> 特征值分解只对特定方阵成立；SVD（奇异值分解）对**任意 $m\times n$ 矩阵**都成立。它是线性代数的瑞士军刀——PCA、伪逆、低秩压缩、Kabsch 全都归到它身上。

## 一、一句话：三个动作拆任何矩阵

$$
\boxed{\ A = U\,\Sigma\,V^\top\ }
$$

- $U$、$V$：正交矩阵（旋转或镜像）
- $\Sigma$：对角且非负，对角元 $\sigma_1\ge\sigma_2\ge\dots\ge 0$ 叫**奇异值**

几何读法（从右往左）：

$$
x\ \xrightarrow{\ V^\top\ }\ \text{旋转}\ \xrightarrow{\ \Sigma\ }\ \text{沿坐标轴缩放}\ \xrightarrow{\ U\ }\ \text{再旋转}
$$

**任何线性变换 = 一次旋转 + 沿轴缩放 + 又一次旋转。**

### 预备：什么是谱定理

要证明 SVD 恒存在，只借一个工具——**谱定理（spectral theorem）**，它只对**对称矩阵**成立：

> **谱定理**：若 $S=S^\top$（实对称），则
> 1. 它的特征值**全是实数**（证略）；
> 2. 它的特征向量可以选成**两两正交、且单位长**；
> 3. 因此 $S=Q\Lambda Q^\top$，$Q$ 的列是那组正交特征向量、$\Lambda$ 对角、$Q$ 正交（$Q^{-1}=Q^\top$）。

对比普通方阵的 $A=V\Lambda V^{-1}$（要求可对角化、$V$ 还不正交），对称矩阵是**无条件成立**并额外送一个"$Q$ 正交"。

**为什么对称矩阵的特征向量必正交？** 设 $Su=\lambda u$、$Sv=\mu v$（$\lambda\ne\mu$），用对称性 $u^\top S=(Su)^\top$：

$$
\lambda\,u^\top v = (Su)^\top v = u^\top S v = u^\top(\mu v)=\mu\,u^\top v
\ \Rightarrow\ (\lambda-\mu)\,u^\top v=0\ \Rightarrow\ u^\top v=0
$$

不同特征值的特征向量被迫正交（相同特征值的再用 Gram–Schmidt 补齐即可）。

> **半正定**：若再满足 $x^\top S x\ge0$，则特征值全 $\ge0$——代入单位特征向量 $v_i$：$\lambda_i=v_i^\top S v_i\ge0$。

### 第一步：把问题甩给 $A^\top A$

难点在"任意 $m\times n$ 都行"，而特征值分解只对方阵成立。破局：**不拆 $A$，看 $A^\top A$**。它满足谱定理的条件：

- **对称**：$(A^\top A)^\top=A^\top(A^\top)^\top=A^\top A$
- **半正定**：任意 $x$，$x^\top A^\top Ax=(Ax)^\top(Ax)=\|Ax\|^2\ge0$
- 且 $A^\top A$ 是 $n\times n$ **方阵**

### 第二步：谱定理给出 $V$ 与 $\sigma$

对 $A^\top A$ 套谱定理：存在正交 $V=[v_1,\dots,v_n]$ 和特征值 $\lambda_1\ge\dots\ge\lambda_n\ge0$，使 $A^\top A=V\operatorname{diag}(\lambda_1,\dots,\lambda_n)V^\top$。定义**奇异值** $\sigma_i=\sqrt{\lambda_i}$（$\lambda_i\ge0$ 保证能开方、非负）：

$$
A^\top A = V\Sigma^2 V^\top
$$

### 第三步：由 $v_i$ 造 $u_i$

对每个 $\sigma_i\ne0$，令 $u_i=\dfrac{Av_i}{\sigma_i}$。验证 $\{u_i\}$ 正交归一：

$$
u_i^\top u_j
= \frac{(Av_i)^\top(Av_j)}{\sigma_i\sigma_j}
= \frac{v_i^\top A^\top A v_j}{\sigma_i\sigma_j}
= \frac{\lambda_j\,v_i^\top v_j}{\sigma_i\sigma_j}
$$

- $i\ne j$：$v_i^\top v_j=0$（正交）→ 得 $0$；
- $i=j$：$v_i^\top v_i=1$（单位长）、$\sigma_i^2=\lambda_i$ → 得 $\lambda_i/\sigma_i^2=1$。

所以 $\{u_i\}$ 正交归一，能拿来当 $U$ 的列。

### 第四步：拼回

把 $u_i=\dfrac{Av_i}{\sigma_i}$ 改写成 $Av_i=\sigma_i u_i$——这是 $A$ 逐列的关系。合起来：

$$
A = \sum_i \sigma_i\,u_i v_i^\top = U\Sigma V^\top
$$

$\sigma_i=0$ 的维、以及 $m>n$ 多余的维，随便补正交向量凑满 $U$（它们乘 0，不影响结果）。

**整个过程没有任何一步会卡住**：$A^\top A$ 的谱分解恒存在 → 正交化恒能做。所以 SVD 对任意矩阵成立，这就是"万能"的来源。

**几何意义**：单位圆被 $A$ 映成椭圆。$\sigma_i$ = 半轴长，$U$ 的列 = 半轴方向，$V^\top$ 描述"输入的哪条方向落到哪根半轴上"；$\sigma_i=0$ 表示那根半轴被压成 0（椭圆退化、丢一维），接第二篇的 rank 视角。

对比：特征值分解 $A=V\Lambda V^{-1}$ 要求 $A$ **本身**方阵且可对角化；SVD 把包袱甩给"永远规整"的 $A^\top A$，处处能用。

## 二、奇异值与特征值的关系，还有秩

**这个关系是怎么来的？** 假设 $A=U\Sigma V^\top$ 成立，两边转置相乘：

$$
A^\top A = \underbrace{(U\Sigma V^\top)^\top}_{V\Sigma^\top U^\top}(U\Sigma V^\top)
= V\Sigma^\top\underbrace{U^\top U}_{I}\Sigma V^\top
= V\Sigma^2 V^\top
$$

$$
AA^\top = (U\Sigma V^\top)(V\Sigma^\top U^\top)
= U\Sigma\underbrace{V^\top V}_{I}\Sigma^\top U^\top
= U\Sigma^2 U^\top
$$

（用了正交性 $U^\top U=V^\top V=I$，以及 $\Sigma$ 对角 $\Rightarrow\Sigma^\top\Sigma=\Sigma^2$，对角元是 $\sigma_i^2$。）读这两行：

$$
\boxed{\ V\text{ 的列} = A^\top A\text{ 的特征向量（右奇异向量）},\qquad \sigma_i^2 = A^\top A\text{ 的特征值}\ }
$$

（同理 $U$ 的列是 $AA^\top$ 的特征向量，叫**左奇异向量**。）

**为什么 $\sigma_i^2\ge0$？** 任意 $x$ 都有 $x^\top A^\top Ax=\|Ax\|^2\ge0$，故 $A^\top A$ 半正定、特征值非负，于是 $\sigma_i=\sqrt{\lambda_i(A^\top A)}\ge0$ 能开方、能排序。

**于是"求 SVD"的菜谱是**：先求 $A^\top A$ 的特征值/特征向量拼出 $V$ 和 $\sigma_i$；再由 $u_i=\tfrac1{\sigma_i}Av_i$（$\sigma_i\ne0$）得 $U$（来源是 $Av_i=\sigma_iu_i$）；剩余维度补正交基凑满，最后拼回 $A=U\Sigma V^\top$。所以文档开头那句"$V$ 是 $A^\top A$ 的特征向量"**不是结论，是构造 SVD 的入口**。

**为什么非零奇异值个数 = 秩？** 两步：

1. $\operatorname{rank}(A^\top A)=\operatorname{rank}(A)$——两者零空间相等：$Ax=0\Rightarrow A^\top Ax=0$；反过来 $A^\top Ax=0\Rightarrow x^\top A^\top Ax=\|Ax\|^2=0\Rightarrow Ax=0$。零空间相等，再由第二篇的维数定理（$\operatorname{rank}+\dim\mathrm{null}=n$）得秩相等。
2. $\operatorname{rank}(A^\top A)=$ 非零特征值个数——因为 $A^\top A=V\Sigma^2V^\top$ 已对角化，秩 = 对角线上非零元个数 = 非零 $\sigma_i^2$ 个数 = 非零 $\sigma_i$ 个数。

合并即得：

$$
\boxed{\ \text{非零奇异值的个数} = \operatorname{rank}(A)\ }
$$

**把第二篇那个 rank=1 的例子彻底算一遍对号。** $A=\begin{bmatrix}1&2\\3&6\end{bmatrix}$。

① 求 $A^\top A$ 与 $V$：

$$
A^\top A=\begin{bmatrix}1&3\\2&6\end{bmatrix}\begin{bmatrix}1&2\\3&6\end{bmatrix}=\begin{bmatrix}10&20\\20&40\end{bmatrix}
$$

迹 $=50$、行列式 $=10\cdot40-20\cdot20=0$，故 $\sigma_1^2=50,\ \sigma_2^2=0$。特征向量：$A^\top A\begin{bmatrix}1\\2\end{bmatrix}=50\begin{bmatrix}1\\2\end{bmatrix}$，故 $v_1=\tfrac1{\sqrt5}[1,2]^\top$；零向量方向 $v_2=\tfrac1{\sqrt5}[2,-1]^\top$。

② 求 $AA^\top$ 与 $U$：$AA^\top=\begin{bmatrix}5&15\\15&45\end{bmatrix}$，$u_1=\tfrac1{\sqrt{10}}[1,3]^\top$、$u_2=\tfrac1{\sqrt{10}}[3,-1]^\top$。

③ 拼回验证（$\sigma_2=0$ 那项不贡献）：

$$
A=\sigma_1 u_1 v_1^\top
=\sqrt{50}\cdot\frac{[1,3]^\top}{\sqrt{10}}\cdot\frac{[1,2]}{\sqrt5}
=\frac{\sqrt{50}}{\sqrt{50}}\,[1,3]^\top[1,2]
=\begin{bmatrix}1&2\\3&6\end{bmatrix}\ \checkmark
$$

看到没有：**矩阵 $A$ 其实只是一个 rank-1 外积 $\sigma_1u_1v_1^\top$**，非零奇异值 1 个，正好等于 rank 1。（那些 $\sigma_i=0$ 对应的 $v$ 正落在 $A$ 的零空间里，被拍成 $\sigma\cdot0=0$——就是"被压掉、救不回的维度"。）

## 三、低秩近似 = 有损压缩的数学根基

SVD 也可以写成秩一外积的和：

$$
A = \sum_{i}\sigma_i\,u_i v_i^\top
$$

$\sigma_i$ 从大到小排，**越往后贡献越小**。只保留前 $k$ 项，得到在所有 rank-$k$ 矩阵里误差最小的近似（Eckart–Young 定理）。

**应用：图像压缩。** 一张灰度图就是矩阵 $A$，保留前 $k$ 个奇异值：

```python
import numpy as np
U, s, Vt = np.linalg.svd(A, full_matrices=False)
k = 20
A_k = U[:, :k] @ np.diag(s[:k]) @ Vt[:k, :]   # 只剩 20 层外积的近似图
```

存储从 $m\times n$ 降到 $k(m+n+1)$。$k$ 越小越省、也越糊——**"有损压缩"的本质就是扔掉小奇异值对应的高频细节**。

## 四、应用 2：PCA（接上一篇）

上一篇说"协方差矩阵特征值=方差、特征向量=主方向"。用 SVD 一步到位：把数据**中心化**成矩阵 $X$（$n$ 样本 × $d$ 特征），

$$
X = U\Sigma V^\top \ \Rightarrow\ \tfrac1n X^\top X = \tfrac1n V\Sigma^2 V^\top
$$

所以 **右奇异向量 $V$ 的列 = 主方向，$\sigma_i^2/n$ = 该方向方差**。最大的 $\sigma_1$ 对应"数据铺得最开"的第一主成分——**PCA 就是 SVD 的一个应用**。

## 五、应用 3：SVD 伪逆（串回线性方程篇）

线性方程篇给的伪逆 $A^+=(A^\top A)^{-1}A^\top$ **只在列满秩时成立**；列不满秩时 $A^\top A$ 不可逆，直接失效。SVD 版通吃：

$$
\boxed{\ A^+ = V\,\Sigma^+\,U^\top\ }
$$

$\Sigma^+$ 是把每个**非零**奇异值取倒数（零奇异值保持 0、跳过）。好处：rank 不满、病态（$\sigma_i$ 接近于 0）都能给出"最稳妥"的解——把趋近 0 的 $\sigma$ 截断，正是工程里防噪声放大的经典手段（这正是上一篇 `determinant-inverse.md` 第五节埋伏的"为什么不直接求逆"的答案）。

## 六、应用 4：Kabsch 对齐（直连纳米精度）

求两个点云间的**最优旋转**：算互相关矩阵 → 做 SVD → $R=VU^\top$ 即为去噪后的最优旋转。这个 SVD 用法你在 `physics/mechanical/nanometer-precision-math.md` 第四节已经完整手推过（求最小奇异值对应向量做零空间、单应 DLT 也是同一招）。这里是它在"分解工具箱"里的位置。

## 七、小结与速查

| 概念 | 一句话 | 应用钩子 |
|------|--------|----------|
| SVD $A=U\Sigma V^\top$ | 任意矩阵 = 旋转·缩放·旋转 | 万能分解 |
| 非零奇异值个数 | = rank | 判定信息维数 |
| 截断 SVD（前 $k$ 项） | 最佳 rank-$k$ 近似 | 图像/数据压缩 |
| 右奇异向量 $V$ | 主方向 | PCA |
| SVD 伪逆 $V\Sigma^+U^\top$ | 通吃的伪逆 | 病态/秩亏方程 |

---

**下一步**：`orthogonal-unitary.md` —— 正交/酉矩阵（保长度保角度），把 DFT 矩阵、旋转矩阵、Parseval 这些"保距"的东西统一收口。