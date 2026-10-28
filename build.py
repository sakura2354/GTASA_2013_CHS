#!/usr/bin/env python3
"""一键构建 GTASA-CN 中文化补丁。

流程：
  1. 汇编三个桩（cn_stash / cn_idx2 / cn_width）
  2. 编译 libcnpatch.so
  3. 合并 GXT（中文包 + 官方手机版缺失条目，按 hash 排序）
  4. 生成字形图集 / 度量表 / 映射表
  5. 把六个补丁打进 libGTASA.so

用法：
    cp config.example.json config.json   # 然后填好路径
    python build.py

产物全部在 out/。
"""
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PATCH = os.path.join(HERE, "patch")
FONTS = os.path.join(HERE, "fonts")
OUT = os.path.join(HERE, "out")
BUILD = os.path.join(HERE, "build")

sys.path.insert(0, PATCH)
sys.path.insert(0, FONTS)


def die(msg):
    print("\n[错误] " + msg)
    sys.exit(1)


def run(cmd, what):
    print("  %s" % what)
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr)
        die("%s 失败（退出码 %d）" % (what, r.returncode))
    return r.stdout


def load_config():
    path = os.path.join(HERE, "config.json")
    if not os.path.exists(path):
        die("缺少 config.json。先复制 config.example.json 再填路径。")
    with open(path, encoding="utf-8-sig") as fh:   # 容忍 Windows 记事本的 BOM
        cfg = json.load(fh)

    for key, label in (("libGTASA_so", "libGTASA.so"),
                       ("american_gxt", "官方 american.gxt"),
                       ("chinese_gxt", "中文 GXT"),
                       ("font", "字体文件"),
                       ("ndk_bin", "NDK bin 目录")):
        v = cfg.get(key, "")
        if not v or v.startswith("path/to"):
            die("config.json 里的 %s 还没填" % key)
        if not os.path.exists(v):
            die("%s 不存在: %s" % (label, v))
    return cfg


def main():
    cfg = load_config()
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(BUILD, exist_ok=True)

    ndk = cfg["ndk_bin"].replace("\\", "/")
    cc = os.path.join(ndk, "armv7a-linux-androideabi21-clang.cmd")
    cxx = os.path.join(ndk, "armv7a-linux-androideabi21-clang++.cmd")
    for t in (cc, cxx):
        if not os.path.exists(t):
            die("找不到编译器: %s" % t)

    common = ("-mthumb -march=armv7-a -mfpu=vfpv3-d16 -mfloat-abi=softfp")

    # ---------- 1. 汇编三个桩 ----------
    print("[1/5] 汇编桩")
    objs = {}
    for name in ("cn_stash", "cn_idx2", "cn_width"):
        src = os.path.join(PATCH, "asm", name + ".s")
        obj = os.path.join(BUILD, name + ".o")
        if not os.path.exists(src):
            die("缺少汇编源: %s" % src)
        run('"%s" -c %s -o "%s" "%s"' % (cc, common, obj, src), name + ".s -> .o")
        objs[name] = obj

    # ---------- 2. 编译 libcnpatch.so ----------
    print("[2/5] 编译 libcnpatch.so")
    cpp = os.path.join(PATCH, "src", "libcnpatch.cpp")
    so_host = os.path.join(OUT, "libcnpatch.so")
    run('"%s" -shared -fPIC -O2 %s -fno-exceptions -fno-rtti -static-libstdc++ '
        '-o "%s" "%s" -llog -Wl,--build-id=none -Wl,-soname,libcnpatch.so'
        % (cxx, common, so_host, cpp), "libcnpatch.so")

    # ---------- 3. 合并 GXT ----------
    print("[3/5] 合并 GXT")
    import merge_missing
    official, _ = merge_missing.load_gxt(cfg["american_gxt"])
    chinese, _ = merge_missing.load_gxt(cfg["chinese_gxt"])

    merged, added = {}, 0
    for name, off_entries in official.items():
        zh = chinese.get(name, {})
        m = dict(zh)
        for h, t in off_entries.items():
            if h not in zh:
                m[h] = t
                added += 1
        merged[name] = m
    for name, zh in chinese.items():
        merged.setdefault(name, dict(zh))

    order = list(official.keys()) + [n for n in merged if n not in official]
    gxt_out = os.path.join(OUT, "japanese.gxt")
    with open(gxt_out, "wb") as fh:
        fh.write(merge_missing.build_android_gxt(merged, order))
    print("  补入 %d 条，合计 %d 条 -> japanese.gxt"
          % (added, sum(len(v) for v in merged.values())))

    # ---------- 4. 字形图集 ----------
    print("[4/5] 生成字形图集")
    import make_font
    # 让 make_font 用合并后的 GXT 决定码位集合
    os.environ["CN_GXT"] = gxt_out
    sys.argv = ["make_font.py", cfg["font"], str(cfg.get("font_face_index", 0)),
                OUT, str(cfg.get("font_size", 30))]
    make_font.main()

    maptable = os.path.join(OUT, "maptable.bin")
    if not os.path.exists(maptable):
        die("没有生成 maptable.bin")

    # ---------- 5. 打补丁 ----------
    print("[5/5] 打补丁到 libGTASA.so")
    import repack_full
    so_out = os.path.join(OUT, "libGTASA.so")
    shutil.copy(cfg["libGTASA_so"], os.path.join(BUILD, "src.so"))
    sys.argv = ["repack_full.py", maptable, so_out]
    repack_full.SRC_SO = os.path.join(BUILD, "src.so")
    repack_full.OBJ_STASH = objs["cn_stash"]
    repack_full.OBJ_IDX2 = objs["cn_idx2"]
    repack_full.OBJ_WIDTH = objs["cn_width"]
    repack_full.main()

    print()
    print("构建完成，产物在 %s:" % OUT)
    for f in sorted(os.listdir(OUT)):
        print("  %-24s %8d 字节" % (f, os.path.getsize(os.path.join(OUT, f))))
    print()
    print("部署方法见 README.md")


if __name__ == "__main__":
    main()
