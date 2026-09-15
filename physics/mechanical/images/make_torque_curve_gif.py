# -*- coding: utf-8 -*-
"""生成 GIF：为什么扭矩曲线是"两头小、中间大"

上半区：三个气缸（低转速 / 中转速 / 高转速）并排对比
        节气门开度 → 进气气流 → 充气系数 → 扭矩
下半区：扭矩-转速曲线，红点沿曲线扫描

结论一句话：扭矩由"每循环吸入的空气量"决定，而不是由"转多快"决定。
所有标注用 ASCII，避免中文字体缺字（同 make_gear_gif.py）。
"""
import math
import os
from PIL import Image, ImageDraw, ImageFont

OUT_DIR = os.path.dirname(os.path.abspath(__file__))

W, H = 720, 460
TOTAL = 44          # 帧数
DUR = 33            # 每帧毫秒 → 循环约 1.45s

BG = (255, 255, 255)
GR = lambda g: (g, g, g)


def F(size):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


F11, F12, F13, F14 = F(11), F(12), F(13), F(14)


def text(d, x, y, s, fill, font=F11, anchor=None):
    if anchor:
        d.text((x, y), s, fill=fill, font=font, anchor=anchor)
    else:
        d.text((x, y), s, fill=fill, font=font)


# ---------------- 单个气缸 ----------------

def draw_throttle(d, cx, y, ang):
    """节气门：ang=0 全开（板水平），ang=pi/2 全关（板竖直）"""
    L = 26
    x1 = cx - L * math.cos(ang)
    y1 = y - L * math.sin(ang)
    x2 = cx + L * math.cos(ang)
    y2 = y + L * math.sin(ang)
    d.line([x1, y1, x2, y2], fill=(52, 58, 64), width=4)
    d.ellipse([cx - 3, y - 3, cx + 3, y + 3], fill=(30, 33, 36))


