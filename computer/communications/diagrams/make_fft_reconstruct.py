# -*- coding: utf-8 -*-
"""x=[1,2,3,4] 的 DFT：频域分量怎么拼出时域信号。
x=[1,2,3,4], X=fft(x)=[10, -2+2j, -2, -2-2j]
x[n] = (1/4) sum_k X[k] e^{+j2pi kn/4}
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

BLUE, ORANGE, GREEN, PURPLE, GRAY = '#1f77b4', '#ff7f0e', '#2ca02c', '#9467bd', '#555555'
N = 4
x = np.array([1, 2, 3, 4])
X = np.fft.fft(x)                       # [10, -2+2j, -2, -2-2j]
n = np.arange(N)
# 每个频率分量的时域贡献 C_k[n] = (X[k]/N) e^{+j2pi k n / N}
C = np.array([[X[k]/N * np.exp(1j*2*np.pi*k*ni/N) for ni in n] for k in range(N)])
labels = ['k=0 直流', 'k=1 低频', 'k=2 中频', 'k=3 高频(=−k1)']
cols = [GRAY, BLUE, ORANGE, PURPLE]

fig, axs = plt.subplots(2, 2, figsize=(11.5, 7.8))
fig.suptitle('频域分量怎么拼出时域：x=[1,2,3,4]  =  Σ (X[k]/4)·e^{j2πkn/4}', fontsize=15, fontweight='bold')

# ① 时域目标
axs[0,0].bar(n, x, width=0.5, color=BLUE, edgecolor='white')
axs[0,0].set_title('① 时域信号 x[n]（目标）', fontsize=12, pad=8)
axs[0,0].set_xticks(n); axs[0,0].set_ylim(0, 5.2)
for i, v in enumerate(x):
    axs[0,0].text(i, v+0.15, str(v), ha='center', fontsize=10)

# ② 频域 |X[k]|
axs[0,1].bar(n, np.abs(X), width=0.5, color=cols, edgecolor='white')
axs[0,1].set_title('② 频域 |X[k]|（各频率多强）', fontsize=12, pad=8)
axs[0,1].set_xticks(n); axs[0,1].set_xticklabels(['k=0\n直流', 'k=1\n低频', 'k=2\n中频', 'k=3\n高频'], fontsize=9)
for i, v in enumerate(np.abs(X)):
    axs[0,1].text(i, v+0.3, f'{v:.1f}', ha='center', fontsize=10)
axs[0,1].set_ylim(0, 11.5)

# ③ 每个频域分量的时域贡献 C_k[n]（实部）
for k in range(3):
    axs[1,0].plot(n, C[k].real, 'o-', color=cols[k], label=f'{labels[k]} (X[{k}]/4)', linewidth=1.8)
# k=3 与 k=1 实部重合（共轭对），用空心虚线表示
axs[1,0].plot(n, C[3].real, 'o--', color=PURPLE, markerfacecolor='none',
              label=f'{labels[3]} (与 k=1 实部重合)', linewidth=1.8)
axs[1,0].axhline(0, color='black', linewidth=0.8)
axs[1,0].set_title('③ 每个频域分量在时域的贡献 C_k[n]', fontsize=12, pad=8)
axs[1,0].set_xticks(n); axs[1,0].legend(fontsize=7.5); axs[1,0].grid(alpha=0.3)

# ④ 重建 vs 目标
recon = C.sum(axis=0).real
axs[1,1].bar(n-0.15, x, width=0.3, color=BLUE, label='目标 x[n]')
axs[1,1].bar(n+0.15, recon, width=0.3, color=GREEN, label='重建 Σ(X[k]/4)e^{j2πkn/4}')
axs[1,1].set_title('④ 重建 = 目标 √', fontsize=12, pad=8)
axs[1,1].set_xticks(n); axs[1,1].set_ylim(0, 5.2)
axs[1,1].legend(fontsize=9)

plt.tight_layout(rect=[0, 0, 1, 0.95])
out = r'D:\code\AI\computer\communications\diagrams\fft-reconstruct.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
print('saved:', out)
print('C 实部各分量:', np.round(C.real, 3))
print('重建 =', np.round(recon, 3))
