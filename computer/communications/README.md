# 数字通信与信号处理 (Digital Communications / Signal Processing)

> 学习目标：理解"电磁波 → 数字 → 比特"这条链，掌握傅里叶变换 / FFT 这一核心数学工具。

## 笔记文件

| 文件 | 说明 | 状态 |
|------|------|------|
| `fft-digital-signal.md` | **无线信号如何变成数字**：采样（Nyquist）→ DFT 矩阵 → FFT 蝶形 → WiFi/卫星真实系统，含 N=4 完整矩阵算例，数字全部经 numpy 验证 | ✅ |
| `convolution-theorem.md` | **卷积定理**：时域卷积 = 频域相乘——连续/离散推导、循环卷积陷阱、FFT 加速卷积、频域滤波、匹配滤波与 OFDM 均衡，数字全部经 numpy 验证 | ✅ |

## 覆盖内容

- 模拟 → 数字：ADC 采样与量化、Nyquist 采样定理、混叠
- 离散傅里叶变换（DFT）：公式、单位根、**矩阵形式** $X = \mathbf{W}_N x$
- 快速傅里叶变换（FFT）：Cooley–Tukey 奇偶分解、蝶形结构、$O(N^2) \to O(N\log N)$
- 逆变换、Parseval 能量守恒（对账方法）
- **卷积定理**：时域卷积 = 频域相乘；循环卷积陷阱；FFT 加速卷积；频域滤波；匹配滤波与 OFDM 均衡
- 真实系统：WiFi OFDM（IFFT 发射 / FFT 接收）、卫星 DVB-S2 / Starlink / 5G NTN
- 计算机怎么处理：ADC → FFT 硬件/GPU/CPU 库 → 解调

## 核心公式速查

$$
X[k] = \sum_{n=0}^{N-1} x[n]\,e^{-j\frac{2\pi}{N}kn} = \sum_n x[n]\,W_N^{kn}, \qquad X = \mathbf{W}_N x
$$

$$
\text{卷积定理}:\ y=x\ast h \iff Y[k]=X[k]\,H[k]\quad(\text{DFT 对应循环卷积，需补零})
$$

## 怎么自己验证

```python
import numpy as np
np.fft.fft([1, 2, 3, 4])    # → [10, -2+2j, -2, -2-2j]
np.fft.ifft(np.fft.fft(x))  # → 原样还原 x
```
