# -*- coding: utf-8 -*-
"""回声系统的"小脉冲 + 卷积"示意图。
y[n] = x[n] + x[n-1],h = [1,1](立即 + 延迟1秒)。
x = [1,2,0.5] @ n=0,1,2  =>  y = [1,3,2.5,0.5] @ n=0..3
"""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

BLUE, ORANGE, GREEN, PURPLE = '#1f77b4', '#ff7f0e', '#2ca02c', '#9467bd'
X = np.arange(0, 5)

def spikes(ax, positions, heights, color, ymax, labels=None, title=None):
    ax.bar(positions, heights, width=0.55, color=color, edgecolor='white', linewidth=0.6, zorder=3)
    ax.set_xlim(-0.6, 4.6)
    ax.set_ylim(0, ymax)
    ax.set_xticks(X); ax.set_xticklabels([str(i) for i in X])
    ax.grid(axis='y', color='#dddddd', linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    if labels:
        for p, hgt, lab in zip(positions, heights, labels):
            ax.text(p, hgt + ymax*0.06, lab, ha='center', va='bottom', fontsize=9)
    if title:
        ax.set_title(title, fontsize=12, pad=8)

fig, axs = plt.subplots(2, 2, figsize=(11.5, 7.8))
fig.suptitle('小脉冲 + 卷积:回声系统  y[n] = x[n] + x[n−1]', fontsize=15, fontweight='bold')

# ① 输入
spikes(axs[0,0], [0,1,2], [1,2,0.5], BLUE, 2.6,
       labels=['1', '2', '0.5'],
       title='① 输入 = 一串小脉冲 x[n]')
axs[0,0].text(0.64, 0.05, '把信号切成竖直细条,\n每一条就是一个小脉冲', transform=axs[0,0].transAxes,
              fontsize=9, color='#555555', va='bottom', ha='left')

# ② 冲激响应
spikes(axs[0,1], [0,1], [1,1], ORANGE, 2.6,
       labels=['立即', '延迟 1 秒'],
       title='② 冲激响应 h[n](喂一个尖峰的输出)')

# ③ 每个脉冲按 h 响应(拆开看)
ax = axs[1,0]
base = [0.0, 1.6, 3.2]
rows = [
    ('脉冲 @0(高 1)',  [0, 1], [1, 1], BLUE),
    ('脉冲 @1(高 2)',  [1, 2], [2, 2], ORANGE),
    ('脉冲 @2(高 0.5)',[2, 3], [0.5, 0.5], GREEN),
]
for (lab, pos, hgt, color), b in zip(rows, base):
    ax.bar(pos, hgt, width=0.55, bottom=b, color=color, edgecolor='white', linewidth=0.6, zorder=3)
ax.set_xlim(-0.6, 4.6); ax.set_ylim(0, 4.4)
ax.set_xticks(X); ax.set_xticklabels([str(i) for i in X])
ax.set_yticks([b + 0.5 for b in base]); ax.set_yticklabels([r[0] for r in rows], fontsize=9)
ax.grid(axis='y', color='#dddddd', linewidth=0.7, zorder=0); ax.set_axisbelow(True)
ax.set_title('③ 每个小脉冲按 h 的形状响应(拆开看)', fontsize=12, pad=8)
ax.text(3.3, 4.1, '每个脉冲都\n复制一份 h,\n高度 × 脉冲高度', fontsize=9, color='#555555', va='top')

# ④ 输出 = 叠加
spikes(axs[1,1], [0,1,2,3], [1,3,2.5,0.5], PURPLE, 3.8,
       labels=['1', '3', '2.5', '0.5'],
       title='④ 全部叠加 = 输出 y[n]')
axs[1,1].text(0.02, 0.97, 'y[1] = 2+1 = 3(两个脉冲的回声撞在一起)', transform=axs[1,1].transAxes,
              fontsize=9, color='#555555', va='top')

plt.tight_layout(rect=[0, 0, 1, 0.95])
out = r'D:\code\AI\computer\communications\diagrams\impulse-convolution.png'
plt.savefig(out, dpi=150, bbox_inches='tight', facecolor='white')
print('saved:', out)