def draw_cylinder(d, px, cfg, fr):
    """px: 面板左边缘 x；cfg: 该工况参数；fr: 当前帧"""
    bw = 104                      # 缸径
    bx = px + 60                  # 气缸左壁
    cx = bx + bw // 2
    cy_top, cy_bot = 96, 176
    stroke = 26                   # 活塞行程
    portw = 22                    # 进气道（气门）流通截面积 —— 固定！

    # 缸体底色（气室）
    d.rectangle([bx, cy_top, bx + bw, cy_bot], fill=(238, 242, 246))

    # --- 活塞（简谐往复）---
    cy = fr / cfg['cyc']
    phase = cy % 1
    ypos = cy_top + stroke + stroke * (1 - math.cos(2 * math.pi * phase)) / 2

    # --- 气体：充入的新鲜混合气（充气系数）---
    gap = max(ypos - cy_top, 2)
    fill_h = gap * cfg['charge'] / 100.0
    if fill_h > 1:
        d.rectangle([bx + 2, cy_top + 2, bx + bw - 2, cy_top + 2 + fill_h],
                    fill=(164, 214, 244))

    # 高转速：来不及进满 → 残余废气/未充满（浅色，非燃烧产物）
    if cfg['charge'] < 90:
        d.rectangle([bx + 2, cy_top + 2 + fill_h, bx + bw - 2, ypos - 1],
                    fill=(214, 222, 228))

    # --- 燃烧闪爆（做功冲程），强度 ∝ 扭矩 ---
    if phase < 0.22:
        k = 1 - phase / 0.22
        glow = cfg['torque'] * k
        d.rectangle([bx + 2, cy_top + 2, bx + bw - 2, ypos - 1],
                    fill=(255, 176 + int(70 * k), 96 + int(80 * k)))
        n = int(3 + glow / 22)
        for i in range(n):
            a = -math.pi / 2 + (i - (n - 1) / 2) * 0.42
            r0, r1 = 12, 12 + 9 + glow / 5.0
            d.line([cx + r0 * math.cos(a), cy_top + 14 + r0 * math.sin(a),
                    cx + r1 * math.cos(a), cy_top + 14 + r1 * math.sin(a)],
                   fill=(248, 150, 40), width=2)

    # --- 活塞本体 ---
    d.rectangle([bx + 3, ypos - 6, bx + bw - 3, ypos + 12],
                fill=(150, 158, 166), outline=(92, 100, 108))
    for i in range(3):
        yy = ypos + i * 3
        d.line([bx + 4, yy, bx + bw - 4, yy], fill=(112, 120, 128), width=1)

    # --- 缸壁 ---
    d.rectangle([bx, cy_top, bx + bw, cy_bot], outline=(92, 100, 108), width=3)

    # --- 曲轴（转速快慢一眼可见）---
    ccx, ccy = cx, cy_bot + 26
    r = 13
    rot = 2 * math.pi * cy
    d.line([cx, ypos + 4, ccx, ccy], fill=(110, 118, 126), width=3)
    d.ellipse([ccx - r, ccy - r, ccx + r, ccy + r],
              outline=(72, 79, 86), width=3)
    for i in range(4):
        a = rot + i * math.pi / 2
        d.line([ccx, ccy, ccx + (r - 2) * math.cos(a), ccy + (r - 2) * math.sin(a)],
               fill=(92, 100, 108), width=2)

    # --- 进气道 + 节气门 ---
    pxx = cx - portw // 2
    d.rectangle([pxx, 52, pxx + portw, cy_top], outline=(92, 100, 108), width=2)
    draw_throttle(d, cx, 68, cfg['throttle'])

    # --- 进气气流（气门流通截面积固定 → 空气流量有天花板）---
    for i in range(cfg['n']):
        yy = 54 + ((i * 78.0 / cfg['n']) + fr * 1.9) % 78
        d.ellipse([cx - 3, yy, cx + 3, yy + 4], fill=(124, 189, 236))

    # --- 右侧：充气系数 + 扭矩 仪表 ---
    gx = px + 178
    gh = 76
    d.rectangle([gx, 62, gx + 20, 62 + gh], outline=(160, 168, 174), width=2)
    fh = gh * cfg['charge'] / 100.0
    d.rectangle([gx + 2, 64 + gh - fh, gx + 18, 62 + gh - 2],
                fill=(124, 189, 236))
    text(d, gx + 10, 40, "fill %d%%" % cfg['charge'], GR(70), F12, 'ma')
    text(d, gx - 4, 84, "VE", GR(120), F11, 'ma')

    mw = 200
    my = 150
    d.rectangle([gx, my, gx + mw, my + 18], outline=(160, 168, 174), width=2)
    fw = (mw - 4) * cfg['torque'] / 100.0
    d.rectangle([gx + 2, my + 2, gx + 2 + fw, my + 16], fill=cfg['color'])
    text(d, gx + 100, my - 22, "TORQUE %d%%" % cfg['torque'], cfg['color'], F14, 'ma')

    # --- 标题 + 底部结论 ---
    text(d, px + 110, 16, cfg['title'], GR(40), F14, 'ma')
    text(d, px + 110, 36, cfg['rpm'], GR(130), F12, 'ma')
    text(d, px + 110, 184, cfg['reason'], cfg['color'], F11, 'ma')
    text(d, px + 110, 200, cfg['note'], GR(120), F11, 'ma')

    d.line([px + 24, 46, px + 196, 46], fill=(226, 228, 230), width=1)


# ---------------- 主循环 ----------------

# 扭矩曲线（与 images/torque-curve.svg 的钟形一致）
AX, AY = 104, 432
EX, EY = 668, 318
RX, RY = 7000, 200


def tx(rpm):
    return AX + (rpm / float(RX)) * (EX - AX)


def ty(t):
    return AY - (t / float(RY)) * (AY - EY)


def torque(rpm):
    """二次抛物线：怠速小 → 4000rpm 峰值 → 红区回落"""
    return 360 * (rpm - 150) * (7250 - rpm) / ((4000 - 150) * (7250 - 4000))


