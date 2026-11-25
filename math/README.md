# 数学 (Math)

## 学习内容

- [x] 泰勒展开：公式从哪来、收敛半径、为什么 eˣ 处处可展开
- [x] 复数与复平面：i²=−1、四则运算、欧拉公式、串回泰勒收敛半径
- [ ] 高等数学：极限、导数、积分、级数
- [ ] 线性代数：向量/矩阵/线性变换 → 方程组与秩 → 行列式与逆 → 特征值 → SVD → 正交矩阵（🟡 进行中，侧重基本原理 + 技术应用）
- [x] 概率统计：分布 + 推断 + 假设检验（✅ 已完成）
- [x] 信息论：熵、交叉熵、KL 散度（✅ 已完成）
- [ ] 离散数学

## 笔记文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `taylor-series/README.md` | 泰勒展开主题大纲 | ✅ 已完成 |
| `taylor-series/taylor-expansion.md` | 泰勒展开：匹配导数拼多项式、收敛半径=到最近奇点距离、eˣ 整函数 vs 1/(1-x) 局部展开、e^{-1/x²} 光滑但非解析、解析延拓 | ✅ 已完成 |
| `complex-numbers/README.md` | 复数与复平面主题大纲 | ✅ 已完成 |
| `complex-numbers/complex-numbers.md` | 复数入门：数系扩充、四则运算、复平面、共轭/模、极坐标与欧拉公式、e^z 处处可导、串回泰勒收敛半径 | ✅ 已完成 |
| `linear-algebra/README.md` | 线性代数大纲：矩阵=变换主线，原理 + 应用，串回 FFT/CNN/纳米精度 | 🟡 进行中 |
| `linear-algebra/vectors-and-matrices.md` | 向量、矩阵=线性变换、矩阵乘法=复合、换基（含 DFT=换基） | 🟡 进行中 |
| `statistical-inference/README.md` | 统计推断主题大纲 | ✅ 已完成 |
| `statistical-inference/probability-distributions.md` | 概率分布地基：离散vs连续、伯努利/二项/均匀/泊松/正态、期望方差速查、参数即"旋钮" | ✅ 已完成 |
| `statistical-inference/mle.md` | 最大似然估计：抛硬币问题→似然→连乘→对数→求导、伯努利/正态推导、串回交叉熵与 MSE | ✅ 已完成 |
| `statistical-inference/bayesian-inference.md` | 贝叶斯推断：先验×似然→后验、共轭先验（贝塔）、MAP、MLE⊂MAP⊂贝叶斯 | ✅ 已完成 |
| `statistical-inference/hypothesis-testing.md` | 假设检验：p 值正确读法、α、两类错误、置信区间、五个翻车坑 | ✅ 已完成 |
| `information-theory/README.md` | 信息论主题大纲 | ✅ 已完成 |
| `information-theory/information-theory.md` | 信息论入门：信息量→熵→交叉熵→KL 散度，串回 MLE 与神经网络 loss | ✅ 已完成 |
| `information-theory/conditional-entropy-mutual-information.md` | 条件熵→互信息：`I(X;Y)=H(X)−H(X\|Y)=KL(P_xy‖P_x·P_y)`，串回决策树/特征选择 | ✅ 已完成 |
| `information-theory/data-compression-shannon-coding.md` | 数据压缩：高频给短码、前缀码、霍夫曼贪心树/香农-范诺，熵=压缩下限 | ✅ 已完成 |
| `information-theory/differential-entropy.md` | 连续熵与微分熵：`∫f·(-log f)`、连续推广、正态最大熵原理，串回 PCA/降维 | ✅ 已完成 |
| `information-theory/loss-family-information-theory.md` | 收尾：信息论视角看 loss——MSE/交叉熵/KL 统一为"分布间距离 / 猜错代价" | ✅ 已完成 |
