# -*- coding: utf-8 -*-
"""生成两张对比 GIF：换挡「不踩离合」vs「踩离合」。

v2 改进（回应"不够清晰"）：
  - 全中文标注（微软雅黑），飞轮/离合器片/结合套/狗牙/目标齿轮/输出轴/车轮都标清楚
  - 主图：动力流 飞轮→离合器片→输入轴+结合套→目标齿轮→输出轴→车轮
  - 右下「狗牙端面特写」圆：正视图放大结合套(外环狗牙)与目标齿轮(内盘狗牙)的咬合
        牙对槽 = 平稳挂入(绿) / 牙对牙 = 打齿(红+火花) —— 一眼看懂怎么耦合
  - 转速差指示：结合套 rpm vs 齿轮 rpm，中间 ≠(不同步) / =(已同步)
"""
import math
import os
from PIL import Image, ImageDraw, ImageFont

W, H = 760, 484
DUR = 60
BG = (255, 255, 255)
OUT_DIR = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = r'C:\Windows\Fonts'


def GR(g):
    return (g, g, g)


def C(size, bold=False):
    p = os.path.join(FONT_DIR, 'msyhbd.ttc' if bold else 'msyh.ttc')
    try:
        return ImageFont.truetype(p, size)
    except Exception:
        try:
            return ImageFont.truetype('arial.ttf', size)
        except Exception:
            return ImageFont.load_default()


C10, C11, C12, C13, C14 = C(10), C(11), C(12), C(13), C(14)
CB13, CB14, CB16, CB20 = C(13, True), C(14, True), C(16, True), C(20, True)


def text(d, x, y, s, fill, font=C11, anchor=None):
    if anchor:
        d.text((x, y), s, fill=fill, font=font, anchor=anchor)
    else:
        d.text((x, y), s, fill=fill, font=font)


ENG = (232, 89, 12)       # 发动机/飞轮/结合套 橙
DRV = (25, 113, 194)      # 齿轮/车轮 蓝
DARK = (92, 100, 108)
GREY = (214, 218, 222)
RED = (201, 42, 42)
GREEN = (40, 150, 80)
YEL = (198, 148, 26)
WENG = 0.24               # 发动机角速度 (=3000 rpm)
WGEAR = 0.08             # 目标齿轮角速度 (=1000 rpm)
RPMF = 0.00008
DOG_N = 8

# 主图布局
AXIS_Y = 132
FW_CX, FW_R = 58, 30             # 飞轮
CL_BASE = 116                     # 离合器片基础 x
CL_R = 24
GEAR_CX, GEAR_R = 432, 34         # 目标齿轮
WHEEL_CX, WHEEL_R = 720, 16       # 车轮
COLLAR_X0, COLLAR_X1 = 224, 372   # 结合套：脱开 / 推到咬合位
# 特写圆（狗牙端面）
ZC_CX, ZC_CY, ZC_R = 592, 352, 90


def draw_disk(d, cx, cy, r, angle, fill, w=2):
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill, outline=DARK, width=w)
    d.line([cx, cy, cx + r * math.cos(angle), cy + r * math.sin(angle)],
           fill=(255, 255, 255), width=2)
    d.ellipse([cx - 2, cy - 2, cx + 2, cy + 2], fill=(255, 255, 255))


def dog_face(d, cx, cy, n, angle, r0, r1, color, outline, width=1):
    """扇形狗牙：从半径 r0 到 r1，角宽半齿距"""
    dth = (2 * math.pi / n) * 0.5
    for k in range(n):
        a = angle + 2 * math.pi * k / n
        a0, a1 = a - dth / 2, a + dth / 2
        pts = [(cx + r0 * math.cos(a0), cy + r0 * math.sin(a0)),
               (cx + r1 * math.cos(a0), cy + r1 * math.sin(a0)),
               (cx + r1 * math.cos(a1), cy + r1 * math.sin(a1)),
               (cx + r0 * math.cos(a1), cy + r0 * math.sin(a1))]
        d.polygon(pts, fill=color, outline=outline, width=width)


