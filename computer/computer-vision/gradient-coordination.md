# 参数一起更新，会不会互相干扰？——梯度可加性与梯度下降为什么能收敛

> 记录日期：2026-09-11
> 讲解人：AI（Claude）
> 前置：`neural-network-basics.md`（前向/反向）、`gradient-descent.md`、`backprop-worked-example.md`
> 配套验证代码：`code/_coordcheck.py`（真实运行，非编造数字）
> 数据来源：`code/08_cat_recognizer_from_scratch.py`（seed=42，第 1 轮第 1 张样本）

## 〇、你在问什么

一个网络前向是 `ŷ = A·x + W·x + b` 这样的多层组合。反向传播算出每个参数的梯度后，**所有参数一起更新**。于是你有个很自然的担心：

> "明明只调 b 也能让结果变对，为什么还要同时调 A、调 W？这三个变量彼此耦合，一起动的话，会不会互相干扰、让结果反而更不确定？"

这篇文档回答：**不会。一起更新不但保证损失下降，而且下降量约等于三者各自下降量之和**——有公式、有真实计算证明。

## 一、结论先行（三句话）

1. **每个参数的梯度，是"假设只有它自己动、其他全不动"时算出的最优方向。**
2. **所有参数一起动时，总损失变化 ≈ 各自损失变化之和**（数学上叫"一阶可加性"）。
3. **因为代入梯度后是"梯度的平方和"（恒 ≥ 0），一起动保证损失只降不升**——结果更确定，不是更不确定。

## 二、公式：全微分 + 梯度下降

### 2.1 损失关于所有参数的全微分（一阶泰勒展开）

假设只有三个参数组 A、W、b，损失 $L(A,W,b)$。把所有参数同时动一点 $(\Delta A,\Delta W,\Delta b)$，损失的变化近似为：

$$
\Delta L \approx \underbrace{\frac{\partial L}{\partial A}\Delta A}_{\text{只算 A 的贡献}} + \underbrace{\frac{\partial L}{\partial W}\Delta W}_{\text{只算 W 的贡献}} + \underbrace{\frac{\partial L}{\partial b}\Delta b}_{\text{只算 b 的贡献}}
$$

**关键：第一项就是"只动 A、W、b 不动"时的损失变化，第二、三项同理。** 所以一阶近似下：

$$
\boxed{\ \Delta L_{\text{一起动}} \approx \Delta L_{\text{只动A}} + \Delta L_{\text{只动W}} + \Delta L_{\text{只动b}}\ }
$$

三个参数各自的贡献是**相加**的，不是相抵的。

### 2.2 把梯度下降代进去

梯度下降：$\Delta w = -\eta\,\dfrac{\partial L}{\partial w}$。代入得：

$$
\Delta L \approx -\eta\left[\left(\frac{\partial L}{\partial A}\right)^2 + \left(\frac{\partial L}{\partial W}\right)^2 + \left(\frac{\partial L}{\partial b}\right)^2\right]
$$

**括号里是梯度的平方和，永远 $\ge 0$。** 所以只要学习率 $\eta > 0$，$\Delta L \le 0$——损失只会下降。

### 2.3 "互相影响"去哪了？——二阶项

参数一起动确实有"交叉影响"，但它藏在**二阶项**里：

$$
\Delta L = \underbrace{(\text{一阶项})}_{\text{可加}} + \underbrace{\frac{\partial^2 L}{\partial A\,\partial W}\Delta A\,\Delta W + \cdots}_{\text{二阶交叉项}\ \sim\ \eta^2}
$$

交叉项的量级是 $\eta^2$。**学习率越小，交叉项越小，可加性越精确。** 这就是"学习率必须小"的数学原因（第六节会再讲）。

### 2.4 具体推导：一个能精确验算到底的例子

上面的公式是从哪来的？完整走一遍。先从**单变量**泰勒展开说起：

