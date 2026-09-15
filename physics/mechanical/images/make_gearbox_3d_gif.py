# -*- coding: utf-8 -*-
"""3D 版变速箱结构动图（matplotlib mplot3d）。

等距视角剖视：两根平行轴（输入=发动机侧 / 输出=车轮侧）+ 5 对齿轮（同模数，
中心距恒定）+ 滑动结合套选择当前档。齿轮为真实 3D 拉伸体 + 逐面光照着色，
比 2D 平面图形象得多。中文标注（微软雅黑）。
"""
import math
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib.animation import FuncAnimation
from matplotlib import font_manager

FONT_DIR = r'C:\Windows\Fonts'
for n in ('msyh.ttc', 'msyhbd.ttc'):
    p = os.path.join(FONT_DIR, n)
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

# 齿轮（同模数 K，中心距 = K*(n1+n2) 恒定）
K = 0.06
TH = 0.13                  # 齿高
GEARS = [(8, 32, '1档', 20), (13, 27, '2档', 40), (17, 23, '3档', 60),
         (20, 20, '4档', 80), (22, 18, '5档', 100)]
CD = K * (GEARS[0][0] + GEARS[0][1])        # 中心距 = 2.4
XS = [-2.4, -1.2, 0.0, 1.2, 2.4]           # 沿轴的 5 个齿轮位置
ZIN, ZOUT = CD / 2, -CD / 2                # 输入轴 z / 输出轴 z
GTH = 0.42                                 # 齿轮厚度（沿 x）
WENG = 0.14                                # 输入轴角速度 rad/帧

ENG = (0.90, 0.55, 0.15)
DRV = (0.22, 0.46, 0.86)
GREY = (0.80, 0.83, 0.86)
DARK = (0.20, 0.22, 0.25)
RED = (0.79, 0.20, 0.20)
GREEN = (0.25, 0.62, 0.36)
LIGHT = np.array([0.45, 0.35, 1.0]); LIGHT /= np.linalg.norm(LIGHT)


def ratio(k):
    return GEARS[k][1] / GEARS[k][0]


def r1(k):
    return K * GEARS[k][0]


def r2(k):
    return K * GEARS[k][1]


def out_rpm(k):
    return 3000.0 / ratio(k)


def shade_color(base, normal):
    s = max(0.30, normal @ LIGHT) * 0.72 + 0.28
    return (base[0] * s, base[1] * s, base[2] * s)


def gear_outline(r, n, ang):
    m = 2 * n
    yy = np.array([(r + TH if i % 2 == 0 else r) * math.cos(ang + 2 * math.pi * i / m)
                   for i in range(m)])
    zz = np.array([(r + TH if i % 2 == 0 else r) * math.sin(ang + 2 * math.pi * i / m)
                   for i in range(m)])
    return yy, zz


def add_gear(ax, xc, zc, r, n, ang, base, edge=DARK):
    yy, zz = gear_outline(r, n, ang)
    zz = zz + zc
    x0, x1 = xc - GTH / 2, xc + GTH / 2
    faces = []
    faces.append(list(zip(np.full_like(yy, x1), yy, zz)))       # 前端面
    faces.append(list(zip(np.full_like(yy, x0), yy, zz)))       # 后端面
    m = len(yy)
    for i in range(m):
        j = (i + 1) % m
        faces.append([(x0, yy[i], zz[i]), (x1, yy[i], zz[i]),
                      (x1, yy[j], zz[j]), (x0, yy[j], zz[j])])
    cols = []
    for f in faces:
        f = np.array(f)
        nrm = np.cross(f[1] - f[0], f[2] - f[0])
        nv = np.linalg.norm(nrm)
        nrm = nrm / nv if nv else np.array([0, 1.0, 0])
        cols.append(shade_color(base, nrm))
    ax.add_collection3d(Poly3DCollection(faces, facecolors=cols,
                                        edgecolors=edge, linewidths=0.25))


def add_cylinder(ax, x0, x1, zc, r, color, res=16):
    t = np.linspace(0, 2 * np.pi, res)
    X = np.tile(np.linspace(x0, x1, 2).reshape(2, 1), (1, res))
    Y = np.tile(r * np.cos(t).reshape(1, res), (2, 1))
    Z = np.tile((zc + r * np.sin(t)).reshape(1, res), (2, 1))
    ax.plot_surface(X, Y, Z, color=color, shade=True, linewidth=0,
                    antialiased=True, cstride=1, rstride=1)


def add_collar(ax, xc, zc, r_in, r_out, th, color):
    # 结合套：短圆筒（输出轴上滑动）
    add_cylinder(ax, xc - th / 2, xc + th / 2, zc, r_out, color, res=14)
    # 内孔提示：前端面画一个环
    t = np.linspace(0, 2 * math.pi, 24)
    ax.plot(np.full_like(t, xc + th / 2), r_in * np.cos(t), zc + r_in * np.sin(t),
            color=(0.3, 0.3, 0.3), linewidth=1.2)


