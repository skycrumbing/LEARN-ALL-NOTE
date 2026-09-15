# -*- coding: utf-8 -*-
"""生成 GIF：5 速变速箱物理结构 —— 发动机保持 ~3000 rpm，换挡选择不同传动比 → 不同车速

上半区：输入轴(发动机) + 5 对齿轮（中心距恒定，同模数 → 可正确啮合）
        + 输出轴(车轮) + 滑动结合套(拨叉/狗牙离合) 选择当前档位
下半区：转速 / 扭矩 / 车速对照，小车随档位加速

所有齿轮同模数（r = K·齿数），故 5 对齿轮中心距恒定 = K·(n1+n2)，能并排装在两根平行轴上。
标注用 ASCII（同 make_gear_gif.py），中文留给 Markdown。
"""
import math
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 760, 420
TOTAL = 60          # 帧数
DUR = 60            # 每帧毫秒 → 循环约 3.6s

BG = (255, 255, 255)


def GR(g):
    return (g, g, g)


def F(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


F10, F11, F12, F13 = F(10), F(11), F(12), F(13)


def text(d, x, y, s, fill, font=F11, anchor=None):
    if anchor:
        d.text((x, y), s, fill=fill, font=font, anchor=anchor)
    else:
        d.text((x, y), s, fill=fill, font=font)


K = 1.8               # 每齿半径系数（所有齿轮同模数 → 线齿距相同 → 可正确啮合）
TH = 6                # 齿高
YIN, YOUT = 100, 172  # 输入轴 / 输出轴 y（中心距 = K*(n1+n2) = 72，恒定）
XS = [110, 230, 350, 470, 590]

# (n1 主动齿数, n2 从动齿数, 档名, 车速 km/h)  —— 中心距 = K*(n1+n2) = 72 全部恒定
GEARS = [
    (8, 32, '1st', 20),
    (13, 27, '2nd', 40),
    (17, 23, '3rd', 60),
    (20, 20, '4th', 80),
    (22, 18, '5th', 100),
]

ENG = (232, 89, 12)       # 主动/发动机 橙
DRV = (25, 113, 194)      # 从动/车轮 蓝
GREY = (214, 218, 222)
DARK = (92, 100, 108)
RED = (201, 42, 42)
WENG = 0.262              # 主动轴角速度 rad/帧（发动机 ~1 圈/24 帧）


def ratio(k):
    return GEARS[k][1] / GEARS[k][0]


def r1(k):
    return K * GEARS[k][0]


def r2(k):
    return K * GEARS[k][1]


def out_rpm(k):
    return 3000.0 / ratio(k)


def gear_verts(cx, cy, r, n, angle):
    pts = []
    for i in range(2 * n):
        a = angle + math.pi * i / n
        rr = r + TH if i % 2 == 0 else r
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts


def draw_gear(d, cx, cy, r, n, angle, fill, outline):
    d.polygon(gear_verts(cx, cy, r, n, angle), fill=fill, outline=outline)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=outline)
    d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(73, 80, 87))


# 垂直啮合相位：主动齿尖朝下(π/2)插入从动齿隙(从动齿隙朝上 -π/2)
def a_driver(k, fr):
    return math.pi / 2 + WENG * fr


def a_driven(k, fr):
    return (-math.pi / 2 - math.pi / GEARS[k][1]) - (WENG / ratio(k)) * fr


def draw_disk(d, cx, cy, r, angle, fill):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=DARK, width=2)
    d.line([cx, cy, cx + r * math.cos(angle), cy + r * math.sin(angle)],
           fill=(255, 255, 255), width=2)
    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(255, 255, 255))