$$
f(x+\Delta x) = f(x) + \underbrace{f'(x)\Delta x}_{\text{一阶·切线}} + \underbrace{\tfrac12 f''(x)\Delta x^2}_{\text{二阶·曲率}} + O(\Delta x^3)
$$

推广到**多变量** $L(a,w)$（交叉耦合由混合偏导处理）：

$$
L(a{+}\Delta a,\,w{+}\Delta w) = L + \underbrace{\frac{\partial L}{\partial a}\Delta a + \frac{\partial L}{\partial w}\Delta w}_{\text{一阶项}} + \underbrace{\tfrac12\frac{\partial^2 L}{\partial a^2}\Delta a^2 + \frac{\partial^2 L}{\partial a\,\partial w}\Delta a\,\Delta w + \tfrac12\frac{\partial^2 L}{\partial w^2}\Delta w^2}_{\text{二阶项}} + O(\Delta^3)
$$

其中 $\dfrac{\partial^2 L}{\partial a\,\partial w}\Delta a\,\Delta w$ 就是**交叉项**——a、w 互相放大对方的部分，量级 $=\Delta a\cdot\Delta w\sim\eta^2$。

**精确验算的例子**：选二次函数 $L=(1-(a+w))^2$，起点 $a=w=0$，步长 $\Delta a=\Delta w=0.02$。起点处各导数为：$\dfrac{\partial L}{\partial a}=\dfrac{\partial L}{\partial w}=-2$，$\dfrac{\partial^2 L}{\partial a^2}=\dfrac{\partial^2 L}{\partial w^2}=2$，**交叉 $\dfrac{\partial^2 L}{\partial a\,\partial w}=2$**。

精确移动（地面真相）：

$$
L(0.02,0.02)=(1-0.04)^2 = 0.9216 \quad\Rightarrow\quad \Delta L_{\text{精确}} = -0.0784
$$

用泰勒重建（二次函数 $O(\Delta^3)=0$，是恒等式）：

$$
\text{一阶 } (-2)(0.02)+(-2)(0.02) = -0.0800
$$
$$
\text{二阶自项 } \tfrac12\cdot2\cdot0.0004\times2 = 0.0008,\qquad \text{交叉项 } 2\times0.02\times0.02 = 0.0008
$$
$$
\text{泰勒预测 } -0.0800 + 0.0016 = -0.0784 = \text{精确值}\ \checkmark
$$

现在把"互相干扰"精确抓出来——对比单独动和一起动：

| 更新方式 | 结果 | ΔL |
|---|---|---|
| 只动 a | L(0.02,0) = 0.9604 | −0.0396 |
| 只动 w | L(0,0.02) = 0.9604 | −0.0396 |
| 单独之和 | — | −0.0792 |
| **一起动** | L(0.02,0.02) = 0.9216 | **−0.0784** |
| 差 | — | **+0.0008** |

$$
\Delta L_{\text{一起动}} - \big(\Delta L_a + \Delta L_w\big) = 0.0008 = \underbrace{\frac{\partial^2 L}{\partial a\,\partial w}\Delta a\,\Delta w}_{\text{交叉项}}
$$

**结论：一起动 ≠ 各自之和的唯一来源就是交叉项**，而它 $\sim\eta^2$，学习率小就消失。

最后把梯度下降 $\Delta w_i = -\eta\,\frac{\partial L}{\partial w_i}$ 代入一阶部分，得到平方和公式：

$$
\Delta L \approx \sum_i \frac{\partial L}{\partial w_i}\Delta w_i = \sum_i \frac{\partial L}{\partial w_i}\Big(-\eta\frac{\partial L}{\partial w_i}\Big) = -\eta\sum_i\Big(\frac{\partial L}{\partial w_i}\Big)^2 \le 0
$$

**真实网络实测**（`code/_derivcheck.py`，全部 218 个参数 $\sum g^2 = 1.524775$）：

| lr | 公式预测 $lr\cdot\sum g^2$ | 实际下降（测量） | 二阶余项 |
|---|---|---|---|
| 0.3 | +0.457433 | +0.379922 | 7.8e-2 |
| 0.03 | +0.045743 | +0.045201 | 5.4e-4 |
| 0.003 | +0.004574 | +0.004570 | **4.3e-6** |

二阶余项随 $lr^2$ 缩小——**公式不是空话，在真实网络上逐位对得上**。

### 2.5 二阶项到底怎么推出来的

多变量展开里的二阶项（系数 $\tfrac12,\,1,\,\tfrac12$）看着是背的，其实有标准推法。核心技巧：**把"两个变量同时动"改写成"沿一条直线走一步"**，然后用一次单变量泰勒展开，二阶项自己冒出来。

**① 定义沿直线走的参数化函数**（$t$ 从 0 走到 1）：

$$
g(t) = L\big(a + t\,\Delta a,\ w + t\,\Delta w\big),\qquad g(0)=L(a,w),\ g(1)=L(a{+}\Delta a,w{+}\Delta w)
$$

$g(t)$ 是普通一元函数，对它用**单变量泰勒展开**。展开点选 $t=0$：那里是"当前参数"（前向刚跑过），$g$ 的值、各阶导数全都算得出来；$t=1$ 是"更新后"，还没跑前向、一无所知。泰勒就是用 $t=0$ 的局部信息（高度+斜率+曲率）去**估计** $t=1$ 的值。

**单变量泰勒公式（展开到二阶，带拉格朗日余项）**：

$$
g(t) = \underbrace{g(0) + g'(0)\,t + \tfrac12 g''(0)\,t^2}_{\text{前二阶近似}} + \underbrace{\frac{g'''(\xi)}{3!}\,t^3}_{\text{余项 }R_2},\qquad \xi\in(0,t)
$$

