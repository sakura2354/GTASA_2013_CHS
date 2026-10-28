#!/usr/bin/env python3
"""重打 libGTASA.so：六个补丁一次完成。

只在**字库内容变化**时才需要跑这个（换字体本身不用，因为字库顺序与字体无关）。
字库变了会导致「码位 → 记录下标」的映射变化，映射表编在 .so 里，必须同步重打。

补丁清单：
  [0] DT_NEEDED -> libcnpatch.so（复用 .dynstr 里废弃的 InitArrayCount 槽）
  [A] 0x5A8A88  PrintChar 入口  -> 桩：暂存码位到 0x6B2DA0
  [B] 0x5A8EB4  索引处          -> 桩：把索引换成我们的记录下标
  [C] 0x5A7BD0  GetJapaneseWidth 入口 -> 桩：恒定返回 20.0
  [D] 0x5A80FE  图集尺寸 0x400 -> 0x800（1024 -> 2048）
  [E] 0x5A7F84  字形上限 0x706 -> 0xFFF（1799 -> 4095）

用法：
    python repack_full.py [映射表.bin] [输出 so]
默认：
    映射表 = ../fonts/out_simsun/maptable.bin
    输出   = libGTASA_full.so
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
WORK = os.path.dirname(HERE)

SRC_SO = os.path.join(WORK, "gtasa_200", "lib", "armeabi-v7a", "libGTASA.so")

# 桩的机器码目标文件（由 clang 汇编）
OBJ_STASH = os.path.join(HERE, "cn_stash.o")
OBJ_IDX2 = os.path.join(HERE, "cn_idx2.o")
OBJ_WIDTH = os.path.join(HERE, "cn_width.o")

CAVE_STASH, OFF_STASH = 0xAA8000, 0x6C0000
CAVE_IDX2, OFF_IDX2 = 0xAA8200, 0x6C0200
CAVE_WIDTH, OFF_WIDTH = 0xAA8400, 0x6C0400
CAVE_TABLE, OFF_TABLE = 0xAA8C00, 0x6C0C00

P_ENTRY, R_ENTRY = 0x5A8A88, 0x5A8A94
EXP_ENTRY = bytes.fromhex("f0b503af4df8048d2ded0c8b")
P_IDX, R_IDX = 0x5A8EB4, 0x5A8EB8
EXP_IDX = bytes.fromhex("00eb4000")
P_WIDTH = 0x5A7BD0
P_SHEET = 0x5A80FE
EXP_SHEET = bytes.fromhex("4ff48061")
NEW_SHEET = bytes.fromhex("4ff40061")
P_CAP = 0x5A7F84
EXP_CAP = bytes.fromhex("40f20670")
NEW_CAP = bytes.fromhex("40f6ff70")

DEAD_SLOT = 0xCC51C
TARGET_LIB = "libcnpatch.so"


def thumb_bw(from_addr, to_addr):
    pc = (from_addr + 4) & 0xFFFFFFFF
    imm32 = (to_addr - pc) & 0xFFFFFFFF
    s = (imm32 >> 24) & 1
    i1 = (imm32 >> 23) & 1
    i2 = (imm32 >> 22) & 1
    imm10 = (imm32 >> 12) & 0x3FF
    imm11 = (imm32 >> 1) & 0x7FF
    j1 = (~(i1 ^ s)) & 1
    j2 = (~(i2 ^ s)) & 1
    return struct.pack("<HH",
                       0xF000 | (s << 10) | imm10,
                       0x9000 | (j1 << 13) | (j2 << 11) | imm11)


def read_text(obj_path):
    d = open(obj_path, "rb").read()
    e_shoff, = struct.unpack_from("<I", d, 0x20)
    es, en, sx = struct.unpack_from("<HHH", d, 0x2E)
    sh = [struct.unpack_from("<IIIIIIIIII", d, e_shoff + i * es) for i in range(en)]
    strtab = sh[sx][4]
    for s in sh:
        end = d.find(b"\0", strtab + s[0])
        if d[strtab + s[0]:end].decode("latin1") == ".text":
            return bytes(d[s[4]:s[4] + s[5]])
    raise SystemExit("没有 .text: %s" % obj_path)


def main():
    maptable = sys.argv[1] if len(sys.argv) > 1 else \
        os.path.join(WORK, "fonts", "out_simsun", "maptable.bin")
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "libGTASA_full.so")

    d = bytearray(open(SRC_SO, "rb").read())

    # ---------- 校验 ----------
    for off, exp, name in ((P_ENTRY, EXP_ENTRY, "PrintChar 入口"),
                           (P_IDX, EXP_IDX, "0x5A8EB4"),
                           (P_SHEET, EXP_SHEET, "图集尺寸"),
                           (P_CAP, EXP_CAP, "字形上限")):
        cur = bytes(d[off:off + len(exp)])
        if cur != exp:
            raise SystemExit("%s 字节不符: %s (期望 %s)" % (name, cur.hex(), exp.hex()))
    hw = struct.unpack_from("<H", d, P_WIDTH)[0]
    if (hw & 0xFF00) != 0xB500:
        raise SystemExit("GetJapaneseWidth 入口不是 push")

    # ---------- [0] DT_NEEDED ----------
    e_shoff, = struct.unpack_from("<I", d, 0x20)
    es, en, sx = struct.unpack_from("<HHH", d, 0x2E)
    sh = [list(struct.unpack_from("<IIIIIIIIII", d, e_shoff + i * es)) for i in range(en)]
    sstr = sh[sx][4]

    def secname(i):
        s = sstr + sh[i][0]
        return d[s:d.find(b"\0", s)].decode("latin1")

    names = {secname(i): i for i in range(en)}
    strtab_off = sh[names[".dynstr"]][4]
    dyn_off, dyn_sz = sh[names[".dynamic"]][4], sh[names[".dynamic"]][5]

    fo = strtab_off + DEAD_SLOT
    if not bytes(d[fo:fo + 14]).startswith(b"InitArrayCount"):
        raise SystemExit("废弃槽内容变了")
    d[fo:fo + len(TARGET_LIB) + 1] = TARGET_LIB.encode() + b"\0"
    null_i = None
    for k in range(dyn_sz // 8):
        if struct.unpack_from("<iI", d, dyn_off + k * 8)[0] == 0:
            null_i = k
            break
    if null_i is None:
        raise SystemExit("找不到 DT_NULL")
    struct.pack_into("<iI", d, dyn_off + null_i * 8, 1, DEAD_SLOT)
    print("[0] DT_NEEDED -> %s" % TARGET_LIB)

    # ---------- [A] 暂存桩 ----------
    a = bytearray(read_text(OBJ_STASH))
    a += thumb_bw(CAVE_STASH + len(a), R_ENTRY)
    d[OFF_STASH:OFF_STASH + len(a)] = a
    d[P_ENTRY:P_ENTRY + 12] = thumb_bw(P_ENTRY, CAVE_STASH) + b"\x00\xbf" * 4
    print("[A] 暂存桩 %d 字节 -> 0x%X" % (len(a) - 4, CAVE_STASH))

    # ---------- [B] 索引桩 ----------
    b = bytearray(read_text(OBJ_IDX2))
    b += thumb_bw(CAVE_IDX2 + len(b), R_IDX)
    d[OFF_IDX2:OFF_IDX2 + len(b)] = b
    d[P_IDX:P_IDX + 4] = thumb_bw(P_IDX, CAVE_IDX2)
    print("[B] 索引桩 %d 字节 -> 0x%X" % (len(b) - 4, CAVE_IDX2))

    # ---------- [C] 字宽桩 ----------
    w = bytearray(read_text(OBJ_WIDTH))
    d[OFF_WIDTH:OFF_WIDTH + len(w)] = w
    d[P_WIDTH:P_WIDTH + 4] = thumb_bw(P_WIDTH, CAVE_WIDTH)
    d[P_WIDTH + 4:P_WIDTH + 10] = b"\x00\xbf" * 3
    print("[C] 字宽桩 %d 字节 -> 0x%X" % (len(w), CAVE_WIDTH))

    # ---------- 映射表 ----------
    table = open(maptable, "rb").read()
    if OFF_TABLE + len(table) > len(d):
        raise SystemExit("映射表超出代码洞")
    d[OFF_TABLE:OFF_TABLE + len(table)] = table
    print("[D] 映射表 %d 字节（来自 %s）" % (len(table), os.path.basename(maptable)))

    # ---------- 图集尺寸 / 字形上限 ----------
    d[P_SHEET:P_SHEET + 4] = NEW_SHEET
    print("[E] 图集尺寸 0x400 -> 0x800")
    d[P_CAP:P_CAP + 4] = NEW_CAP
    print("[F] 字形上限 0x706 -> 0xFFF")

    open(out, "wb").write(bytes(d))
    print("输出 %s（%d 字节）" % (out, len(d)))


if __name__ == "__main__":
    main()
