# K210 standalone SDK

This fork builds as an external CMake SDK. It retains the SuperOctet fixes for
trap/FCSR handling, unaligned instructions, secondary-core startup, PLIC claims,
PLL1, nonblocking UARTHS writes and fatal assertions.

Requirements: CMake 3.25+, Ninja or Make, and a bare-metal
`riscv64-unknown-elf` GCC toolchain with newlib and the `rv64imafc` / `lp64f` ABI.
The current validation toolchain is GCC 16.1.0. Builds do not download dependencies.

## Use from another project

Place this checkout at `$HOME/k210-sdk`, or set `K210_SDK_PATH`. Copy
`external/k210_sdk_import.cmake` to the application next to its `CMakeLists.txt`:

```cmake
cmake_minimum_required(VERSION 3.25)
include(k210_sdk_import.cmake) # before project()
project(example LANGUAGES C CXX ASM)
k210_sdk_init()

add_executable(example main.c)
target_link_libraries(example PRIVATE k210_stdlib k210_hardware_i2s)
k210_set_linker_script(example "${CMAKE_CURRENT_LIST_DIR}/memory.ld") # optional
k210_add_extra_outputs(example)
```

```sh
cmake -S . -B build -G Ninja -DK210_SDK_PATH=/path/to/k210-sdk \
  -DK210_TOOLCHAIN_PATH=/path/to/toolchain/bin -DCMAKE_BUILD_TYPE=Release
cmake --build build
```

The SDK path is selected from the CMake variable, the environment variable, then
`$HOME/k210-sdk`. Relative paths are relative to the consuming source directory.
Compiler selection uses `K210_TOOLCHAIN_PATH` (CMake, then environment), the legacy
`TOOLCHAIN` (CMake, then environment), then `PATH`. Explicit compiler paths must
contain all required RISC-V tools. Use a new build directory when changing SDK or
toolchain. The SDK does not replace the selected Ninja/Make program.

`k210_sdk_init()` may be called repeatedly. SDK objects are built in the consuming
build tree, never in the checkout. All libraries use the same SDK policy within a
build; use separate build directories for different SDK compilation policies.
Each executable can independently select its linker script.

## Targets and build policy

- `k210_stdlib`: startup, traps, syscalls, C runtime objects and required base
  peripherals. It supplies the default memory map, ABI and link options. An
  ordinary C++ target uses the C++ linker and runtime automatically.
- `k210_hardware_<driver>`: `aes`, `apu`, `clint`, `dmac`, `dvp`, `fft`, `fpioa`,
  `gpio`, `gpiohs`, `i2c`, `i2s`, `kpu`, `plic`, `pwm`, `rtc`, `sha256`, `spi`,
  `sysctl`, `timer`, `uart`, `uarths`, `utils`, `wdt`. Dependencies are transitive;
  only selected libraries and their dependencies are compiled.
- `k210_headers`: include paths only, suitable for independent loaders or host
  header tests. Host projects can use their own include paths without importing
  the cross toolchain.
- `k210_platform`: headers, ISA/ABI and basic compilation settings, with no startup
  or memory-map policy.
- `k210_newlib_locks`: optional vendor newlib locks; not included by `k210_stdlib`.
- `k210_sdk_config`: an INTERFACE target for consumer-provided SDK compile options
  and definitions. For example, `target_compile_options(k210_sdk_config INTERFACE
  -Ofast -fno-allow-store-data-races)`. Application policy remains on application
  targets. SDK sources are excluded from LTO because of the BSP trap declarations.

`K210_ENABLE_DIAGNOSTIC_LOGGING` defaults ON and controls SDK log/assert printing.
Assertions always evaluate their condition and halt on failure, including when
printing is disabled. `K210_ENABLE_FAULT_HOOK` defaults OFF. When enabled, the
application must implement the following non-returning callback from `syscalls.h`:

```c
void k210_record_misaligned_fault(uintptr_t cause, uintptr_t epc,
                                uintptr_t regs[32]);
```

