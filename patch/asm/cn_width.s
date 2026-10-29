@ cn_width.s - GetJapaneseWidth 的替代：按码位返回字宽
@
@ 为什么需要这个桩：
@   PrintChar 的 CJK 分支调用 GetJapaneseWidth 取"字宽"，而它拿到的是已被
@   改写过的码位，算不出正确宽度，结果文字被推到屏幕外。
@
@ 这个返回值同时决定两件事：
@   1. 水平步进（advance）
@   2. 字形四边形的宽度 —— PrintChar 里：
@         右边界 = C * (返回值 * k) * CFontScale * screenScale + 左边界
@      高度来自 CFont+0x10 的字体尺寸，与本值无关。
@
@ 为什么用 r0 而不是共享暂存槽：
@   GetJapaneseWidth 不只被 PrintChar 调用（排版/测宽也会调）。
@   如果从 cn_stash 的槽里取码位，在这些调用点读到的是**上一个字符的旧值**，
@   宽度会随机变化，表现就是字符位置乱跳。
@   而本函数的第一个参数 r0 就是调用方传进来的码位，直接用即可。
@
@ 两个常量由构建脚本替换（搜索 0x42000000 / 0x41800000）。

    .syntax unified
    .thumb
    .text

    .global cn_width
    .thumb_func
    .type   cn_width, %function
cn_width:
    cmp     r0, #0x80                @ r0 = 码位（调用方直接传入）
    blo     ascii

    ldr     r0, wide_lit             @ CJK / 全角
    bx      lr

ascii:
    ldr     r0, narrow_lit           @ 拉丁 / 数字 / 半角
    bx      lr

    .balign 4
wide_lit:
    .word   0x42000000               @ 32.0f —— CJK 字宽（构建脚本替换）
narrow_lit:
    .word   0x41800000               @ 16.0f —— ASCII 字宽（构建脚本替换）

    .size   cn_width, . - cn_width
