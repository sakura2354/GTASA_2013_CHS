@ cn_idx2.s - 在「索引已算出」之后把它换成我们的记录下标
@
@ 插桩点：ELF 0x5A8EB4 的 `add.w r0,r0,r0,lsl #1`
@   此时 r0 = 引擎算出的字形记录索引（扫描命中值，或默认 32）
@   下一条 0x5A8EB8 开始用 r0 计算记录指针
@
@ 与之前「在入口改码位」的区别：
@   入口改码位会破坏 PrintChar 内部其它依赖原始码位的判断，实测导致文字完全不显示。
@   这里原始码位从未被改动，只替换最终的记录索引。
@
@ 码位由 cn_stash 在入口暂存到 0x6B2DA0。
@
@ 必须保持 r1/r2/r3：0x5A8EB2 刚把 r1 设为字面量指针，后续 0x5A8EBA 还要 add r1,pc。
@ r0 是我们要改写的，故意不保存。

    .syntax unified
    .thumb
    .text

    .equ SLOT_VADDR,  0x6B2DA0
    .equ TABLE_ADDR,  0xAA8C00
    .equ TABLE_MAX,   0xFFFF
    .equ CAVE_ADDR,   0xAA8200

    .global cn_idx2
    .thumb_func
    .type   cn_idx2, %function
cn_idx2:
    push    {r1, r2, r3, r4, r5, lr}

    adr     r4, cn_idx2
    ldr     r5, slot_delta
    add     r5, r5, r4               @ r5 = 暂存槽地址
    ldr     r2, [r5]                 @ r2 = 码位 - 0x20
    cbz     r2, keep                 @ 0 表示没有存过，保持原索引

    uxth    r3, r2
    movw    r5, #(TABLE_MAX & 0xFFFF)
    cmp     r3, r5
    bhi     keep

    ldr     r5, table_delta
    add     r5, r5, r4               @ r5 = 映射表地址
    add     r3, r3, r3
    ldrh    r5, [r5, r3]             @ r5 = 下标 + 1
    cbz     r5, keep
    subs    r0, r5, #1               @ r0 = 我们的记录下标

keep:
    pop     {r1, r2, r3, r4, r5, lr}

    @ 重放被替换掉的 `add.w r0,r0,r0,lsl #1`
    add.w   r0, r0, r0, lsl #1

    b.w     resume_idx2

    .balign 4
slot_delta:
    .word   (SLOT_VADDR - CAVE_ADDR)
    .balign 4
table_delta:
    .word   (TABLE_ADDR - CAVE_ADDR)

    .balign 4
resume_idx2:
    @ <<< 打包脚本在此追加 B.W -> 0x5A8EB8 >>>

    .size   cn_idx2, . - cn_idx2
