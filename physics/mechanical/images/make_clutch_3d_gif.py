# -*- coding: utf-8 -*-
"""3D 版离合换挡对比动图（matplotlib mplot3d）。

共享单轴场景（沿 x 轴）：
  飞轮(发动机) ──离合器片── 输入轴+结合套(带狗牙) ── 目标齿轮(带狗牙,连车轮)

  不踩离合(nogl)：离合器闭合 → 输入轴被发动机锁在 3000，齿轮 1000
        → 结合套被推向齿轮时，狗牙齿尖撞齿尖 → 火花，永不挂入
  踩离合(yes)：离合器片断开(出现间隙) → 输入轴自由
        → 同步环(锥面)摩擦把结合套转速 3000→1000 与齿轮拉平
        → 狗牙对槽 → 结合套滑入，锁定齿轮到轴 → 平稳

3D 狗牙为真实拉伸块，咬合/打齿一眼可辨；同步环为锥体。中文标注（微软雅黑）。
"""
import math
import io
import os
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from matplotlib import font_manager
from PIL import Image

FONT_DIR = r'C:\Windows\Fonts'
for n in ('msyh.ttc', 'msyhbd.ttc'):
    p = os.path.join(FONT_DIR, n)
    if os.path.exists(p):
        font_manager.fontManager.addfont(p)
