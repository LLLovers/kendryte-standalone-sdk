OUTPUT_ARCH(riscv)
ENTRY(_start)
MEMORY {
    image (rwx) : ORIGIN = 0x80000000, LENGTH = 256K
    data (rw) : ORIGIN = 0x80080000, LENGTH = 128K
}
SECTIONS {
    .text : { KEEP(*(.text.start)) *(.text .text.*) *(.init) *(.fini) } > image
    .rodata : { *(.rodata .rodata.* .srodata .srodata.*) } > image
    .preinit_array : ALIGN(8) {
        __preinit_array_start = .; KEEP(*(.preinit_array)) __preinit_array_end = .;
    } > image
    .init_array : ALIGN(8) {
        __init_array_start = .; KEEP(*(SORT_BY_INIT_PRIORITY(.init_array.*)))
        KEEP(*(.init_array)) __init_array_end = .;
    } > image
    .fini_array : ALIGN(8) {
        __fini_array_start = .; KEEP(*(SORT_BY_INIT_PRIORITY(.fini_array.*)))
        KEEP(*(.fini_array)) __fini_array_end = .;
    } > image
    .data : ALIGN(8) {
        _data = .; __global_pointer$ = . + 0x800;
        *(.data .data.* .sdata .sdata.*) _edata = .;
    } > data AT> image
    _data_lma = LOADADDR(.data);
    .bss (NOLOAD) : ALIGN(8) {
        _bss = .; *(.bss .bss.* .sbss .sbss.* COMMON) . = ALIGN(8); _ebss = .;
    } > data
    .retained (NOLOAD) : ALIGN(64) { KEEP(*(.retained)) } > data
    . = ALIGN(64);
    _end = .;
    _tp0 = .; _sp0 = _tp0 + 4096;
    _tp1 = _sp0; _sp1 = _tp1 + 8192;
    _heap_start = _sp1; _heap_end = ORIGIN(data) + LENGTH(data);
}
ASSERT(_heap_start <= _heap_end, "Stacks/heap overflow")