cfgs = [
    {'title': 'LOW rpm', 'rpm': '800 ~ 2000 rpm', 'charge': 58, 'throttle': math.radians(38),
     'n': 3, 'torque': 34, 'cyc': 8.67, 'color': (134, 142, 150),
     'reason': 'throttle half open -> big vacuum',
     'note': '-> little air per cycle'},
    {'title': 'MID rpm', 'rpm': '3000 ~ 4500 rpm', 'charge': 92, 'throttle': 0.0,
     'n': 9, 'torque': 100, 'cyc': 4.0, 'color': (232, 89, 12),
     'reason': 'throttle wide open -> bore fills up',
     'note': '-> max air per cycle'},
    {'title': 'HIGH rpm', 'rpm': '6000 ~ 7000 rpm', 'charge': 46, 'throttle': 0.0,
     'n': 5, 'torque': 58, 'cyc': 2.2, 'color': (201, 42, 42),
     'reason': 'port / valve area is FIXED',
     'note': '-> air cannot get in fast'},
]

frames = []
for fr in range(TOTAL):
    img = Image.new('RGB', (W, H), BG)
    d = ImageDraw.Draw(img)

    # ---- 上半区：三个气缸 ----
    for i, cfg in enumerate(cfgs):
        draw_cylinder(d, i * 240, cfg, fr)

    d.line([0, 236, W, 236], fill=(226, 228, 230), width=1)
    for sx in (240, 480):
        d.line([sx, 8, sx, 228], fill=(236, 238, 240), width=1)

    # ---- 下半区：扭矩-转速曲线 ----
    text(d, AX, 240, 'torque = air mass per cycle', GR(70), F12)
    d.line([AX, 264, AX, 440], fill=GR(51), width=2)
    d.line([AX, 432, EX, 432], fill=GR(51), width=2)
    text(d, EX - 2, 444, 'RPM ->', GR(70), F11, 'ra')

    # 峰值参考线
    d.line([tx(4000), ty(100) + 8, tx(4000), 432], fill=(226, 230, 234), width=1)

    # 曲线（随帧逐步绘出）
    end = min(1.0, fr / 14.0)
    prev = None
    for s in range(0, 7001, 25):
        if s > 7000 * end:
            break
        p = (tx(s), ty(torque(s)))
        if prev:
            d.line([prev[0], prev[1], p[0], p[1]], fill=(232, 89, 12), width=3)
        prev = p
    if prev:
        d.ellipse([prev[0] - 3, prev[1] - 3, prev[0] + 3, prev[1] + 3],
                  fill=(232, 89, 12))

    # 峰值标注
    d.ellipse([tx(4000) - 5, ty(100) - 5, tx(4000) + 5, ty(100) + 5],
              fill=(201, 42, 42))
    text(d, tx(4000) - 8, ty(100) - 22, 'peak ~4000 rpm', (201, 42, 42), F11)

    # 红区
    d.line([tx(6600), 264, tx(6600), 432], fill=(244, 200, 200), width=18)
    text(d, tx(6600) - 6, 270, 'redline', (201, 42, 42), F11, 'ma')

    # 区域底注
    text(d, (tx(600) + tx(2500)) / 2, 444, 'low: not enough air', (134, 142, 150), F11, 'ma')
    text(d, (tx(3000) + tx(4800)) / 2, 444, 'mid: fills the bore', (232, 89, 12), F11, 'ma')
    text(d, (tx(5500) + tx(6900)) / 2, 444, 'high: ports limit flow', (201, 42, 42), F11, 'ma')

    # ---- 扫描点：低 → 中 → 高 ----
    if fr >= 14:
        p = min(1.0, (fr - 14) / 28.0)
        u = 0.5 - 0.5 * math.cos(math.pi * p)
        si = min(2, int(u * 3))                 # 第几段: 0 低 / 1 中 / 2 高
        lo, hi = [(1000, 2500), (2500, 4800), (4800, 6600)][si]
        rpm = lo + (hi - lo) * (u * 3 - si)
        rpm = max(800, min(rpm, 7000))
        col = cfgs[si]['color']
        d.line([tx(rpm), ty(torque(rpm)), tx(rpm), 432], fill=(206, 210, 214), width=1)
        d.ellipse([tx(rpm) - 5, ty(torque(rpm)) - 5, tx(rpm) + 5, ty(torque(rpm)) + 5],
                  fill=col, outline=(255, 255, 255))

    frames.append(img)

out = os.path.join(OUT_DIR, 'torque-curve-why.gif')
frames[0].save(out, save_all=True, append_images=frames[1:], duration=DUR, loop=0)
print('saved %s, %d frames, %dx%d' % (out, len(frames), W, H))
