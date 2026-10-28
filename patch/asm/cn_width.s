@ cn_width.s - 让 GetJapaneseWidth 恒定返回 20.0
@
@ 为什么需要：
@   PrintChar 的桩会把码位改写成 0x7FE0+下标，好让引擎的直接索引命中我们的记录。
@   但 GetJapaneseWidth 拿到的也是这个改写后的码位，它算不出正确字宽，
@   结果文字被推到屏幕外（实测：标题屏文字完全消失）。
@
@   中文是等宽排版，直接恒定返回 20.0 即可，同时绕开了宽度查找。
@
@ 返回约定：softfp，float 通过 r0 返回位模式。20.0f = 0x41A00000

    .syntax unified
    .thumb
    .text

    .global cn_width
    .thumb_func
    .type   cn_width, %function
cn_width:
    movw    r0, #0x0000
    movt    r0, #0x41A0
    bx      lr

    .size   cn_width, . - cn_width
