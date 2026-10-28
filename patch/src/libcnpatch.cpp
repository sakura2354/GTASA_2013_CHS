// libcnpatch.so - 扩大字形记录数组容量
//
// 背景：
//   引擎的字形记录数组 JMet 是 .bss 里一块固定 86,400 字节的符号
//   （= 1800 条 × 0x30），紧跟其后就是 jCount 和 CFont 的几个语言标志。
//   所以直接在原数组里塞更多记录会踩坏相邻全局。
//
// 做法：
//   ReadMetFile 每次调用时才从 GOT 槽 (libGTASA+0x676924) 读数组基址。
//   本库在 constructor（远早于 ReadMetFile）里把该槽换成 malloc 出来的大数组，
//   于是 ReadMetFile 后续就把记录写进我们的数组，容量不再受 1800 限制。
//   配合把上限立即数 0x706 放宽，即可容纳全部字形。
//
// GOT 槽位于 RELRO 段，加载后只读，写之前需要 mprotect 成可写。

#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>
#include <sys/mman.h>
#include <android/log.h>

#define TAG "cnpatch"
#define LOGI(...) __android_log_print(ANDROID_LOG_INFO,  TAG, __VA_ARGS__)
#define LOGE(...) __android_log_print(ANDROID_LOG_ERROR, TAG, __VA_ARGS__)

#define OFF_RECBASE 0x00676924u
#define REC_SIZE    0x30
#define REC_COUNT   4096

static uintptr_t find_module_base(const char *name) {
    FILE *f = fopen("/proc/self/maps", "r");
    if (!f) return 0;
    char line[512];
    uintptr_t base = 0;
    while (fgets(line, sizeof(line), f)) {
        if (!strstr(line, name)) continue;
        uintptr_t start = (uintptr_t)strtoul(line, NULL, 16);
        if (base == 0 || start < base) base = start;
    }
    fclose(f);
    return base;
}

__attribute__((constructor))
static void cn_init(void) {
    LOGI("libcnpatch loaded (pid=%d)", getpid());

    uintptr_t base = find_module_base("libGTASA.so");
    if (!base) { LOGE("libGTASA.so not found"); return; }

    size_t bytes = (size_t)REC_SIZE * REC_COUNT;
    void *arr = calloc(1, bytes);
    if (!arr) { LOGE("calloc(%zu) failed", bytes); return; }
    LOGI("new glyph array @ %p (%zu bytes = %d records)", arr, bytes, REC_COUNT);

    void **slot = (void **)(base + OFF_RECBASE);
    long ps = sysconf(_SC_PAGESIZE);
    if (ps <= 0) ps = 4096;
    void *page = (void *)((uintptr_t)slot & ~((uintptr_t)ps - 1));
    if (mprotect(page, (size_t)ps, PROT_READ | PROT_WRITE) != 0) {
        LOGE("mprotect failed errno=%d", errno);
        free(arr);
        return;
    }
    LOGI("old value = %p", *slot);
    *slot = arr;
    LOGI("new value = %p", *slot);
}
