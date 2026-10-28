@ cn_stash.s - PrintChar 入口：把「码位-0x20」暂存到 .bss 空隙
@
@ 之前直接在入口改写 r2，虽然索引对了，但 PrintChar 内部还有别的判断依赖原始码位，
@ 结果文字整个不显示。改成只「暂存」不动 r2，让原函数按原样跑，
@ 到索引算出来之后再改写（见 cn_idx2.s）。
@
@ 暂存槽 0x6B2DA0：位于 .data 末尾(0x6B2D85)与 .bss 起始(0x6B2DC0)之间的空隙，
@ 不属于任何符号，且已在 RW 段内映射。
@
@ 只用 r4/r5（callee-saved，用后恢复），r0-r3 完全不碰。

    .syntax unified
    .thumb
    .text

    .equ SLOT_VADDR, 0x6B2DA0
    .equ CAVE_ADDR,  0xAA8000

    .global cn_stash
    .thumb_func
    .type   cn_stash, %function
cn_stash:
    push    {r4, r5}
    adr     r4, cn_stash
    ldr     r5, slot_delta
    add     r5, r5, r4
    str     r2, [r5]                @ 存 码位 - 0x20
    pop     {r4, r5}

    @ 重放被替换掉的 12 字节序言
    .byte   0xf0, 0xb5, 0x03, 0xaf
    .byte   0x4d, 0xf8, 0x04, 0x8d
    .byte   0x2d, 0xed, 0x0c, 0x8b

    b.w     resume_stash

    .balign 4
slot_delta:
    .word   (SLOT_VADDR - CAVE_ADDR)

    .balign 4
resume_stash:
    @ <<< 打包脚本在此追加 B.W -> 0x5A8A94 >>>

    .size   cn_stash, . - cn_stash
