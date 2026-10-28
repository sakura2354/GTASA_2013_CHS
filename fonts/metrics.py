#!/usr/bin/env python3
"""METRICS1（GTA:SA Android 字形度量文件）读写。

格式（实测自 assets/Textures/fonts/JapaneseFont.met，1675 条）：

    METRICS1
    <字体名>              e.g. JapaneseFont
    <N>                   e.g. 5      —— 每行的字段数（实际行里有 5 个数）
    <code> <x0> <y0> <x1> <y1>
    ...

引擎侧的解析（`ReadMetFile` @0x5b7d98）：
    sscanf(line, "%d %d %d %d %d", &code, &x0, &y0, &x1, &y1)
    记录 0x30 字节：
        +0x04 u16  code
        +0x08 f32  x0 / sheetSize     UV 左上
        +0x0c f32  y0 / sheetSize
        +0x10 f32  x1 / sheetSize
        +0x14 f32  y0 / sheetSize
        +0x18 f32  x0 / sheetSize
        +0x1c f32  y1 / sheetSize
        +0x20 f32  x1 / sheetSize
        +0x24 f32  y1 / sheetSize
        +0x28 s32  width  = x1 - x0   ← advance
        +0x2c s32  height = y1 - y0
    sheetSize 由 `AddJapaneseTexture` 传入的 0x400 (=1024) 决定。

注意：引擎按 code 线性扫描匹配，所以行序不重要；但 code 必须与 GXT 里
实际出现的 UTF-16 码元完全一致。
"""


class Metrics:
    def __init__(self, name="JapaneseFont", field_count=5):
        self.name = name
        self.field_count = field_count
        self.rows = []          # list of (code, x0, y0, x1, y1)

    # ---------------------------------------------------------------- 读

    @classmethod
    def load(cls, path):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            raw = fh.read()
        lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
        if not lines or lines[0].strip() != "METRICS1":
            raise SystemExit("不是 METRICS1 文件: %s" % path)

        # 第二行是字体名，第三行是每行字段数
        m = cls(name=lines[1].strip(), field_count=int(lines[2].strip()))
        for ln in lines[3:]:
            parts = ln.split()
            if len(parts) < 5:
                continue
            try:
                code, x0, y0, x1, y1 = (int(p) for p in parts[:5])
            except ValueError:
                continue
            m.rows.append((code, x0, y0, x1, y1))
        return m

    # ---------------------------------------------------------------- 写

    def dumps(self):
        out = ["METRICS1", self.name, str(self.field_count)]
        for code, x0, y0, x1, y1 in self.rows:
            out.append("%5d %4d %4d %4d %4d" % (code, x0, y0, x1, y1))
        return "\n".join(out) + "\n"

    def save(self, path):
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(self.dumps())

    # ---------------------------------------------------------------- 便捷

    def by_code(self):
        return {r[0]: r[1:] for r in self.rows}

    def extent(self):
        """返回所有矩形的最大 x1 / y1，用于校验是否落在图集内。"""
        mx = max((r[3] for r in self.rows), default=0)
        my = max((r[4] for r in self.rows), default=0)
        return mx, my
