# -*- coding: utf-8 -*-
"""生成两个齿轮啮合旋转的 GIF 动图：小齿轮转 4 圈，大齿轮转 1 圈（传动比 4:1）"""
import math
from PIL import Image, ImageDraw

W, H = 520, 280

# 齿轮参数
cx1, cy1, r1, teeth1 = 160, 150, 36, 8      # 小齿轮（驱动）
cx2, cy2, r2, teeth2 = 160 + 36 + 78, 150, 78, 32   # 大齿轮（从动），中心距 = r1 + r2
tooth_h = 11

def gear_vertices(cx, cy, r, n, angle):
    """齿轮轮廓顶点：交替齿尖(r+tooth_h)和齿根(r)"""
    pts = []
    for i in range(2 * n):
        a = angle + math.pi * i / n
        rr = r + tooth_h if i % 2 == 0 else r
        pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
    return pts

def draw_gear(d, cx, cy, r, n, angle, color, outline):
    d.polygon(gear_vertices(cx, cy, r, n, angle), fill=color, outline=outline)
    # 主体圆覆盖到半径 r，让齿尖 r~r+tooth_h 露出
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color, outline=outline)
    d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=(73, 80, 87))

COLOR = (255, 224, 102)
OUTLINE = (230, 119, 0)
RED = (201, 42, 42)
BLUE = (25, 113, 194)

# 初始相位：啮合点（小齿轮右侧 / 大齿轮左侧）齿尖对齿槽
a1_0 = 0.0                                   # 小齿轮齿尖在角度 0（指向大齿轮）
a2_0 = math.pi - math.pi / teeth2            # 大齿轮齿槽在角度 pi（指向小齿轮）

TOTAL = 40
frames = []
for f in range(TOTAL):
    t = f / TOTAL
    a1 = a1_0 + 2 * math.pi * t       # 小齿轮顺时针转 1 圈（360°）
    a2 = a2_0 - (math.pi / 2) * t     # 大齿轮逆时针转 1/4 圈（90°）

    img = Image.new('RGB', (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)

    # 大齿轮（先画，在后面）
    draw_gear(d, cx2, cy2, r2, teeth2, a2, COLOR, OUTLINE)
    # 小齿轮
    draw_gear(d, cx1, cy1, r1, teeth1, a1, COLOR, OUTLINE)

    # 标注（ASCII，避免中文字体问题）
    d.text((cx1 - 20, cy1 - 62), "z1=%d" % teeth1, fill=RED)
    d.text((cx2 - 22, cy2 - 100), "z2=%d" % teeth2, fill=BLUE)
    d.text((cx2 - 95, cy1 + 98), "small gear: 4 turns", fill=(80, 80, 80))
    d.text((cx2 - 85, cy1 + 112), "big gear: 1 turn", fill=(80, 80, 80))

    frames.append(img)

frames[0].save('gear-mesh.gif', save_all=True, append_images=frames[1:],
               duration=60, loop=0)
print("saved gear-mesh.gif, %d frames" % len(frames))
