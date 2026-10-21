cmake_minimum_required(VERSION 3.25)
include(k210_sdk_import.cmake)
project(sdk_consumer LANGUAGES C CXX ASM)
k210_sdk_init()
k210_sdk_init() # Public entry is intentionally idempotent.

add_executable(default_map main.cpp)
target_link_libraries(default_map PRIVATE k210_stdlib)
k210_add_extra_outputs(default_map)
k210_add_extra_outputs(default_map)
add_executable(custom_map main.cpp)
target_link_libraries(custom_map PRIVATE k210_stdlib)
k210_set_linker_script(custom_map "${CMAKE_CURRENT_SOURCE_DIR}/memory.ld"
    DEPENDS "${CMAKE_CURRENT_SOURCE_DIR}/layout-note.ld")
k210_add_extra_outputs(custom_map)

add_executable(relocated main.cpp)
target_link_libraries(relocated PRIVATE k210_stdlib)
target_compile_definitions(relocated PRIVATE TEST_RETAINED=1)
k210_set_linker_script(relocated "${CMAKE_CURRENT_SOURCE_DIR}/relocated.ld")
k210_add_extra_outputs(relocated)

# Keep every function in the selected archive to expose missing dependencies.
foreach(driver aes apu clint dmac dvp fft fpioa gpio gpiohs i2c i2s kpu plic pwm
               rtc sha256 spi sysctl timer uart uarths utils wdt)
    add_executable(driver_${driver} empty.c)
    target_link_libraries(driver_${driver} PRIVATE
        -Wl,--whole-archive k210_hardware_${driver} -Wl,--no-whole-archive
        k210_stdlib -Wl,--no-gc-sections)
endforeach()
add_executable(with_locks empty.c)
target_link_libraries(with_locks PRIVATE k210_stdlib
    -Wl,--whole-archive k210_newlib_locks -Wl,--no-whole-archive)

add_executable(missing_symbols EXCLUDE_FROM_ALL empty.c)
target_link_libraries(missing_symbols PRIVATE k210_stdlib)
k210_set_linker_script(missing_symbols "${CMAKE_CURRENT_SOURCE_DIR}/missing.ld")
add_executable(overflow EXCLUDE_FROM_ALL empty.c)
target_link_libraries(overflow PRIVATE k210_stdlib)
k210_set_linker_script(overflow "${CMAKE_CURRENT_SOURCE_DIR}/overflow.ld")