- 前三项：只用 $t=0$ 处的值、一阶导、二阶导，就能近似任意 $t$ 处的 $g$
- 余项 $R_2$：真实函数与前二阶近似之间的误差，由"某个中间点 $\xi$ 的三阶导 $\times\, t^3$"刻画

代入 $t=1$（步长 $h=1$，故 $1^1=1^2=1^3=1$）：

$$
g(1) = g(0) + g'(0)\cdot 1 + \tfrac12 g''(0)\cdot 1^2 + \frac{g'''(\xi)}{3!}\cdot 1^3
$$

**为什么本例余项恒为 0**：因为 $L=(1-(a+w))^2$ 是**二次函数**。代入直线参数化后（本例 $a=w=0$，$\Delta a+\Delta w=0.04$）：

$$
g(t) = \Big(1 - (a+w) - t(\Delta a+\Delta w)\Big)^2 = 1 - 0.08\,t + 0.0016\,t^2
$$

这是 $t$ 的**二次多项式**，三阶导 $g'''(t)\equiv 0$，所以 $R_2\equiv 0$——泰勒到二阶就**精确等于**原函数。用数字验证：$g(1)=1-0.08+0.0016=0.9216$，一分不差。**一般规律：$n$ 次多项式 = 它自己的 $n$ 阶泰勒展开**（更高阶项在多项式里不存在）。真实网络的 $L=-\ln p_y$ 不是二次的，余项不为 0——2.4 末尾实测表里那个随 $lr^2$ 缩小的"二阶余项"就是它。

**② 链式法则算 $g'(t)$（一阶项）**——展开算一遍，别只记结论。

先看结构：$g(t)$ 是**复合函数** $g(t)=L\big(a(t),w(t)\big)$，其中 $a(t)=a+t\Delta a$、$w(t)=w+t\Delta w$。$L$ 有两个输入，每个又都是 $t$ 的函数，所以要用**多元链式法则**——$t$ 动一点，既通过 $a(t)$ 影响 $L$、又通过 $w(t)$ 影响 $L$，两条路的贡献相加：

$$
g'(t) = \frac{\partial L}{\partial a}\,\frac{da}{dt} + \frac{\partial L}{\partial w}\,\frac{dw}{dt}
$$

算两个内层导数：

$$
\frac{da}{dt} = \frac{d}{dt}\big(a+t\Delta a\big) = \Delta a,\qquad \frac{dw}{dt} = \frac{d}{dt}\big(w+t\Delta w\big) = \Delta w
$$

代入：

$$
g'(t) = \frac{\partial L}{\partial a}\,\Delta a + \frac{\partial L}{\partial w}\,\Delta w
$$

**代入本例数字**（$L=(1-(a+w))^2$，点 $(0,0)$，$\Delta a=\Delta w=0.02$）。先算偏导：设 $v=1-(a+w)$，则 $L=v^2$、$\frac{dv}{da}=-1$，由链式法则

$$
\frac{\partial L}{\partial a} = \frac{dL}{dv}\frac{dv}{da} = 2v\cdot(-1) = -2(1-a-w) \quad\xrightarrow{\ (0,0)\ }\quad -2
$$

同理 $\frac{\partial L}{\partial w}=-2$。代回并取 $t=0$：

$$
g'(0) = (-2)(0.02) + (-2)(0.02) = -0.04 - 0.04 = \boxed{-0.08}
$$

**交叉验证**（直接对 $g(t)$ 求导，应得同一数）：$g(t)=\big(1-(a+w)-t(\Delta a+\Delta w)\big)^2$，其内层对 $t$ 求导为 $-(\Delta a+\Delta w)$，故

$$
g'(0) = -2(1-a-w)(\Delta a+\Delta w) = -2\times1\times0.04 = -0.08\ \checkmark
$$

两种算法殊途同归：**$g'(0)=-0.08$，正是 2.4 例子里"一阶项 $-0.0800$"的来源**。

**③ 再求导算 $g''(t)$**——展开算一遍。起点是②的结论，对它再对 $t$ 求一次导：

$$
g'(t) = \frac{\partial L}{\partial a}\Delta a + \frac{\partial L}{\partial w}\Delta w
\qquad\Longrightarrow\qquad
g''(t) = \frac{d}{dt}\Big[\frac{\partial L}{\partial a}\Delta a\Big] + \frac{d}{dt}\Big[\frac{\partial L}{\partial w}\Delta w\Big]
$$

**先算第一项**。$\frac{\partial L}{\partial a}\,\Delta a$ 是"函数 × 常数"：$\Delta a$ 不随 $t$ 变，提到导数外面；而 $\frac{\partial L}{\partial a}$ 本身依赖 $a(t),w(t)$，是**复合函数，还要再用一次多元链式法则**：

$$
\frac{d}{dt}\Big[\frac{\partial L}{\partial a}\Delta a\Big] = \Big[\frac{d}{dt}\Big(\frac{\partial L}{\partial a}\Big)\Big]\Delta a
$$

$$
\frac{d}{dt}\Big(\frac{\partial L}{\partial a}\Big) = \frac{\partial^2 L}{\partial a^2}\underbrace{\frac{da}{dt}}_{\Delta a} + \frac{\partial^2 L}{\partial a\,\partial w}\underbrace{\frac{dw}{dt}}_{\Delta w} = \frac{\partial^2 L}{\partial a^2}\Delta a + \frac{\partial^2 L}{\partial a\,\partial w}\Delta w
$$

所以：

$$
\frac{d}{dt}\Big[\frac{\partial L}{\partial a}\Delta a\Big] = \Big(\frac{\partial^2 L}{\partial a^2}\Delta a + \frac{\partial^2 L}{\partial a\,\partial w}\Delta w\Big)\Delta a = L_{aa}\,\Delta a^2 + L_{aw}\,\Delta a\,\Delta w
$$

**第二项完全对称**（$\frac{\partial L}{\partial w}$ 也是复合函数）：

$$
\frac{d}{dt}\Big[\frac{\partial L}{\partial w}\Delta w\Big] = \Big(\frac{\partial^2 L}{\partial w\,\partial a}\Delta a + \frac{\partial^2 L}{\partial w^2}\Delta w\Big)\Delta w = L_{wa}\,\Delta w\,\Delta a + L_{ww}\,\Delta w^2
$$

**两项相加**：

$$
g''(t) = L_{aa}\,\Delta a^2 + \big(L_{aw}+L_{wa}\big)\Delta a\,\Delta w + L_{ww}\,\Delta w^2
$$

**代入本例数字验证**（$L=(1-(a+w))^2$，点 $(0,0)$，$\Delta a=\Delta w=0.02$）。先算二阶偏导（对②算出的 $-2(1-a-w)$ 再求导）：

$$
\frac{\partial^2 L}{\partial a^2} = \frac{\partial}{\partial a}\big[-2(1-a-w)\big] = 2,\qquad
\frac{\partial^2 L}{\partial w^2} = 2,\qquad
\frac{\partial^2 L}{\partial a\,\partial w} = \frac{\partial^2 L}{\partial w\,\partial a} = 2
$$

代入：

$$
g'' = 2\times0.0004 + (2+2)\times0.0004 + 2\times0.0004 = 0.0008 + 0.0016 + 0.0008 = \boxed{0.0032}
$$

**交叉验证**（直接对 $g(t)$ 求两次导）：$g(t)=(1-0.04t)^2$，则 $g'(t)=-0.08(1-0.04t)$，再导得

$$
g''(t) = 0.0032\ \checkmark
$$

三种说法（逐项展开 / 数值代入 / 直接求导）得到同一个 $0.0032$——这就是 2.4 例子里"二阶合计 $0.0016 = \tfrac12 g''$"的来源。

**④ 那个"2"的来历**：对光滑函数两种混合偏导顺序相等（克莱罗定理）$L_{aw}=L_{wa}$，所以交叉项系数是 $2$：

$$
g''(t) = \frac{\partial^2 L}{\partial a^2}\Delta a^2 + 2\,\frac{\partial^2 L}{\partial a\,\partial w}\Delta a\,\Delta w + \frac{\partial^2 L}{\partial w^2}\Delta w^2
$$

> 直觉：交叉项代表"a、w 互相影响"。沿直线走，既有"先动 a、再被 w 影响"这条路，也有"先动 w、再被 a 影响"这条路，两条路各贡献一份，所以是 $\Delta a\,\Delta w$ 的两倍。

**⑤ 代回泰勒的 $\tfrac12 g''(0)$，系数 2 折半成 1**：

$$
\boxed{\ \tfrac12\frac{\partial^2 L}{\partial a^2}\Delta a^2 + \frac{\partial^2 L}{\partial a\,\partial w}\Delta a\,\Delta w + \tfrac12\frac{\partial^2 L}{\partial w^2}\Delta w^2\ }
$$

这就是 2.4 例子里三个二阶项的系数 ½、1、½ 的来由。

**⑥ 用 2.4 的数字验证**（$L=(1-(a+w))^2$，$a=w=0$，$\Delta a=\Delta w=0.02$，$L_{aa}=L_{ww}=2$，$L_{aw}=2$）：

$$
g'' = 2\times0.0004 + 2\times2\times0.0004 + 2\times0.0004 = 0.0032
\qquad
\tfrac12 g'' = 0.0016
$$

正好等于 2.4 里"二阶合计 $0.0016$"，一个数不差。

> 为什么二次函数展开到二阶就精确：$L$ 是二次的，三阶及以上偏导全为 0，$O(\Delta^3)=0$，泰勒到二阶是恒等式而非近似。

## 三、先来个能心算的玩具（三个标量参数）

设模型输出 $\hat y = a\cdot1 + w\cdot1 + b = a+w+b$，目标 $t=1$，损失 $L=(1-\hat y)^2$。起点 $a=w=b=0$，则 $\hat y=0$，$L=1$，误差 $e=1$，三个梯度都是 $-2$。

取学习率 $\eta=0.01$：

| 更新方式 | 更新后 | $\hat y$ | $L$ | $\Delta L$ |
|---------|--------|---------|-----|-----------|
| 只动 a | $a=0.02$ | 0.02 | 0.9604 | 0.0396 |
| 只动 w | $w=0.02$ | 0.02 | 0.9604 | 0.0396 |
| 只动 b | $b=0.02$ | 0.02 | 0.9604 | 0.0396 |
| **一起动** | $a=w=b=0.02$ | **0.06** | **0.8836** | **0.1164** |
| 单独下降之和 | — | — | — | 0.1188 |

看三点：

1. **只动任何一个参数，损失都降到 0.9604；一起动，降到 0.8836——比任何单独动都低。** 更确定，不是更不确定。
2. **一起动的下降 0.1164 ≈ 单独下降之和 0.1188**，差 0.0024。
3. 这 0.0024 正是**二阶交叉项** $= 24\eta^2$（$24\times0.01^2 = 0.0024$）。这是二次函数，展开精确到二阶，所以你能"看见"交叉项长什么样——它随 $\eta^2$ 缩小。

> 换 $\eta=0.001$ 再算：单独之和 $0.011988$，一起动 $0.011964$，差 $0.000024=24\times0.001^2$——**误差小了 100 倍**。可加性随 $\eta$ 变好，肉眼可见。

## 四、真实网络的"铁证"（`_coordcheck.py` 实际运行）

上面的玩具太理想。换成**真实 cat 网络**（16×16 卷积 CNN，第 1 轮第 1 张样本），对四组参数（卷积层 A=W1+b1、全连接权重 W=W2、偏置 b=b2）做完全相同的实验——用**同一份梯度**，分别只动 A / 只动 W / 只动 b / 一起动，测真实交叉熵损失：

$$
L_0 = 0.648027
$$

| 学习率 $\eta$ | 只动 b | 只动 W | 只动 A | **一起动 Δ总** | 单独之和 Δb+ΔW+ΔA | 相对误差 |
|:---:|---:|---:|---:|---:|---:|---:|
| 0.3 | +0.126339 | +0.246818 | +0.015266 | **+0.379922** | +0.388428 | 2.24% |
| 0.03 | +0.013545 | +0.028795 | +0.002742 | **+0.045201** | +0.045082 | 0.26% |
| 0.003 | +0.001364 | +0.002922 | +0.000283 | **+0.004570** | +0.004569 | 0.03% |

（相对误差 $= \big|\Delta\text{总} - (\Delta b+\Delta W+\Delta A)\big| \big/ \Delta\text{总}$）

**三条铁证：**

1. **任何一行，一起动的下降都是最大**——即使 $\eta=0.3$ 这种大学习率，一起动也把损失降了 0.38，远超任何单独动。
2. **可加性成立**：$\Delta\text{总} \approx \Delta b+\Delta W+\Delta A$，在 $\eta=0.03$ 时已经差到 $10^{-4}$ 量级。
3. **误差随学习率线性缩小**（2.24% → 0.26% → 0.03%，每缩小 10 倍 lr，误差也约缩 10 倍）——这正是二阶交叉项 $O(\eta^2)$ 的行为。**学习率越小，三组参数越"互不干扰"。**

## 五、回到"只改 b 就够了"

你直觉的另一半值得认真回应：单样本上，只调 b 确实能把损失压下来（第四节第一列都是正的下降）。但训练不是满足一张图：

| 为什么不能只调 b | 解释 |
|------------------|------|
| **b 是全局常数** | 128 张训练图共用同一个 b，每张图"想要的 b"都不同，没有一个 b 能同时满足所有图。让不同图给出不同输出，正是 A、W 的职责。 |
| **b 只会"平移"** | 给得分加常数偏移。只靠 b 学不出"耳朵=猫"，最多得到"永远猜猫/永远猜非猫"的恒定模型。决策边界的**形状**靠 A、W，b 只是微调**位置**。 |
| **正确 b 依赖 A/W** | A/W 一直在变，"此刻最优的 b"也在变。所以 b 不能一次定死，必须跟着一起学。 |

还有一个**自平衡**性质：错误信号是共享的——A/W 学得越好，误差越小，b 收到的梯度也自动变小。所以三组参数不是抢功，而是**协作收敛**到所有梯度都 ≈ 0 的局部最优。

## 六、为什么学习率必须小（把两件事串起来）

- **可加性误差 = 二阶交叉项 $\sim \eta^2$**。学习率一大，参数之间的耦合就开始"发威"，一起动会偏离"各自之和"，更新就可能来回震荡、甚至发散。
- 这正是你脚本里踩过的坑：`lr=0.3` 时第 1 轮梯度太大，把卷积核一步推进 ReLU 死亡区，梯度全灭，模型永远学不动（dying ReLU）。第二节的平方和公式是"一阶保证下降"，但**二阶项一旦压不住，一阶保证就不够用了**。
- 所以真实框架（PyTorch/TensorFlow）默认学习率都取小值（$10^{-3}\sim10^{-2}$），还配动量、学习率衰减——本质都是在压制二阶交叉项、让"可加性"这条主旋律成立。

## 七、一句话总结

> 每个参数按"别人不动时"的最优方向迈一小步；一起迈时，总效果 ≈ 各自效果之和（梯度平方和保证只降不升）；参数间的相互影响是 $\eta^2$ 量级的二阶项，靠小学习率压住。所以一起更新不是"更不确定"，而是**严格更确定**——这就是梯度下降能收敛的数学根基。

## 八、怎么自己复现

```bash
cd computer/computer-vision/code
python _coordcheck.py
```

脚本用**同一份梯度**（真实网络第 1 样本），分别只动 A / W / b / 一起动，按三种学习率打印上面第四节那张表。改 `lr` 列表、改 `train_data[0]` 换成别的样本，都能重复看到"一起动降最多、误差随 lr 缩小"。

---

## 对照前面笔记

| 内容 | 对应笔记 |
|------|---------|
| 链式法则、梯度是什么 | `neural-network-basics.md` |
| 梯度下降、学习率、dying ReLU | `gradient-descent.md` |
| 单个参数的前向/反向全流程 | `backprop-worked-example.md` |