plt.rcParams['font.sans-serif'] = ['Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

WENG = 0.24            # 发动机角速度 = 3000 rpm
WGEAR = 0.08           # 目标齿轮角速度 = 1000 rpm
RPMF = 0.00008
DOG_N = 5              # 狗牙数（少而粗，看得清）

ENG = (0.90, 0.55, 0.15)
DRV = (0.22, 0.46, 0.86)
GREY = (0.80, 0.83, 0.86)
DARK = (0.20, 0.22, 0.25)
RED = (0.85, 0.22, 0.20)
GREEN = (0.20, 0.62, 0.34)
YEL = (0.82, 0.66, 0.20)
LIGHT = np.array([0.45, 0.35, 1.0]); LIGHT /= np.linalg.norm(LIGHT)

# 场景几何（x 轴 = 传动轴，z=0）—— 聚焦关键区，放大狗牙
FW_X0, FW_X1, FW_R = -2.85, -2.45, 0.70       # 飞轮
CL_X0, CL_R = -2.20, 0.50                      # 离合器片
SHAFT_R = 0.11
COLLAR_DISC, COLLAR_ENG = 0.0, 0.95            # 结合套：脱开 / 挂入位
COLLAR_ROUT, COLLAR_TH = 0.42, 0.44
GEAR_CX, GEAR_R, GEAR_N, GTH = 1.85, 0.90, 14, 0.44
GEAR_FACE = GEAR_CX - GTH / 2                   # 齿轮左端面 = 1.63
WHEEL_CX, WHEEL_R = 2.62, 0.34
DOG_R, DOG_L, DOG_RW = 0.30, 0.26, 0.11


def rpm(w):
    return int(round(w / RPMF))


def shade(base, nrm):
    s = max(0.30, nrm @ LIGHT) * 0.72 + 0.28
    return (base[0] * s, base[1] * s, base[2] * s)


def _nrm(f):
    f = np.array(f)
    n = np.cross(f[1] - f[0], f[2] - f[0])
    nv = np.linalg.norm(n)
    return n / nv if nv else np.array([1.0, 0, 0])


def add_faces(ax, faces, edge=DARK, lw=0.2):
    cols = [shade((0.6, 0.6, 0.6), _nrm(f)) for f in faces]  # placeholder
    ax.add_collection3d(Poly3DCollection(faces, facecolors=cols,
                                          edgecolors=edge, linewidths=lw))


def add_gear(ax, xc, r, n, ang, base, zc=0.0, th=GTH):
    m = 2 * n
    yy = [(r + 0.13 if i % 2 == 0 else r) * math.cos(ang + 2 * math.pi * i / m)
          for i in range(m)]
    zz = [(r + 0.13 if i % 2 == 0 else r) * math.sin(ang + 2 * math.pi * i / m)
          for i in range(m)]
    yy = np.array(yy); zz = np.array(zz) + zc
    x0, x1 = xc - th / 2, xc + th / 2
    faces = [list(zip(np.full_like(yy, x1), yy, zz)),
             list(zip(np.full_like(yy, x0), yy, zz))]
    mm = len(yy)
    for i in range(mm):
        j = (i + 1) % mm
        faces.append([(x0, yy[i], zz[i]), (x1, yy[i], zz[i]),
                      (x1, yy[j], zz[j]), (x0, yy[j], zz[j])])
    cols = [shade(base, _nrm(f)) for f in faces]
    ax.add_collection3d(Poly3DCollection(faces, facecolors=cols,
                                         edgecolors=DARK, linewidths=0.25))


def add_cylinder(ax, x0, x1, r, base, zc=0.0, res=18):
    t = np.linspace(0, 2 * np.pi, res)
    X = np.tile(np.linspace(x0, x1, 2).reshape(2, 1), (1, res))
    Y = np.tile((r * np.cos(t)).reshape(1, res), (2, 1))
    Z = np.tile((zc + r * np.sin(t)).reshape(1, res), (2, 1))
    ax.plot_surface(X, Y, Z, color=base, shade=True, linewidth=0,
                    antialiased=True, cstride=1, rstride=1)


def add_frustum(ax, x0, x1, r0, r1, base, zc=0.0, res=22, alpha=0.85):
    t = np.linspace(0, 2 * np.pi, res)
    X = np.tile(np.linspace(x0, x1, 2).reshape(2, 1), (1, res))
    R = np.linspace(r0, r1, 2)
    Y = np.array([R[i] * np.cos(t) for i in range(2)])
    Z = np.array([zc + R[i] * np.sin(t) for i in range(2)])
    ax.plot_surface(X, Y, Z, color=base, shade=True, linewidth=0,
                    antialiased=True, cstride=1, rstride=1, alpha=alpha)


def add_dog_teeth(ax, x_face, ang, direction, base, zc=0.0,
                  n=DOG_N, rdog=DOG_R, length=DOG_L, rw=DOG_RW):
    da = 2 * math.pi / n * 0.34
    r_out, r_in = rdog + rw, rdog - rw
    for k in range(n):
        a = ang + 2 * math.pi * k / n
        a0, a1 = a - da, a + da
        def YZ(r, ang):
            return r * math.cos(ang), zc + r * math.sin(ang)
        y1, z1 = YZ(r_out, a0); y2, z2 = YZ(r_out, a1)
        y3, z3 = YZ(r_in, a1); y4, z4 = YZ(r_in, a0)
        x1 = x_face + direction * length
        B = [(x_face, y1, z1), (x_face, y2, z2), (x_face, y3, z3), (x_face, y4, z4)]
        F = [(x1, y1, z1), (x1, y2, z2), (x1, y3, z3), (x1, y4, z4)]
        faces = [B, F,
                 [B[0], B[1], F[1], F[0]],
                 [B[2], B[3], F[3], F[2]],
                 [B[1], B[2], F[2], F[1]],
                 [B[3], B[0], F[0], F[3]]]
        cols = [shade(base, _nrm(f)) for f in faces]
        ax.add_collection3d(Poly3DCollection(faces, facecolors=cols,
                                             edgecolors=DARK, linewidths=0.2))


def sparks3d(ax, cx, fr):
    for i in range(10):
        a = fr * 0.6 + i * 0.63
        el = i * 0.5
        r = 0.08 + i * 0.06
        dy = r * math.cos(a)
        dz = r * math.sin(a) * math.cos(el) + 0.02 * math.sin(el)
        ax.plot([cx, cx + 0.02], [0, dy], [0, dz],
                color=(1.0, 0.72, 0.10), linewidth=1.6)


def draw_frame(fr, mode):
    is_nogl = (mode == 'nogl')
    th_eng = WENG * fr
    th_gear = WGEAR * fr
    if is_nogl:
        gap = 0.0
        omega = WENG
        st = 0.0
    else:
        gap = min(1.0, fr / 5.0) * 0.35
        st = min(1.0, max(0.0, (fr - 6) / 30.0))
        omega = WENG + (WGEAR - WENG) * (0.5 - 0.5 * math.cos(math.pi * st))
    # 结合套累计转角（连续）
    if not hasattr(draw_frame, '_ths') or fr == 0:
        draw_frame._ths = 0.0
    draw_frame._ths += omega
    ths = draw_frame._ths

    if is_nogl:
        p = (fr % 16) / 16.0
        if p < 0.70:
            xc = COLLAR_DISC + (COLLAR_ENG - COLLAR_DISC) * (p / 0.70)
        elif p < 0.85:
            xc = COLLAR_ENG
        else:
            xc = COLLAR_ENG - (COLLAR_ENG - COLLAR_DISC) * ((p - 0.85) / 0.15)
    else:
        xc = COLLAR_DISC + (COLLAR_ENG - COLLAR_DISC) * \
             (1.0 - math.exp(-0.35 * max(0.0, st - 0.85) / 0.15))

    delta = abs((ths - th_gear) / (2 * math.pi / DOG_N)) - 0.5
    phase_ok = delta < 0.18
    near = xc > COLLAR_ENG - 0.20
    fully = xc > COLLAR_ENG - 0.03
    engaged = fully and phase_ok
    clash = (near and not phase_ok) if is_nogl else (fully and not phase_ok)
    sync = engaged or phase_ok

    fig = plt.figure(figsize=(10.5, 5.8), dpi=92)
    fig.subplots_adjust(left=0.0, right=1.0, top=0.93, bottom=0.05)
    ax = fig.add_subplot(111, projection='3d')
    # 输入轴
    add_cylinder(ax, CL_X0 - 0.1, GEAR_FACE - 0.05, SHAFT_R, (0.55, 0.57, 0.60))
    # 飞轮
    add_cylinder(ax, FW_X0, FW_X1, FW_R, ENG)
    ax.text(FW_X0 - 0.3, 0, 0, '飞轮\n发动机\n3000', color=ENG, fontsize=8.5,
            ha='center', va='center')
    # 离合器片
    disk_col = ENG if is_nogl else (GREEN if engaged else (YEL if st > 0.05 else (0.66, 0.68, 0.70)))
    add_cylinder(ax, CL_X0 + gap, CL_X0 + 0.45 + gap, CL_R, disk_col)
    ax.text(CL_X0 + 0.22 + gap, 0, CL_R + 0.35, '离合器片', color=(0.4, 0.4, 0.4),
            fontsize=8.5, ha='center', va='center')
    if gap > 0.02:
        ax.plot([FW_X1, CL_X0 + gap], [0, 0], [0, 0], color=YEL, linewidth=2.5)
        ax.text((FW_X1 + CL_X0 + gap) / 2, 0, 0.5, '断开', color=YEL,
                fontsize=8.5, ha='center', va='center')
    # 目标齿轮（空转，连车轮）
    gcol = GREEN if engaged else (RED if clash else DRV)
    gbody = (0.35, 0.78, 0.45) if engaged else ((0.85, 0.55, 0.50) if clash else GREY)
    add_gear(ax, GEAR_CX, GEAR_R, GEAR_N, th_gear, gbody)
    # 齿轮端面狗牙（面向结合套）
    add_dog_teeth(ax, GEAR_FACE, th_gear, -1, gcol)
    ax.text(GEAR_CX, 0, -GEAR_R - 0.55, '目标齿轮\n1000', color=DRV, fontsize=8.5,
            ha='center', va='center')
    # 车轮
    add_cylinder(ax, WHEEL_CX - 0.18, WHEEL_CX + 0.18, WHEEL_R, DRV)
    ax.text(WHEEL_CX, 0, -WHEEL_R - 0.5, '车轮', color=DRV, fontsize=8.5,
            ha='center', va='center')
    # 结合套
    cbody = (0.85, 0.55, 0.50) if clash else ((0.35, 0.78, 0.45) if engaged else (0.62, 0.64, 0.66))
    cout = RED if clash else (GREEN if sync else (0.45, 0.47, 0.50))
    add_cylinder(ax, xc - COLLAR_TH / 2, xc + COLLAR_TH / 2, COLLAR_ROUT, cbody)
    add_dog_teeth(ax, xc + COLLAR_TH / 2, ths, 1, cout)
    ax.text(xc, 0, COLLAR_ROUT + 0.55, '结合套\n%d' % rpm(omega), color=cout,
            fontsize=8.5, ha='center', va='center')
    # 同步环（踩离合、同步中）
    if not is_nogl and st > 0.03 and not engaged:
        add_frustum(ax, xc + COLLAR_TH / 2 + DOG_L, GEAR_FACE - DOG_L,
                    DOG_R - 0.04, DOG_R + 0.02, YEL, alpha=0.8)
        ax.text((xc + GEAR_CX) / 2, 0, DOG_R + 0.45, '同步环(锥面摩擦)',
                color=YEL, fontsize=8.5, ha='center', va='center')
    # 咬合结果
    cx_contact = (xc + COLLAR_TH / 2 + DOG_L + GEAR_FACE - DOG_L) / 2
    if clash:
        sparks3d(ax, cx_contact, fr)
    # 视角：固定画布，3D 充满
    ax.set_xlim(-3.0, 2.9); ax.set_ylim(-1.25, 1.25); ax.set_zlim(-1.25, 1.25)
    try:
        ax.set_box_aspect((5.9, 2.5, 2.5))
    except Exception:
        pass
    ax.view_init(elev=13, azim=-55)
    ax.set_axis_off()
    ax.set_proj_type('ortho')
    # 2D 覆盖文字
    if is_nogl:
        title = '换挡不踩离合：转速不同步，狗牙打齿'
        tcol = RED
    else:
        title = '换挡踩离合：断开 → 同步环拉平转速 → 结合套滑入'
        tcol = GREEN
    fig.text(0.5, 0.955, title, ha='center', fontsize=14, color=tcol, weight='bold')
    # 状态
    if is_nogl:
        stat = '结合套 3000 ≠ 齿轮 1000 → 牙尖撞牙尖，挂不进'
        scol = RED
    elif clash:
        stat = '仍在打齿：转速还没拉平'
        scol = RED
    elif engaged:
        stat = '已同步：牙对槽，结合套滑入，锁定齿轮到轴'
        scol = GREEN
    elif st > 0.05:
        stat = '同步环摩擦：结合套 3000 → 1000（向齿轮靠拢）'
        scol = YEL
    else:
        stat = '踩下离合：发动机与输入轴断开'
        scol = (0.4, 0.4, 0.4)
    fig.text(0.5, 0.025, stat, ha='center', fontsize=11.5, color=scol, weight='bold')
    # 渲染为 PIL 图像（固定画布，帧尺寸一致）
    buf = io.BytesIO()
    fig.savefig(buf, format='png', facecolor='white')
    plt.close(fig)
    return Image.open(buf).convert('RGB')


def gen(mode, total, fname):
    draw_frame._ths = 0.0
    frames = []
    for fr in range(total):
        if fr == 0:
            draw_frame._ths = 0.0
        frames.append(draw_frame(fr, mode))
    path = os.path.join(OUT_DIR, fname)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=70, loop=0)
    print('saved %s, %d frames' % (path, len(frames)))


if __name__ == '__main__':
    gen('nogl', 54, 'clutch-no3d.gif')
    gen('clutch', 66, 'clutch-yes3d.gif')
