#!/usr/bin/env python3
"""把官方手机版 GXT 里「中文包缺失」的条目原样补进中文 GXT。

要求：不翻译、不修改原文，只补缺项。

匹配依据：GXT 的 hash 是跨语言恒定的 key，所以按 (表名, hash) 配对。

输入：
    官方 Android GXT（UTF-16LE，flags 0x0010）
    中文 GXT（UTF-8，flags 0x0008，来自 PC 包）
输出：
    合并后的 Android GXT（UTF-16LE，flags 0x0010），中文条目保持不变，
    官方有而中文没有的条目按原文补入。

用法：python merge_missing.py <官方.gxt> <中文.gxt> <输出.gxt>
"""
import struct
import sys


# ---------------------------------------------------------------- 解析

def _iter_tables(d):
    """产出 (表名, 条目区起始, 条目字节数, 字符串数据区)。"""
    n_bytes = struct.unpack_from("<I", d, 8)[0]
    n_tab = n_bytes // 12
    for i in range(n_tab):
        o = 12 + i * 12
        name = d[o:o + 8].rstrip(b"\x00").decode("latin1")
        off = struct.unpack_from("<I", d, o + 8)[0]
        if off + 12 > len(d):
            continue
        if d[off:off + 4] == b"TKEY":
            tk = off
        elif off + 16 <= len(d) and d[off + 8:off + 12] == b"TKEY":
            tk = off + 8            # 非 MAIN 表在 TKEY 前重复表名
        else:
            continue
        esize = struct.unpack_from("<I", d, tk + 4)[0]
        body = tk + 8
        tdat = body + esize
        if tdat + 8 > len(d) or d[tdat:tdat + 4] != b"TDAT":
            continue
        dsize = struct.unpack_from("<I", d, tdat + 4)[0]
        yield name, body, esize, d[tdat + 8: tdat + 8 + dsize]


def load_gxt(path):
    """返回 {表名: {hash: 文本}}，自动识别 UTF-16 还是 UTF-8。"""
    d = open(path, "rb").read()
    flags = struct.unpack_from("<H", d, 2)[0]
    out = {}
    for name, body, esize, data in _iter_tables(d):
        entries = {}
        for k in range(esize // 8):
            e = body + k * 8
            if e + 8 > len(d):
                break
            rel, h = struct.unpack_from("<II", d, e)
            if rel >= len(data):
                continue
            if flags & 0x0010:                       # UTF-16LE
                chars = []
                p = rel
                while p + 1 < len(data):
                    w = data[p] | (data[p + 1] << 8)
                    if w == 0:
                        break
                    chars.append(w)
                    p += 2
                text = "".join(chr(c) for c in chars)
            else:                                    # UTF-8
                z = data.find(b"\x00", rel)
                raw = data[rel:z if z >= 0 else len(data)]
                try:
                    text = raw.decode("utf-8")
                except UnicodeDecodeError:
                    continue
            entries[h] = text
        out[name] = entries
    return out, flags


# ---------------------------------------------------------------- 写出

def build_android_gxt(tables, order):
    """按 Android 布局重建：UTF-16LE，flags 0x0010。order 决定表顺序。

    重要：每个表的条目**必须按 hash 升序排列**。
        引擎是按 hash 做二分查找的，官方三个 GXT 都是升序；
        合并后若不排序，查找会大面积失败，游戏里表现为文本空白。
    """
    header = bytearray()
    header += struct.pack("<HH", 0x0004, 0x0010)
    header += b"TABL"
    header += struct.pack("<I", len(order) * 12)

    dir_size = 12 + len(order) * 12
    cursor = dir_size
    layout = []
    for name in order:
        entries = tables[name]
        esize = len(entries) * 8
        payload = bytearray()
        entry_bytes = bytearray()
        # 按 hash 升序（引擎按 hash 二分查找）
        for h in sorted(entries):
            entry_bytes += struct.pack("<II", len(payload), h)
            payload += entries[h].encode("utf-16-le") + b"\x00\x00"
        chunk = bytearray()
        if name != "MAIN":
            chunk += name.encode("ascii")[:7].ljust(8, b"\x00")
        chunk += b"TKEY" + struct.pack("<I", esize)
        chunk += entry_bytes
        chunk += b"TDAT" + struct.pack("<I", len(payload))
        chunk += payload
        layout.append((name, cursor, bytes(chunk)))
        cursor += len(chunk)

    directory = bytearray()
    for name, off, _c in layout:
        directory += name.encode("ascii")[:7].ljust(8, b"\x00")
        directory += struct.pack("<I", off)

    out = header + directory
    for _n, _o, chunk in layout:
        out += chunk
    return bytes(out)


def main():
    if len(sys.argv) < 4:
        raise SystemExit(__doc__)
    off_path, zh_path, out_path = sys.argv[1:4]

    official, off_flags = load_gxt(off_path)
    chinese, zh_flags = load_gxt(zh_path)

    print("官方 GXT : %s  flags=0x%04X  表=%d  条目=%d"
          % (off_path, off_flags, len(official), sum(len(v) for v in official.values())))
    print("中文 GXT : %s  flags=0x%04X  表=%d  条目=%d"
          % (zh_path, zh_flags, len(chinese), sum(len(v) for v in chinese.values())))

    added_total = 0
    added_detail = []
    merged = {}

    for name, off_entries in official.items():
        zh_entries = chinese.get(name, {})
        merged_entries = dict(zh_entries)                  # 中文条目保持原样
        missing = [(h, t) for h, t in off_entries.items() if h not in zh_entries]
        for h, t in missing:
            merged_entries[h] = t                          # 原样补入，不改动
        merged[name] = merged_entries
        if missing:
            added_total += len(missing)
            added_detail.append((name, len(zh_entries), len(missing), len(merged_entries)))

    # 官方没有、中文独有的表/条目也保留
    for name, zh_entries in chinese.items():
        if name not in merged:
            merged[name] = dict(zh_entries)

    print()
    print("补入条目: %d" % added_total)
    print("%-10s %8s %8s %8s" % ("表", "原中文", "补入", "合并后"))
    for name, a, b, c in sorted(added_detail, key=lambda x: -x[2])[:20]:
        print("%-10s %8d %8d %8d" % (name, a, b, c))

    order = list(official.keys())
    for name in merged:
        if name not in order:
            order.append(name)

    data = build_android_gxt(merged, order)
    open(out_path, "wb").write(data)

    total_before = sum(len(v) for v in chinese.values())
    total_after = sum(len(v) for v in merged.values())
    print()
    print("条目总数: %d -> %d  (+%d)" % (total_before, total_after, total_after - total_before))
    print("已写出 %s（%d 字节）" % (out_path, len(data)))

    # 字符集变化
    cs_before = {ord(c) for v in chinese.values() for t in v.values() for c in t if ord(c) >= 0x20}
    cs_after = {ord(c) for v in merged.values() for t in v.values() for c in t if ord(c) >= 0x20}
    new_chars = sorted(cs_after - cs_before)
    print("新增码位: %d 个" % len(new_chars))
    if new_chars:
        print("  " + "".join(chr(c) for c in new_chars[:80]))
        print("  这些字符需要重新生成字形图集并重打 .so")


if __name__ == "__main__":
    main()
