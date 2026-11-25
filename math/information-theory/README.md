# 信息论 (Information Theory)

> 学习目标：从"越不可能越有信息"的直觉出发，一步步走到熵、交叉熵、KL 散度，理解机器学习 loss 的深层含义。
> 串回：`statistical-inference/probability-distributions.md`（实践）、`statistical-inference/mle.md`（负对数似然=loss）、`machine-learning/neural-network-basics.md`。

## 学习内容

- [x] 信息量：为什么是 -log(p)
- [x] 熵：平均信息量
- [x] 交叉熵：用错的分布去度量
- [x] KL 散度：纯猜错代价
- [x] 条件熵：知道 Y 后 X 还剩多少不确定性
- [x] 互信息：Y 给 X 提供的信息量，= KL(联合‖独立)
- [x] 数据压缩：高频给短码、前缀码、霍夫曼/香农-范诺，熵=压缩下限
- [x] 连续熵与微分熵：连续量推广、正态最大熵、串回 PCA/降维
- [x] 收尾：信息论视角看 loss（MSE/交叉熵/KL 统一为分布间距离）
- [x] 串回机器学习 loss / 特征选择 / 决策树

> 🎉 信息论单元已完成。

## 笔记文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `information-theory.md` | 信息论入门：信息量→熵→交叉熵→KL 散度，串回 MLE 与神经网络 loss | ✅ 已完成 |
| `conditional-entropy-mutual-information.md` | 条件熵→互信息：`I(X;Y)=H(X)−H(X\|Y)=KL(P_xy‖P_x·P_y)`，掷骰子例子，串回决策树/特征选择 | ✅ 已完成 |
| `data-compression-shannon-coding.md` | 数据压缩：高频给短码、前缀码、霍夫曼贪心树/香农-范诺，熵定义压缩下限，串回信息量 | ✅ 已完成 |
| `differential-entropy.md` | 连续熵与微分熵：`∫f·(-log f)`、连续推广、正态最大熵原理，串回 PCA/降维 | ✅ 已完成 |
| `loss-family-information-theory.md` | 收尾：信息论视角看 loss——MSE/交叉熵/KL 统一为"分布间距离 / 猜错代价" | ✅ 已完成 |

## 看过的通路

```
信息量 → 熵 → 交叉熵 → KL散度
   ├─ 互信息 (I = H(X)-H(X|Y) = KL)
   ├─ 压缩 (熵 = 压缩下限; 霍夫曼)
   └─ 微分熵 (连续量; 正态最大熵)
        └─ 全部串回 → 机器学习 loss = "分布间距离 / 猜错代价"
```