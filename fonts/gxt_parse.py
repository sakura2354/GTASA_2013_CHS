#!/usr/bin/env python3
"""GXT 解析（UTF-8 / TDAT 版）。

实测结构（wm_sachs.gxt，与官方 american.gxt 同一套骨架）：

    0x00  u16 version
    0x02  u16 flags
    0x04  "TABL"
    0x08  u32 目录字节数 (= 表数 * 12)
    0x0C  表目录: 每项 char[8] name + u32 表偏移

    表偏移处:
        "TKEY" + u32 条目区字节数
        条目区: 每项 8 字节 { u32 rel_off, u32 hash }
                rel_off 相对于紧跟其后的 TDAT 数据区起点
        "TDAT" + u32 数据区字节数
        数据区: UTF-8 字符串，NUL 分隔

对照：官方 american.gxt 的表体是 UTF-16（无双零以外的差异），
      而这份中文包用 UTF-8 —— 引擎在加载时转成内部 UTF-16（GxtChar）。
"""
import struct
import sys
from collections import Counter


def parse(path):
    d = open(path, "rb").read()
    n_bytes = struct.unpack_from("<I", d, 8)[0]
    n_tab = n_bytes // 12

    tables = []
    for i in range(n_tab):
        o = 12 + i * 12
        name = d[o:o + 8].rstrip(b"\x00").decode("latin1")
        off = struct.unpack_from("<I", d, o + 8)[0]
        tables.append((name, off))

    out = []          # (table, key_hash, text)
    for name, off in tables:
        if off + 12 > len(d) or d[off:off + 4] != b"TKEY":
            continue
        esize = struct.unpack_from("<I", d, off + 4)[0]
        body = off + 8
        tdat = body + esize
        if tdat + 8 > len(d) or d[tdat:tdat + 4] != b"TDAT":
            continue
        dsize = struct.unpack_from("<I", d, tdat + 4)[0]
        data = d[tdat + 8: tdat + 8 + dsize]

        n = esize // 8
        for i in range(n):
            e = body + i * 8
            if e + 8 > len(d):
                break
            rel, h = struct.unpack_from("<II", d, e)
            if rel >= len(data):
                continue
            z = data.find(b"\x00", rel)
            raw = data[rel:z if z >= 0 else len(data)]
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if text:
                out.append((name, h, text))
    return d, tables, out


def main():
    path = sys.argv[1]
    d, tables, entries = parse(path)
    print("文件      : %s" % path)
    print("大小      : %d 字节" % len(d))
    print("表数      : %d" % len(tables))
    print("有效文本  : %d 条" % len(entries))

    codes = Counter()
    for _t, _h, s in entries:
        for ch in s:
            codes[ord(ch)] += 1

    cjk = [c for c in codes if 0x3400 <= c <= 0x9FFF]
    ascii_ = [c for c in codes if 0x20 <= c < 0x7F]
    ctrl = [c for c in codes if c < 0x20]
    punct = [c for c in codes
             if c >= 0x20 and not (0x20 <= c < 0x7F) and not (0x3400 <= c <= 0x9FFF)]

    print()
    print("唯一码位  : %d" % len(codes))
    print("  汉字    : %d" % len(cjk))
    print("  ASCII   : %d" % len(ascii_))
    print("  标点/其他: %d" % len(punct))
    print("  控制符  : %d" % len(ctrl))

    need = len(cjk) + len(ascii_) + len(punct)
    print()
    print("需要绘制的字形数: %d   (引擎上限 1799 -> %s)"
          % (need, "够" if need <= 1799 else "不够"))

    print()
    print("=== 样例（按表） ===")
    seen = set()
    for t, _h, s in entries:
        if t in seen:
            continue
        seen.add(t)
        print("  [%-8s] %s" % (t, s[:60]))
        if len(seen) >= 8:
            break

    print()
    print("=== 高频字 40 个 ===")
    top = "".join(chr(c) for c, _ in codes.most_common(60) if c >= 0x20)
    print("  " + top)


if __name__ == "__main__":
    main()
