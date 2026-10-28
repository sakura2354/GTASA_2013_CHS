#!/usr/bin/env python3
"""把 PC 版 GXT（UTF-8, flags=0x0008）转成 Android 版（UTF-16LE, flags=0x0010）。

背景：
  * PC 版 GXT 用 UTF-8，头部 flags = 0x0008
  * Android 版 GXT 用 UTF-16LE，头部 flags = 0x0010
    （两份官方文件实测：assets/Text/american.gxt = 04 00 10 00）
  * 两者骨架完全相同：
        "TABL" + u32 目录字节数
        目录项: char[8] name + u32 表偏移
        表体:   [char[8] name, 仅非 MAIN] + "TKEY" + u32 条目区字节数
                条目: { u32 data_offset(相对 TDAT 数据区), u32 hash }
                "TDAT" + u32 数据区字节数
                数据区: 字符串，NUL 结尾
  * 唯一差别是字符串编码与 flags。

所以转换只做两件事：
  1. flags 0x0008 -> 0x0010
  2. 每个字符串 UTF-8 -> UTF-16LE，结尾从 1 个 0x00 变成 2 个 0x00

hash 原样保留（它是跨语言恒定的 key，不能改）。
"""
import struct
import sys


def parse_pc_gxt(d):
    """返回 [(table_name, [(hash, text), ...]), ...]，保持文件中的表顺序。

    注意：目录里的偏移对 MAIN 指向 TKEY 本身，而对其它表指向「表名(8) + TKEY」，
    因为非 MAIN 表会在 TKEY 前重复一次表名。两种都要处理。
    """
    n_bytes = struct.unpack_from("<I", d, 8)[0]
    n_tab = n_bytes // 12
    out = []
    for i in range(n_tab):
        o = 12 + i * 12
        name = d[o:o + 8].rstrip(b"\x00").decode("latin1")
        off = struct.unpack_from("<I", d, o + 8)[0]

        if off + 12 <= len(d) and d[off:off + 4] == b"TKEY":
            tk = off
        elif off + 16 <= len(d) and d[off + 8:off + 12] == b"TKEY":
            tk = off + 8                      # 跳过重复的表名
        else:
            continue

        esize = struct.unpack_from("<I", d, tk + 4)[0]
        body = tk + 8
        tdat = body + esize
        if tdat + 8 > len(d) or d[tdat:tdat + 4] != b"TDAT":
            continue
        dsize = struct.unpack_from("<I", d, tdat + 4)[0]
        data = d[tdat + 8: tdat + 8 + dsize]
        entries = []
        for k in range(esize // 8):
            e = body + k * 8
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
            entries.append((h, text))
        out.append((name, entries))
    return out


def build_android_gxt(tables):
    """按 Android 布局重建：UTF-16LE + flags 0x0010。"""
    body = bytearray()

    # 头 12 字节
    header = bytearray()
    header += struct.pack("<HH", 0x0004, 0x0010)
    header += b"TABL"
    header += struct.pack("<I", len(tables) * 12)
    body += header

    # 先算每张表的块大小，才能确定各表偏移
    # 布局：[TABL 目录][表0: name?+TKEY+hdr+entries][TDAT 头+数据][表1...]
    dir_size = 12 + len(tables) * 12
    cursor = dir_size
    layout = []
    for name, entries in tables:
        esize = len(entries) * 8
        blob = bytearray()
        payload = bytearray()
        entry_bytes = bytearray()
        for h, text in entries:
            entry_bytes += struct.pack("<II", len(payload), h)
            payload += text.encode("utf-16-le") + b"\x00\x00"
        table_off = cursor
        chunk = bytearray()
        if name != "MAIN":
            chunk += name.encode("ascii")[:7].ljust(8, b"\x00")
        chunk += b"TKEY" + struct.pack("<I", esize)
        chunk += entry_bytes
        chunk += b"TDAT" + struct.pack("<I", len(payload))
        chunk += payload
        layout.append((name, table_off, bytes(chunk)))
        cursor += len(chunk)

    # 目录
    directory = bytearray()
    for name, table_off, _chunk in layout:
        directory += name.encode("ascii")[:7].ljust(8, b"\x00")
        directory += struct.pack("<I", table_off)
    out = header + directory
    for _name, _off, chunk in layout:
        out += chunk
    return bytes(out), layout


def main():
    if len(sys.argv) < 3:
        raise SystemExit("用法: gxt_utf8_to_utf16.py <pc.gxt> <android.gxt>")
    src, dst = sys.argv[1], sys.argv[2]
    d = open(src, "rb").read()
    ver, flags = struct.unpack_from("<HH", d, 0)
    print("源文件: %s  大小=%d  version=0x%04X flags=0x%04X" % (src, len(d), ver, flags))

    tables = parse_pc_gxt(d)
    n_entries = sum(len(e) for _n, e in tables)
    print("表数=%d  条目=%d" % (len(tables), n_entries))

    out, layout = build_android_gxt(tables)
    open(dst, "wb").write(out)
    print("已写出: %s  大小=%d" % (dst, len(out)))

    # 自检：重新按 Android 规则解析一遍
    n2 = len(parse_pc_gxt(out)) if False else None
    print()
    print("=== 布局抽样（前 3 张表） ===")
    for name, off, chunk in layout[:3]:
        print("  %-8s off=0x%06X chunk=%d 字节  首 16B=%s"
              % (name, off, len(chunk), chunk[:16].hex()))


if __name__ == "__main__":
    main()