def draw_car(d, cx, cy):
    w, h = 28, 10
    d.rectangle([cx - w // 2, cy - h, cx + w // 2, cy], fill=(70, 130, 190), outline=DARK)
    d.rectangle([cx - w // 2 + 6, cy - h - 5, cx + w // 2 - 6, cy - h],
                fill=(70, 130, 190), outline=DARK)
    for wx in (cx - w // 2 + 6, cx + w // 2 - 6):
        d.ellipse([wx - 4, cy - 2, wx + 4, cy + 5], fill=(45, 49, 53), outline=DARK)


state = {'collar': XS[0], 'out_ang': 0.0, 'dist': 0.0}
frames = []
for fr in range(TOTAL):
    target = (fr // 12) % 5                       # 目标档（每 12 帧推进一档）
    state['collar'] += (XS[target] - state['collar']) * 0.35   # 结合套缓动滑向目标
    # 实际啮合档 = 结合套当前最接近的那一列 → 颜色/转速/车速都跟着结合套走，始终一致
    gi = min(range(5), key=lambda k: abs(XS[k] - state['collar']))
    state['out_ang'] += WENG / ratio(gi)
    state['dist'] += GEARS[gi][3] * 0.6

    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)

    text(d, W // 2, 6, '5-speed gearbox: engine holds ~3000 rpm, gear selects the ratio',
         GR(70), F13, 'ma')

    # 两根轴
    d.line([45, YIN, 705, YIN], fill=DARK, width=4)
    d.line([45, YOUT, 705, YOUT], fill=DARK, width=4)
    text(d, 55, 80, 'ENGINE', GR(90), F10, 'ma')
    text(d, 695, 198, 'WHEELS', GR(90), F10, 'ma')

    # 发动机盘（恒定转速） + 车轮盘（随档位变）
    draw_disk(d, 55, YIN, 15, WENG * fr, ENG)
    draw_disk(d, 695, YOUT, 15, state['out_ang'], DRV)

    # 5 列齿轮
    for k in range(5):
        n1, n2, lab, speed = GEARS[k]
        cx = XS[k]
        active = (k == gi)
        draw_gear(d, cx, YIN, r1(k), n1, a_driver(k, fr),
                  ENG if active else GREY,
                  (180, 60, 0) if active else (165, 169, 173))
        draw_gear(d, cx, YOUT, r2(k), n2, a_driven(k, fr),
                  DRV if active else GREY,
                  (15, 80, 140) if active else (165, 169, 173))
        text(d, cx, YIN - r1(k) - TH - 9, lab,
             ENG if active else GR(115), F12, 'ma')
        text(d, cx, YOUT + r2(k) + TH + 8, 'i=%.2f' % ratio(k), GR(130), F10, 'ma')

    # 滑动结合套（拨叉/狗牙离合）—— 锁定当前档的从动齿轮到输出轴
    ccx = state['collar']
    d.rectangle([ccx - 18, YOUT - 12, ccx + 18, YOUT + 12], outline=RED, width=3)

    # ---- 下半区：对照表 ----
    n1, n2, lab, speed = GEARS[gi]
    info = '%s    ratio %.2f    engine 3000 rpm    wheels %d rpm    car %d km/h' % (
        lab, ratio(gi), int(out_rpm(gi)), speed)
    text(d, W // 2, 260, info, GR(55), F13, 'ma')

    # 车速条
    sy = 284
    d.rectangle([60, sy, 700, sy + 13], outline=(175, 179, 183), width=2)
    sw = 640 * speed / 120.0
    d.rectangle([62, sy + 2, 62 + sw, sy + 11], fill=ENG)
    for v, l in [(0, '0'), (40, '40'), (80, '80'), (120, '120')]:
        tx2 = 60 + 640 * v / 120.0
        d.line([tx2, sy - 2, tx2, sy + 15], fill=(205, 209, 213))
        text(d, tx2, sy + 16, l, GR(130), F10, 'ma')
    text(d, 56, sy + 1, 'km/h', GR(130), F10, 'ra')

    # 道路 + 小车（累计位移，档位高 → 跑得快）
    ry = 332
    d.line([60, ry, 700, ry], fill=(180, 184, 188), width=2)
    carx = 78 + (state['dist'] % 622)
    draw_car(d, carx, ry - 2)

    # 扭矩条（输出扭矩 = 发动机扭矩 × 传动比）
    ty = 356
    d.rectangle([60, ty, 700, ty + 13], outline=(175, 179, 183), width=2)
    tw = 640 * ratio(gi) / 5.0
    d.rectangle([62, ty + 2, 62 + tw, ty + 11], fill=RED)
    text(d, 56, ty + 1, 'T out', GR(130), F10, 'ra')
    text(d, 706, ty + 1, 'x%.1f' % ratio(gi), RED, F10, 'la')

    text(d, W // 2, 390,
         'low gear: big ratio -> slow wheels + big torque | high gear: small ratio -> fast wheels + low torque',
         GR(110), F11, 'ma')

    frames.append(img)

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gearbox-structure.gif')
frames[0].save(out, save_all=True, append_images=frames[1:], duration=DUR, loop=0)
print('saved %s, %d frames, %dx%d' % (out, len(frames), W, H))