It runs only when an unaligned access cannot be recovered. SDK headers/source do
not depend on Helios-specific definitions or symbols. Set SDK options before
`k210_sdk_init()`.

`k210_add_extra_outputs(target)` creates `<output-name>.bin` and
`<output-name>.map` beside the ELF, including separate configuration directories
when using a multi-configuration generator. It does not rename the ELF target.
Call it in the directory that defines the executable.

## Memory maps and startup contract

The default `lds/kendryte.ld` uses 6 MiB of cached CPU SRAM from `0x80000000` and
two 32 KiB stack windows, with the remaining RAM available as heap. AI SRAM is
not allocated. Cached and uncached addresses describe the same physical CPU RAM;
applications must avoid overlapping physical allocations through the aliases.

`k210_set_linker_script(target script [DEPENDS additional.ld ...])` completely
replaces the default for that target. Paths are resolved relative to the calling
source directory. The script and explicit dependencies trigger relinking under
Ninja and Make. List included scripts in `DEPENDS`; include-file paths/search
paths themselves remain part of your linker script/link options.

Independent loaders can combine `k210_headers`, their own startup/link options
and `k210_set_linker_script()` without inheriting the SDK C runtime.

A script using SDK startup must provide:

| Symbols/sections | Meaning |
| --- | --- |
| `ENTRY(_start)`, `KEEP(*(.text.start))` | Entry and startup code; the loader must jump to the selected entry |
| `__global_pointer$` | RISC-V global pointer |
| `_sp0`, `_sp1` | Initial stack tops, aligned to 16 bytes, separately reserved for both cores |
| `_tp0`, `_tp1` | Per-core thread-pointer bases, normally aligned to 64 bytes below the corresponding stack |
| `_data_lma`, `_data`, `_edata` | Load source and half-open destination range for initialized data |
| `_bss`, `_ebss` | Half-open zero-initialized range, aligned to 4 bytes |
| `_heap_start`, `_heap_end` | Available heap range, excluding both stacks and reserved sections |
| `__preinit_array_*`, `__init_array_*`, `__fini_array_*` | Start/end symbols and retained arrays for C/C++ initialization/finalization |

Core 0 copies data when LMA differs from VMA, clears BSS, then runs constructors.
The load image must already be in CPU-readable memory; source/destination ranges
must not overlap unless identical. Secondary-core initialization still waits for
`register_core1()`. Startup does not clear custom `NOLOAD` regions or initialize
additional data ranges. Such regions and peripheral/AI SRAM readiness belong to
the application. The thread-pointer symbols select addresses; this change does
not add a new TLS runtime.

The default script checks stack alignment, positive sizes, overlap and heap/RAM
bounds. Custom scripts must retain equivalent checks for their own layout.
`examples/memory.ld` shows a 2 MiB region starting at `0x80010000` and 8 KiB stacks.
`tests/fixture/relocated.ld` demonstrates separate data load/run addresses, unequal
stack sizes and an untouched `NOLOAD` region.

## Examples and validation

The SDK root is a convenience build for explicit example targets; the former
`PROJ`/`src/<project>` discovery and global CMake helpers are retired. The original
dual-core sample is now `examples/dual_core.c`.

```sh
cmake -S . -B build -G Ninja -DK210_TOOLCHAIN_PATH=/path/to/toolchain/bin \
  -DCMAKE_BUILD_TYPE=Release
cmake --build build --target all k210_all_drivers
```

Integration tests need a Python environment with `unicorn>=2` and `pyelftools`:

```sh
cmake -S . -B build -DK210_BUILD_TESTS=ON -DPython3_EXECUTABLE=/path/to/venv/bin/python
ctest --test-dir build --output-on-failure
```

Tests build independent C/C++ consumers in a path containing spaces, link all 23
driver dependency closures, check two independent memory maps, execute both
cores' startup and data relocation, check constructors and reserved bytes, and
verify relinking and expected failures. Peripheral initialization is stubbed in
the emulator; electrical behavior and boot transport still require hardware.
