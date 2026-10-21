add_library(k210_headers INTERFACE)
target_include_directories(k210_headers INTERFACE
    "${CMAKE_CURRENT_SOURCE_DIR}/bsp/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/drivers/include"
    "${CMAKE_CURRENT_SOURCE_DIR}/utils/include")
add_library(k210_platform INTERFACE)
target_link_libraries(k210_platform INTERFACE k210_headers)
target_compile_definitions(k210_platform INTERFACE __riscv64)
target_compile_options(k210_platform INTERFACE
    -march=rv64imafc -mabi=lp64f -mcmodel=medany
    $<$<COMPILE_LANGUAGE:C,CXX>:-mstrict-align;-fno-common;-ffunction-sections;-fdata-sections;-fstrict-volatile-bitfields>)
target_link_options(k210_platform INTERFACE -march=rv64imafc -mabi=lp64f -mcmodel=medany)

# Per-build SDK policy; consumers can extend this INTERFACE target.
add_library(k210_sdk_config INTERFACE)
option(K210_ENABLE_DIAGNOSTIC_LOGGING "Enable BSP diagnostic printing" ON)
option(K210_ENABLE_FAULT_HOOK "Call k210_record_misaligned_fault on fatal unaligned access" OFF)
add_library(k210_diagnostics INTERFACE)
target_compile_definitions(k210_diagnostics INTERFACE
    K210_ENABLE_DIAGNOSTIC_LOGGING=$<BOOL:${K210_ENABLE_DIAGNOSTIC_LOGGING}>
    K210_ENABLE_FAULT_HOOK=$<BOOL:${K210_ENABLE_FAULT_HOOK}>
    $<IF:$<BOOL:${K210_ENABLE_DIAGNOSTIC_LOGGING}>,CONFIG_LOG_LEVEL=LOG_VERBOSE,CONFIG_LOG_LEVEL=LOG_NONE>
    $<$<BOOL:${K210_ENABLE_DIAGNOSTIC_LOGGING}>:CONFIG_LOG_ENABLE;CONFIG_LOG_COLORS;LOG_KERNEL>)
function(k210_sdk_library target)
    target_link_libraries(${target} PUBLIC k210_platform PRIVATE k210_sdk_config k210_diagnostics)
    set_target_properties(${target} PROPERTIES C_STANDARD 11 C_STANDARD_REQUIRED YES
        INTERPROCEDURAL_OPTIMIZATION FALSE)
    # Trap declarations are ABI-compatible, but not C-type-compatible.
    target_compile_options(${target} PRIVATE $<$<COMPILE_LANGUAGE:C,CXX>:-fno-lto>)
endfunction()
set(drivers aes apu clint dmac dvp fft fpioa gpio gpiohs i2c i2s kpu plic pwm rtc
    sha256 spi sysctl timer uart uarths utils wdt)
foreach(driver IN LISTS drivers)
    add_library(k210_hardware_${driver} STATIC "drivers/${driver}.c")
    k210_sdk_library(k210_hardware_${driver})
endforeach()
include("${K210_SDK_PATH}/cmake/driver_dependencies.cmake")
add_library(k210_runtime OBJECT bsp/crt.S bsp/entry.c bsp/entry_user.c
    bsp/interrupt.c bsp/printf.c bsp/sleep.c bsp/syscalls.c)
k210_sdk_library(k210_runtime)
add_library(k210_newlib_locks STATIC bsp/locks.c)
k210_sdk_library(k210_newlib_locks)

add_library(k210_linker_script INTERFACE)
set(script "$<IF:$<BOOL:$<TARGET_PROPERTY:K210_LINKER_SCRIPT>>,$<TARGET_PROPERTY:K210_LINKER_SCRIPT>,${K210_SDK_PATH}/lds/kendryte.ld>")
target_link_options(k210_linker_script INTERFACE "LINKER:-T,${script}")
set_property(TARGET k210_linker_script PROPERTY INTERFACE_LINK_DEPENDS
    "${script};$<TARGET_PROPERTY:K210_LINKER_SCRIPT_DEPENDS>")
add_library(k210_stdlib INTERFACE)
target_link_libraries(k210_stdlib INTERFACE k210_platform k210_diagnostics k210_linker_script
    k210_hardware_clint k210_hardware_fpioa k210_hardware_plic
    k210_hardware_sysctl k210_hardware_uart k210_hardware_uarths)
target_sources(k210_stdlib INTERFACE $<TARGET_OBJECTS:k210_runtime>)
target_link_options(k210_stdlib INTERFACE -nostartfiles -static
    "LINKER:--gc-sections" "LINKER:--no-relax" "LINKER:-EL")
# Keep CRT objects target-local: independent loaders need no C runtime.
foreach(crt crti crtbegin crtend crtn)
    execute_process(COMMAND "${CMAKE_C_COMPILER}" -march=rv64imafc -mabi=lp64f
        "-print-file-name=${crt}.o" OUTPUT_VARIABLE crt_path
        OUTPUT_STRIP_TRAILING_WHITESPACE COMMAND_ERROR_IS_FATAL ANY)
    if(NOT EXISTS "${crt_path}")
        message(FATAL_ERROR "Compiler is missing ${crt}.o: ${crt_path}")
    endif()
    if(crt STREQUAL "crti" OR crt STREQUAL "crtbegin")
        target_sources(k210_stdlib INTERFACE "${crt_path}")
    else()
        target_link_libraries(k210_stdlib INTERFACE "${crt_path}")
    endif()
endforeach()
target_link_libraries(k210_stdlib INTERFACE "$<LINK_GROUP:RESCAN,c,m,gcc>")
add_custom_target(k210_all_drivers)
foreach(driver IN LISTS drivers)
    add_dependencies(k210_all_drivers k210_hardware_${driver})
endforeach()