def draw_car(d, cx, cy):
    w, h = 30, 11
    d.rectangle([cx - w // 2, cy - h, cx + w // 2, cy], fill=(70, 130, 190), outline=DARK)
    d.rectangle([cx - w // 2 + 6, cy - h - 6, cx + w // 2 - 6, cy - h],
                fill=(70, 130, 190), outline=DARK)
    for wx in (cx - w // 2 + 6, cx + w // 2 - 6):
        d.ellipse([wx - 4, cy - 2, wx + 4, cy + 5], fill=(45, 49, 53), outline=DARK)


def sparks(d, cx, cy, fr):
    for i in range(8):
        a = fr * 0.6 + i * 0.78
        r = 8 + i * 3
        d.line([cx, cy, cx + r * math.cos(a), cy + r * math.sin(a)],
               fill=(255, 180, 0), width=2)
    d.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(255, 96, 0))


def rpm(w):
    return int(round(w / RPMF))


def main_diagram(d, fr, gap, omega, ths, th_eng, th_gear, x, clash, engaged, sync, is_nogl):
    # 输入轴 + 输出轴
    d.line([CL_BASE, AXIS_Y, WHEEL_CX, AXIS_Y], fill=DARK, width=4)
    # 飞轮
    draw_disk(d, FW_CX, AXIS_Y, FW_R, th_eng, ENG)
    text(d, FW_CX, AXIS_Y + FW_R + 8, '飞轮', GR(70), C11, 'ma')
    text(d, FW_CX, AXIS_Y + FW_R + 22, '3000', ENG, C11, 'ma')
    # 离合器片
    cdx = CL_BASE + gap
    disk_col = ENG if is_nogl else (GREEN if engaged else (YEL if st_val > 0.05 else (176, 182, 188)))
    draw_disk(d, cdx, AXIS_Y, CL_R, ths, disk_col)
    text(d, CL_BASE + 6, AXIS_Y - CL_R - 18, '离合器片', GR(70), C11)
    if gap > 0:
        d.line([CL_BASE, AXIS_Y + 0, cdx - CL_R, AXIS_Y + 0], fill=YEL, width=3)
        text(d, (CL_BASE + cdx) / 2, AXIS_Y - 10, '断开', YEL, C10, 'ma')
    # 目标齿轮（空转，连输出轴）
    gbody = (206, 228, 212) if engaged else GREY
    gout = GREEN if engaged else (165, 169, 173)
    d.ellipse([GEAR_CX - GEAR_R, AXIS_Y - GEAR_R, GEAR_CX + GEAR_R, AXIS_Y + GEAR_R],
              fill=gbody, outline=gout, width=3)
    d.ellipse([GEAR_CX - 5, AXIS_Y - 5, GEAR_CX + 5, AXIS_Y + 5], fill=(73, 80, 87))
    # 齿轮旋转标记
    d.line([GEAR_CX, AXIS_Y, GEAR_CX + (GEAR_R - 6) * math.cos(th_gear),
            AXIS_Y + (GEAR_R - 6) * math.sin(th_gear)], fill=(255, 255, 255), width=2)
    text(d, GEAR_CX, AXIS_Y + GEAR_R + 8, '目标齿轮', GR(70), C11, 'ma')
    text(d, GEAR_CX, AXIS_Y + GEAR_R + 22, '1000', DRV, C11, 'ma')
    # 车轮
    draw_disk(d, WHEEL_CX, AXIS_Y, WHEEL_R, th_gear, DRV)
    text(d, WHEEL_CX, AXIS_Y + WHEEL_R + 8, '车轮', GR(70), C11, 'ma')
    # 结合套（带狗牙标记，滑动）
    cbody = (232, 196, 196) if clash else ((206, 228, 212) if engaged else (228, 232, 236))
    cout = RED if clash else (GREEN if sync else (150, 156, 162))
    d.rectangle([x - 22, AXIS_Y - 16, x + 22, AXIS_Y + 16], fill=cbody, outline=cout, width=3)
    d.ellipse([x - 5, AXIS_Y - 5, x + 5, AXIS_Y + 5], fill=(110, 118, 126))
    # 结合套上的小狗牙示意（侧视，朝右几根）
    for k in range(3):
        yy = AXIS_Y - 9 + k * 9
        d.rectangle([x + 18, yy - 2, x + 26, yy + 2], fill=cout, outline=DARK)
    text(d, x, AXIS_Y - 30, '结合套', GR(60), C11, 'ma')
    text(d, x, AXIS_Y + 30, '%d' % rpm(omega), cout, C11, 'ma')
    # 换挡力箭头
    if x > COLLAR_X0 + 8:
        ax = x - 30
        d.line([ax, AXIS_Y - 36, ax - 16, AXIS_Y - 36], fill=cout, width=2)
        d.polygon([(ax - 16, AXIS_Y - 36), (ax - 11, AXIS_Y - 39), (ax - 11, AXIS_Y - 33)],
                  fill=cout)
        text(d, ax - 8, AXIS_Y - 50, '换挡', GR(120), C10, 'ma')
    # 转速差 ≠ / =
    midx = (x + GEAR_CX - GEAR_R) / 2
    sym, symcol = ('≠', RED) if (not sync and not engaged) else (('≈', YEL) if not engaged else ('=', GREEN))
    text(d, midx, AXIS_Y - 30, sym, symcol, CB20, 'ma')


def zoom(d, fr, ths, th_gear, clash, engaged, sync):
    # 圆框
    d.ellipse([ZC_CX - ZC_R, ZC_CY - ZC_R, ZC_CX + ZC_R, ZC_CY + ZC_R],
              outline=(190, 194, 198), width=2)
    text(d, ZC_CX, ZC_CY - ZC_R - 14, '狗牙端面特写（结合套 ↔ 目标齿轮）', GR(70), CB13, 'ma')
    # 外环体（结合套）
    d.ellipse([ZC_CX - 80, ZC_CY - 80, ZC_CX + 80, ZC_CY + 80], fill=(236, 240, 244), outline=DARK, width=2)
    d.ellipse([ZC_CX - 58, ZC_CY - 58, ZC_CX + 58, ZC_CY + 58], fill=BG, outline=DARK, width=1)
    # 内盘体（目标齿轮）
    d.ellipse([ZC_CX - 30, ZC_CY - 30, ZC_CX + 30, ZC_CY + 30], fill=(206, 228, 212) if engaged else (228, 234, 240),
              outline=(15, 80, 140) if not engaged else GREEN, width=2)
    # 外环狗牙（结合套，朝内）：颜色随状态
    ocol = RED if clash else (GREEN if sync else (150, 156, 162))
    dog_face(d, ZC_CX, ZC_CY, DOG_N, ths, 56, 40, ocol, DARK, 1)
    # 内盘狗牙（齿轮，朝外）：蓝色
    dog_face(d, ZC_CX, ZC_CY, DOG_N, th_gear, 30, 43, DRV, (15, 80, 140), 1)
    # 中心轴
    d.ellipse([ZC_CX - 4, ZC_CY - 4, ZC_CX + 4, ZC_CY + 4], fill=(73, 80, 87))
    # 咬合区结果
    if clash:
        sparks(d, ZC_CX, ZC_CY, fr)
        d.line([ZC_CX - 10, ZC_CY - 10, ZC_CX + 10, ZC_CY + 10], fill=RED, width=3)
        d.line([ZC_CX - 10, ZC_CY + 10, ZC_CX + 10, ZC_CY - 10], fill=RED, width=3)
        text(d, ZC_CX, ZC_CY + ZC_R + 4, '牙尖撞牙尖 → 打齿', RED, CB14, 'ma')
    elif engaged:
        d.line([ZC_CX - 8, ZC_CY, ZC_CX - 3, ZC_CY + 6], fill=GREEN, width=3)
        d.line([ZC_CX - 3, ZC_CY + 6, ZC_CX + 8, ZC_CY - 6], fill=GREEN, width=3)
        text(d, ZC_CX, ZC_CY + ZC_R + 4, '牙对槽 → 锁定齿轮到轴', GREEN, CB14, 'ma')
    else:
        text(d, ZC_CX, ZC_CY + ZC_R + 4, '牙与槽错位', YEL, C12, 'ma')
    # 图例
    text(d, ZC_CX - 70, ZC_CY + ZC_R + 24, '外环=结合套', ocol, C10)
    text(d, ZC_CX + 70, ZC_CY + ZC_R + 24, '内盘=齿轮', DRV, C10, 'ma')


st_val = 0.0


def gen(mode, total, fname):
    global st_val
    is_nogl = (mode == 'nogl')
    ths = 0.0
    st_val = 0.0
    x = COLLAR_X0
    carx = 120.0
    frames = []
    for fr in range(total):
        th_eng = WENG * fr
        th_gear = WGEAR * fr
        if is_nogl:
            gap = 0.0
            omega = WENG
            st_val = 0.0
        else:
            gap = min(1.0, fr / 5.0) * 14
            st_val = min(1.0, max(0.0, (fr - 6) / 30.0))
            omega = WENG + (WGEAR - WENG) * (0.5 - 0.5 * math.cos(math.pi * st_val))
        ths += omega

        if is_nogl:
            p = (fr % 16) / 16.0
            if p < 0.70:
                x = COLLAR_X0 + (COLLAR_X1 - COLLAR_X0) * (p / 0.70)
            elif p < 0.85:
                x = COLLAR_X1
            else:
                x = COLLAR_X1 - (COLLAR_X1 - COLLAR_X0) * ((p - 0.85) / 0.15)
        else:
            x = COLLAR_X0 + (COLLAR_X1 - COLLAR_X0) * (1.0 - math.exp(-0.35 * max(0.0, st_val - 0.85) / 0.15))

        delta = abs((ths - th_gear) / (2 * math.pi / DOG_N)) - 0.5
        phase_ok = delta < 0.18
        near = x > COLLAR_X1 - 20
        fully = x > COLLAR_X1 - 3
        engaged = fully and phase_ok
        clash = (near and not phase_ok) if is_nogl else (fully and not phase_ok)
        sync = engaged or phase_ok

        img = Image.new('RGB', (W, H), BG)
        d = ImageDraw.Draw(img)
        title = '换挡不踩离合：狗牙打齿' if is_nogl else '换挡踩离合：同步后平稳挂入'
        text(d, W // 2, 10, title, RED if is_nogl else GREEN, CB16, 'ma')

        main_diagram(d, fr, gap, omega, ths, th_eng, th_gear, x, clash, engaged, sync, is_nogl)
        zoom(d, fr, ths, th_gear, clash, engaged, sync)

        # 状态横幅
        if is_nogl:
            stat, scol = '转速不同步：结合套3000 ≠ 齿轮1000，狗牙永远撞不进', RED
        elif clash:
            stat, scol = '仍在打齿：转速还没拉平', RED
        elif engaged:
            stat, scol = '已同步：狗牙对槽，结合套滑入，锁定齿轮', GREEN
        elif st_val > 0.05:
            stat, scol = '同步环摩擦：结合套转速 3000 → 1000（向齿轮靠拢）', YEL
        else:
            stat, scol = '踩下离合：发动机与输入轴断开', GR(110)
        text(d, W // 2, 446, stat, scol, CB14, 'ma')

        # 小车：顿挫 vs 平顺
        carx += 1.2 if not is_nogl else (3.0 if clash else 0.6)
        if carx > 300:
            carx -= 220
        jerk = 0.0
        if is_nogl:
            jerk = 14 * math.sin(2 * math.pi * fr / 4) if clash else 5 * math.sin(2 * math.pi * fr / 3)
        d.line([60, 404, 300, 404], fill=(190, 194, 198), width=2)
        draw_car(d, carx + jerk, 402)
        text(d, 56, 392, '车身：', GR(110), C10, 'ra')
        text(d, 56, 420, '顿挫' if is_nogl else '平顺', RED if is_nogl else GREEN, C11, 'ra')

        frames.append(img)

    path = os.path.join(OUT_DIR, fname)
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=DUR, loop=0)
    print('saved %s, %d frames, %dx%d' % (path, len(frames), W, H))


gen('nogl', 54, 'clutch-no.gif')
gen('clutch', 66, 'clutch-yes.gif')