def add_dog_ring(ax, xc, zc, r, n, ang, x_face, base):
    # 齿轮端面的狗牙小齿（正视环）
    yy, zz = gear_outline(r, n, ang)
    zz = zz + zc
    L = 0.16
    m = len(yy)
    faces = []
    for i in range(m):
        if i % 2 != 0:
            continue
        j = (i + 1) % m
        faces.append([(x_face, yy[i], zz[i]), (x_face + L, yy[i], zz[i]),
                      (x_face + L, yy[j], zz[j]), (x_face, yy[j], zz[j])])
    cols = []
    for f in faces:
        f = np.array(f)
        nrm = np.cross(f[1] - f[0], f[2] - f[0])
        nv = np.linalg.norm(nrm)
        nrm = nrm / nv if nv else np.array([1.0, 0, 0])
        cols.append(shade_color(base, nrm))
    ax.add_collection3d(Poly3DCollection(faces, facecolors=cols,
                                        edgecolors=DARK, linewidths=0.2))


TOTAL = 60
collar_x = XS[0]
out_ang = 0.0


def draw(fr):
    global collar_x, out_ang
    target = (fr // 12) % 5
    collar_x += (XS[target] - collar_x) * 0.35
    gi = min(range(5), key=lambda k: abs(XS[k] - collar_x))
    out_ang += WENG / ratio(gi)

    fig = plt.figure(figsize=(9.2, 5.6), dpi=92)
    ax = fig.add_subplot(111, projection='3d')
    # 两根轴
    add_cylinder(ax, XS[0] - 0.9, XS[-1] + 0.9, ZIN, 0.10, (0.55, 0.57, 0.60))
    add_cylinder(ax, XS[0] - 0.9, XS[-1] + 0.9, ZOUT, 0.10, (0.55, 0.57, 0.60))
    # 5 列齿轮
    for k in range(5):
        n1, n2, lab, speed = GEARS[k]
        active = (k == gi)
        add_gear(ax, XS[k], ZIN, r1(k), n1, math.pi / 2 + WENG * fr,
                 ENG if active else GREY)
        add_gear(ax, XS[k], ZOUT, r2(k), n2,
                 (-math.pi / 2 - math.pi / n2) - (WENG / ratio(k)) * fr,
                 DRV if active else GREY)
        # 狗牙（输出轴齿轮端面，面向结合套）
        add_dog_ring(ax, XS[k], ZOUT, 0.22, 8,
                     (-math.pi / 2 - math.pi / 8) - (WENG / ratio(k)) * fr,
                     XS[k] + GTH / 2, DRV if active else GREY)
        col = ENG if active else (0.55, 0.57, 0.60)
        ax.text(XS[k], 0, ZIN + r1(k) + 0.45, lab, color=col, fontsize=10,
                ha='center', va='center')
        ax.text(XS[k], 0, ZOUT - r2(k) - 0.55, 'i=%.2f' % ratio(k),
                color=(0.45, 0.45, 0.45), fontsize=7.5, ha='center', va='center')
    # 结合套（输出轴上，红色，滑向当前档）
    add_collar(ax, collar_x, ZOUT, 0.10, 0.26, 0.30, RED)
    ax.text(collar_x, 0, ZOUT - 0.50, '结合套', color=RED, fontsize=8.5,
            ha='center', va='center')
    # 轴标注
    ax.text(XS[0] - 1.2, 0, ZIN, '输入轴(发动机)', color=ENG, fontsize=9,
            ha='center', va='center')
    ax.text(XS[-1] + 1.2, 0, ZOUT, '输出轴(车轮)', color=DRV, fontsize=9,
            ha='center', va='center')

    ax.set_xlim(-3.6, 3.6); ax.set_ylim(-2.0, 2.0); ax.set_zlim(-2.0, 2.0)
    try:
        ax.set_box_aspect((7.2, 4, 4))
    except Exception:
        pass
    ax.view_init(elev=20, azim=-58)
    ax.set_axis_off()
    n1, n2, lab, speed = GEARS[gi]
    ax.text2D(0.5, 0.965, '3D 变速箱：发动机保持 ~3000 rpm，结合套选当前档（%s，i=%.2f，轮速 %d rpm，%d km/h）'
              % (lab, ratio(gi), int(out_rpm(gi)), speed),
              transform=fig.transFigure, ha='center', fontsize=11,
              color=(0.25, 0.25, 0.28))
    return fig


def make():
    def gen(fr):
        fig = draw(fr)
        return fig,

    anim = FuncAnimation(plt.figure(), gen, frames=TOTAL, interval=70, blit=False)
    out = os.path.join(OUT_DIR, 'gearbox-3d.gif')
    anim.save(out, writer='pillow', fps=14, savefig_kwargs={'facecolor': 'white'})
    plt.close('all')


if __name__ == '__main__':
    # 先验证单帧
    f = draw(0)
    f.savefig(os.path.join(OUT_DIR, '_proto3d_gb.png'), facecolor='white')
    plt.close('all')
    print('proto frame saved')
