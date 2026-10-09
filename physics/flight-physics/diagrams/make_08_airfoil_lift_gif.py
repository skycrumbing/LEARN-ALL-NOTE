# -*- coding: utf-8 -*-
"""
生成动图：翼型如何产生升力（08-airfoil-lift.gif）

展示内容（与 flight-principles.md 第 2.1~2.3 节一致）：
  1. 气流从左向右流过翼型
  2. 上表面空气被"压"着走更长的弯曲路径 → 加速 → 低压区
  3. 下表面较平坦 → 流速慢 → 高压区
  4. 上下压差 → 升力 L 逐渐产生
  5. 后缘气流向下偏转（下洗，牛顿第三定律视角）

依赖：matplotlib, Pillow
运行：python make_08_airfoil_lift_gif.py [--preview]
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import PathPatch, FancyBboxPatch, Polygon
from matplotlib.path import Path as MPath
from matplotlib import animation
from matplotlib.animation import PillowWriter
from PIL import Image, ImageSequence

# ----------------------------------------------------------------------
# 颜色（与现有 SVG 风格统一）
# ----------------------------------------------------------------------
BG        = "#FAFBFC"
AIRFOIL   = "#4A90D9"
AIRFOIL_E = "#2C5F8A"
RED       = "#E74C3C"   # 上表面（快）
GREEN     = "#2ECC71"   # 下表面（慢）
LOWP      = "#5DADE2"   # 低压区
HIGHP     = "#52BE80"   # 高压区
ORANGE    = "#E67E22"   # 升力箭头
DARK      = "#1a1a2e"
GREY      = "#8d99ae"
DARKGREY  = "#57606f"

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Arial"]
plt.rcParams["axes.unicode_minus"] = False

# ----------------------------------------------------------------------
# 翼型几何（沿用 08-airfoil-section.svg 的控制点，y 翻转使"上"为正）
#   up: 前缘(-180,0) → 上表面 → 后缘(180,0)
#   lo: 后缘(180,0) → 下表面 → 前缘(-180,0)
# 首尾相接即成闭合回路
# ----------------------------------------------------------------------
def bez(P0, C1, C2, P3, n=90):
    t = np.linspace(0, 1, n)
    P0, C1, C2, P3 = (np.array(p, float) for p in (P0, C1, C2, P3))
    return ((1 - t)[:, None] ** 3 * P0
            + 3 * (1 - t)[:, None] ** 2 * t[:, None] * C1
            + 3 * (1 - t)[:, None] * t[:, None] ** 2 * C2
            + t[:, None] ** 3 * P3)

up = np.vstack([bez((-180, 0), (-180, 42), (-90, 78), (0, 68)),
                bez((0, 68), (90, 58), (150, 35), (180, 0))[1:]])
lo = np.vstack([bez((180, 0), (150, -20), (90, -30), (0, -28)),
                bez((0, -28), (-90, -26), (-180, -16), (-180, 0))[1:]])

airfoil_path = MPath(np.vstack([up, lo, up[:1]]),
                     [MPath.MOVETO] + [MPath.LINETO] * (len(up) + len(lo)))

# ----------------------------------------------------------------------
# 流线：上表面偏移（红/快）、下表面偏移（绿/慢）
#
#   y(x) = offset + w(x)·s(x)·(1−v(x)) + v(x)·DOWNWASH·(x−180)
#
#   s(x)   翼型表面高度（翼型范围外外推为 0）
#   w(x)   入口平滑开关 0→1：自由流水平段 → 贴表面段
#   v(x)   出口平滑开关 0→1：贴表面段 → 带下洗的自由流段
# 用 smoothstep 做开关，保证流线处处 C1 连续（前缘/后缘无折角）
# ----------------------------------------------------------------------
DOWNWASH = 0.24
X_IN, X_OUT = -258, 250
X_LE, X_TE = -180, 180
X_BEND_IN, X_BEND_OUT = -118, 162


def smoothstep(a, b, x):
    u = np.clip((x - a) / (b - a), 0, 1)
    return u * u * (3 - 2 * u)


def surface_of(boundary, x):
    return np.interp(x, boundary[:, 0], boundary[:, 1], left=0.0, right=0.0)


def make_streamline(boundary, offset):
    xs = np.concatenate([np.linspace(X_IN, X_LE, 30),
                         np.linspace(X_LE, X_OUT, 130)])
    s = surface_of(boundary, xs)
    w = smoothstep(X_LE, X_BEND_IN, xs)
    v = smoothstep(X_BEND_OUT, X_OUT, xs)
    ys = offset + w * s * (1 - v) + v * DOWNWASH * (xs - X_TE)
    return np.stack([xs, ys], axis=1)


def band(boundary, dy):
    """表面与其偏移线围成的压差带（仅在翼型范围内）"""
    outer = np.column_stack([boundary[:, 0], boundary[:, 1] + dy])
    return np.vstack([boundary, outer[::-1]])


TOP_OFF, BOT_OFF = [14, 34, 56], [-14, -34, -56]
NP = 4                                    # 每条流线上的粒子数
TOP_CYC, BOT_CYC = 2, 1                  # 每循环跨越的间距数（上快下慢）

streams = ([("top", make_streamline(up, d)) for d in TOP_OFF]
           + [("bot", make_streamline(lo, d)) for d in BOT_OFF])

# ----------------------------------------------------------------------
# 图
# ----------------------------------------------------------------------
fig, ax = plt.subplots(figsize=(11, 5.9), dpi=112)
fig.patch.set_facecolor(BG)
ax.set_facecolor(BG)
ax.set_aspect("equal")
ax.set_xlim(-258, 302)
ax.set_ylim(-162, 202)
ax.axis("off")


def rbox(x0, y0, w, h, border):
    p = FancyBboxPatch((x0, y0), w, h,
                       boxstyle="round,pad=0,rounding_size=7",
                       facecolor="white", edgecolor=border,
                       lw=1.6, zorder=8)
    ax.add_patch(p)
    return p


# ---- 压差带：低压在上（蓝）、高压在下（绿）----
ax.add_patch(plt.Polygon(band(up, 62), closed=True, facecolor=LOWP,
                         edgecolor="none", alpha=0.15, zorder=1))
ax.add_patch(plt.Polygon(band(lo, -62), closed=True, facecolor=HIGHP,
                         edgecolor="none", alpha=0.12, zorder=1))

# ---- 流线（静态虚线）+ 粒子 ----
particle_artists = []
for kind, stream in streams:
    color = RED if kind == "top" else GREEN
    ax.plot(stream[:, 0], stream[:, 1], color=color, lw=1.4,
            ls=(0, (5, 3)) if kind == "top" else (0, (3, 3)),
            alpha=0.55, zorder=2)
    d = np.diff(stream, axis=0)
    seg = np.hypot(d[:, 0], d[:, 1])
    clen = np.concatenate([[0], np.cumsum(seg)])
    L = clen[-1]
    cyc = TOP_CYC if kind == "top" else BOT_CYC
    s0 = np.linspace(0, L, NP, endpoint=False)
    art, = ax.plot([], [], "o", ms=7.5, color=color, alpha=0.95, zorder=6)
    particle_artists.append((art, stream, clen, s0, L, cyc))

# ---- 翼型 ----
ax.add_patch(PathPatch(airfoil_path, facecolor=AIRFOIL, edgecolor=AIRFOIL_E,
                       lw=2.6, zorder=5))

# ---- 升力箭头（动画：每循环生长一次）----
LIFT_BASE, LIFT_TIP = -22, 124
HEAD_L, HEAD_W = 26.0, 17.0          # 箭头长度 / 半宽
lift_shaft, = ax.plot([], [], color=ORANGE, lw=6, solid_capstyle="round",
                      zorder=7)
lift_head = Polygon(np.zeros((3, 2)), closed=True, facecolor=ORANGE,
                    edgecolor="none", zorder=7)
ax.add_patch(lift_head)


def set_arrow(x, y0, y1):
    """按 (x, y0) → (x, y1) 重绘箭头（杆 + 三角头）"""
    tip = max(y1, y0 + HEAD_L + 1)
    lift_shaft.set_data([x, x], [y0, tip - HEAD_L])
    lift_head.set_xy([[x - HEAD_W, tip - HEAD_L], [x + HEAD_W, tip - HEAD_L],
                      [x, tip]])


set_arrow(0, LIFT_BASE, LIFT_BASE + HEAD_L + 1)
lift_shaft.set_alpha(0.0)
lift_head.set_alpha(0.0)
lift_txt = ax.text(0, 136, "升力 L", ha="center", va="bottom", fontsize=16,
                   fontweight="bold", color=ORANGE, zorder=7, alpha=0.0)

# ---- 标注框 ----
rbox(-250, 120, 222, 54, RED)
ax.text(-240, 159, "上表面：曲率大", fontsize=12.5, fontweight="bold",
        color=RED, va="center", zorder=9)
ax.text(-240, 138, "空气被加速 → 压强低", fontsize=11.5, color=RED,
        va="center", zorder=9)

rbox(-250, -112, 222, 54, GREEN)
ax.text(-240, -73, "下表面：较平坦", fontsize=12.5, fontweight="bold",
        color=GREEN, va="center", zorder=9)
ax.text(-240, -94, "流速慢 → 压强高", fontsize=11.5, color=GREEN,
        va="center", zorder=9)

rbox(196, 120, 102, 54, GREY)
ax.text(247, 159, "后缘气流", fontsize=12, fontweight="bold", color=DARKGREY,
        ha="center", va="center", zorder=9)
ax.text(247, 138, "向下偏转（下洗）", fontsize=10.5, color=DARKGREY,
        ha="center", va="center", zorder=9)

# ---- 标题 + 底部说明 ----
ax.text(20, 190, "翼型如何产生升力（Airfoil Lift Generation）",
        ha="center", va="center", fontsize=17.5, fontweight="bold",
        color=DARK, zorder=9)

ax.add_patch(plt.Rectangle((-250, -158), 548, 34, facecolor="#EEF2F7",
                           edgecolor="none", zorder=1))
ax.text(24, -141, "上表面气流快 → 压强低；下表面气流慢 → 压强高 → 上下压差产生升力",
        ha="center", va="center", fontsize=12, color=DARK, zorder=2)

# ----------------------------------------------------------------------
# 动画
# ----------------------------------------------------------------------
T = 8.0          # 单循环时长（秒）
NFRAME = 48


def pos_at(s, stream, clen, L, t, cyc):
    """等弧长插值；每循环恰好跨越 cyc 个间距 → 循环首尾完全重合"""
    trav = cyc * (L / NP) * (t / T)
    sp = (s + trav) % L
    idx = np.clip(np.searchsorted(clen, sp, side="right") - 1, 0, len(clen) - 2)
    f = (sp - clen[idx]) / np.maximum(clen[idx + 1] - clen[idx], 1e-9)
    return stream[idx] * (1 - f[:, None]) + stream[idx + 1] * f[:, None]


def ramp(t, a, b):
    return float(np.clip((t - a) / (b - a), 0, 1))


def animate(i):
    # 最后一帧取 t=T（= 整周期），首帧取 t=T/NFRAME，衔接处恰好差一帧 → 无缝
    t = (i + 1) / NFRAME * T
    for art, stream, clen, s0, L, cyc in particle_artists:
        p = pos_at(s0, stream, clen, L, t, cyc)
        art.set_data(p[:, 0], p[:, 1])
    # 升力：t∈[0.18,0.50] 生长并显现，t∈[0.86,1.0] 消退
    k = ramp(t / T, 0.18, 0.50) * (1 - ramp(t / T, 0.86, 1.0))
    set_arrow(0, LIFT_BASE, LIFT_BASE + (LIFT_TIP - LIFT_BASE) * k)
    lift_shaft.set_alpha(k)
    lift_head.set_alpha(k)
    lift_txt.set_alpha(k)
    return [a[0] for a in particle_artists] + [lift_shaft, lift_head, lift_txt]


anim = animation.FuncAnimation(fig, animate, frames=NFRAME,
                               interval=T / NFRAME * 1000, blit=False)


def preview(frac=0.55, path="_preview_08_airfoil_lift.png"):
    animate(int(round(frac * NFRAME)) - 1)
    fig.savefig(path, facecolor=BG, dpi=112)
    print("preview saved:", path)


def save_gif(path="08-airfoil-lift.gif"):
    anim.save(path, writer=PillowWriter(fps=NFRAME / T))
    # 确保无限循环播放
    im = Image.open(path)
    frames = [f.copy() for f in ImageSequence.Iterator(im)]
    frames[0].save(path, save_all=True, append_images=frames[1:],
                   loop=0, duration=int(1000 * T / NFRAME))
    print("saved:", path)


if __name__ == "__main__":
    if "--preview" in sys.argv:
        preview()
    else:
        save_gif()
