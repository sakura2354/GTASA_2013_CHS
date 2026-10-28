#!/usr/bin/env python3
"""换字体：从任意 TTF/OTF/TTC 生成游戏用的字形图集 + 度量表。

好消息：换字体**不需要重新补丁 libGTASA.so**。
    因为字库顺序是「按码位升序」，与用哪款字体无关，
    所以映射表（编在 .so 里）保持不变，只要重新生成两个资源文件：
        JapaneseFont.png   2048x2048 字形图集
        JapaneseFont.met   位置即下标的度量表

用法：
    python make_font.py <字体文件> [face索引] [输出目录] [字号]

    字体文件   例如 C:\\Windows\\Fonts\\msyh.ttc
    face索引   TTC 里选第几个字面，默认 0；TTF 忽略
    输出目录   默认 ./out
    字号       默认 30（2048 图集用 32x32 格子，30px 刚好留边）

例：
    python make_font.py C:\\Windows\\Fonts\\simhei.ttf
    python make_font.py C:\\Windows\\Fonts\\msyh.ttc 0
    python make_font.py C:\\Windows\\Fonts\\simsun.ttc 0
"""
import os
import struct
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from merge_missing import load_gxt               # noqa: E402  (自动识别 UTF-8/UTF-16)

SHEET = 2048
CELL = 32
COLS = ROWS = SHEET // CELL
CAP = COLS * ROWS                                # 4096

DEFAULT_GXT = r"C:\Users\Administrator\Downloads\wm_sachs\wm_sachs.gxt"


def charset_from_gxt(gxt_path):
    """取 GXT 里所有出现过的码位（>=0x20），并**补齐完整可打印 ASCII**。

    为什么要补 ASCII：
        GXT 里只出现了 86 个 ASCII 字符，但玩家名、mod 文本、控制台等
        可能用到别的可打印字符。补满 0x20..0x7E（95 个）后英文永不缺字，
        代价只有几个槽位。

    排序规则：按码位升序。顺序必须与编进 libGTASA.so 的映射表一致；
    本函数不使用频率筛选，所以结果确定；但**一旦字库内容变化，
    必须同时重新生成 maptable.bin 并重打 .so**（本脚本会自动输出映射表）。
    """
    tables, _flags = load_gxt(gxt_path)      # 自动识别 UTF-8 / UTF-16
    seen = set(range(0x20, 0x7F))            # 完整可打印 ASCII
    for _name, entries in tables.items():
        for text in entries.values():
            for ch in text:
                cp = ord(ch)
                if cp >= 0x20:
                    seen.add(cp)
    return sorted(seen)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)

    font_path = sys.argv[1]
    face = int(sys.argv[2]) if len(sys.argv) > 2 else 0
    outdir = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "out")
    size = int(sys.argv[4]) if len(sys.argv) > 4 else 30

    gxt = os.environ.get("CN_GXT", DEFAULT_GXT)
    if not os.path.exists(gxt):
        raise SystemExit("找不到 GXT: %s（可用环境变量 CN_GXT 指定）" % gxt)

    chars = charset_from_gxt(gxt)
    print("GXT 字库: %d 个码位（图集容量 %d）" % (len(chars), CAP))
    if len(chars) > CAP:
        raise SystemExit("字库超出图集容量，需要减小格子或加大图集")

    try:
        font = ImageFont.truetype(font_path, size, index=face)
    except Exception as e:
        raise SystemExit("加载字体失败: %s\n（TTC 请试着换 face 索引：0/1/2/3…）" % e)
    print("字体: %s  face=%d  字号=%d" % (font.getname(), face, size))

    img = Image.new("RGBA", (SHEET, SHEET), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)
    baseline = int(CELL * 0.82)

    rows = []
    missing = []
    for i, cp in enumerate(chars):
        cx = (i % COLS) * CELL
        cy = (i // COLS) * CELL
        ch = chr(cp)
        advance = max(1, min(CELL, int(round(font.getlength(ch)))))
        # 用字体自身的墨迹范围判断是否有该字形（.notdef 通常是一个方框）
        draw.text((cx, cy + baseline), ch, font=font,
                  fill=(255, 255, 255, 255), anchor="ls")
        rows.append((cp, cx, cy, cx + advance, cy + CELL))

    os.makedirs(outdir, exist_ok=True)
    png = os.path.join(outdir, "JapaneseFont.png")
    met = os.path.join(outdir, "JapaneseFont.met")
    img.save(png)

    # 位置即下标：code = 0x8000 + 行号
    lines = ["METRICS1", "JapaneseFont", "5"]
    for i, (_cp, x0, y0, x1, y1) in enumerate(rows):
        lines.append("%5d %5d %5d %5d %5d" % (0x8000 + i, x0, y0, x1, y1))
    with open(met, "wb") as fh:
        fh.write(("\r\n".join(lines) + "\r\n").encode("utf-8"))

    # 同步输出映射表（码位-0x20 -> 下标+1），用于重打 libGTASA.so
    LO, HI = 0x20, 0x10000   # 覆盖整个 BMP，含全角标点(0xFF01+)
    table = [0] * (HI - LO)
    for i, cp in enumerate(chars):
        if LO <= cp < HI:
            table[cp - LO] = i + 1
    maptable = os.path.join(outdir, "maptable.bin")
    with open(maptable, "wb") as fh:
        fh.write(struct.pack("<%dH" % len(table), *table))

    # 自查：抽几个字看是否真的有墨迹
    def ink(ch):
        cp = ord(ch)
        for r in rows:
            if r[0] == cp:
                crop = img.crop(r[1:])
                a = crop.split()[3]
                return sum(1 for v in a.get_flattened_data() if v > 16)
        return -1

    print()
    print("已写出:")
    print("  %s (%d 字节)" % (png, os.path.getsize(png)))
    print("  %s (%d 条, %d 字节)" % (met, len(rows), os.path.getsize(met)))
    print("  %s (%d 字节)  <- 字库若与上次不同，需要用它重打 libGTASA.so"
          % (maptable, os.path.getsize(maptable)))
    print()
    print("抽样检查（不透明像素数，0 表示该字体缺这个字）:")
    for ch in "我你他，。！？ABC123":
        print("  %s -> %d" % (ch, ink(ch)))
    print()
    print("安装到设备:")
    print("  adb push %s \"$FILES/Textures/Fonts/JapaneseFont.png\"" % png)
    print("  adb push %s \"$FILES/Textures/Fonts/JapaneseFont.met\"" % met)
    print("  # 其中 FILES=/sdcard/Android/data/com.rockstargames.gtasa/files")
    print("  # 换完不用动 libGTASA.so，直接重启游戏即可")


if __name__ == "__main__":
    main()
