#!/usr/bin/env python3
"""Build independent consumers and execute startup in Unicorn (no board needed)."""
import argparse
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile

from elftools.elf.elffile import ELFFile
from unicorn import Uc, UC_ARCH_RISCV, UC_MODE_RISCV64, UC_HOOK_CODE
from unicorn.riscv_const import (
    UC_RISCV_REG_PC, UC_RISCV_REG_X0, UC_RISCV_REG_MHARTID,
)


def run(*args, success=True):
    result = subprocess.run([str(a) for a in args], text=True, capture_output=True)
    if (result.returncode == 0) != success:
        raise AssertionError(f"Command: {args}\n{result.stdout}\n{result.stderr}")
    return result.stdout + result.stderr


def elf_image(path):
    with path.open('rb') as stream:
        elf = ELFFile(stream)
        symbols = {s.name: s['st_value'] for s in elf.get_section_by_name('.symtab').iter_symbols()}
        segments = [(s['p_paddr'], s.data()) for s in elf.iter_segments()
                    if s['p_type'] == 'PT_LOAD']
        return symbols, segments


def startup(path, stack_sizes, relocated=False):
    symbols, segments = elf_image(path)
    for hart in (0, 1):
        cpu = Uc(UC_ARCH_RISCV, UC_MODE_RISCV64)
        cpu.mem_map(0x80000000, 0x600000)
        for address, data in segments:
            cpu.mem_write(address, data)
        # Emulate a loader that fills only the load image, not destination BSS.
        bss_size = symbols['_ebss'] - symbols['_bss']
        cpu.mem_write(symbols['_bss'], b'\xa5' * bss_size)
        if relocated:
            assert symbols['_data'] != symbols['_data_lma']
            cpu.mem_write(symbols['_data'], b'\xcc' * (symbols['_edata'] - symbols['_data']))
            cpu.mem_write(symbols['retained'], b'RETAINED')
        sentinel = 0x805fff00
        cpu.mem_write(sentinel, b'RESERVED')
        cpu.reg_write(UC_RISCV_REG_MHARTID, hart)
        entered, main_reached = [], []
        # Peripheral initialization is outside this memory/startup contract.
        skipped = {symbols[n] for n in ('fpioa_set_function', 'uart_debug_init',
                   'fpioa_init', 'atexit', 'sysctl_get_reset_status', 'plic_init') if n in symbols}

        def code(uc, address, size, _):
            # Unicorn exposes mhartid as read-only zero. Supply the second hart
            # at the CSR instruction, leaving all actual stack setup executed.
            if size == 4 and bytes(uc.mem_read(address, 4)) == b'\x73\x25\x40\xf1':
                uc.reg_write(UC_RISCV_REG_X0 + 10, hart)
                uc.reg_write(UC_RISCV_REG_PC, address + 4)
                return
            if address == symbols['_init_bsp']:
                entered.append((uc.reg_read(UC_RISCV_REG_X0 + 2),
                                uc.reg_read(UC_RISCV_REG_X0 + 4)))
                if hart == 1:
                    # Run the secondary wait loop, checking it leaves BSS alone.
                    return
            if address in skipped:
                uc.reg_write(UC_RISCV_REG_X0 + 10, 0)
                uc.reg_write(UC_RISCV_REG_PC, uc.reg_read(UC_RISCV_REG_X0 + 1))
            elif address == symbols['main']:
                main_reached.append(True)
                uc.emu_stop()

        cpu.hook_add(UC_HOOK_CODE, code)
        cpu.emu_start(symbols['_start'], 0, count=300000)
        assert entered == [(symbols[f'_sp{hart}'], symbols[f'_tp{hart}'])], (hart, entered)
        assert symbols[f'_sp{hart}'] - symbols[f'_tp{hart}'] == stack_sizes[hart]
        assert cpu.mem_read(sentinel, 8) == b'RESERVED'
        if relocated:
            assert cpu.mem_read(symbols['retained'], 8) == b'RETAINED'
        if hart == 0:
            assert main_reached, hex(cpu.reg_read(UC_RISCV_REG_PC))
            value = lambda n: struct.unpack('<Q', cpu.mem_read(symbols[n], 8))[0]
            assert value('zeroed') == 0
            assert value('initialized') == 0x123456789abcdef0
            assert value('constructed') == 0x123456789abcdef0
        else:
            assert not main_reached
            assert cpu.mem_read(symbols['_bss'], bss_size) == b'\xa5' * bss_size
    print(f'PASS startup: {path.name}, stacks={stack_sizes}, relocated={relocated}', flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--sdk', type=Path, required=True)
    parser.add_argument('--toolchain', type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='k210 sdk contract ') as temp:
        root = Path(temp)
        source, build = root/'consumer', root/'build'
        shutil.copytree(Path(__file__).parent/'fixture', source)
        shutil.copy(args.sdk/'external/k210_sdk_import.cmake', source)
        custom = (args.sdk/'examples/memory.ld').read_text()
        (source/'memory.ld').write_text(custom)
        (source/'layout-note.ld').write_text('/* Explicit extra linker dependency. */\n')
        (source/'missing.ld').write_text(custom.replace('_sp1', '_missing_sp1'))
        (source/'overflow.ld').write_text(custom.replace('(2 * 1024 * 1024)', '64'))
        run('cmake', '-S', source, '-B', build, '-G', 'Ninja',
            f'-DK210_SDK_PATH={args.sdk}', f'-DK210_TOOLCHAIN_PATH={args.toolchain}',
            '-DCMAKE_BUILD_TYPE=Release', '-DK210_ENABLE_DIAGNOSTIC_LOGGING=OFF')
        run('cmake', '--build', build, '--parallel', '8')
        print('PASS C/C++ consumers, all 23 driver dependency closures, optional locks', flush=True)
        for target in ('default_map', 'custom_map', 'relocated'):
            assert (build/f'{target}.bin').is_file()
            assert (build/f'{target}.map').is_file()
        default, _ = elf_image(build/'default_map')
        custom_symbols, _ = elf_image(build/'custom_map')
        assert default['_start'] == 0x80000000
        assert custom_symbols['_start'] == 0x80010000
        startup(build/'default_map', (32768, 32768))
        startup(build/'custom_map', (8192, 8192))
        startup(build/'relocated', (4096, 8192), relocated=True)
        for dependency in ('memory.ld', 'layout-note.ld'):
            before = {n: (build/n).stat().st_mtime_ns for n in ('default_map', 'custom_map')}
            with (source/dependency).open('a') as stream:
                stream.write('\n/* relink */\n')
            run('cmake', '--build', build, '--target', 'custom_map', 'default_map')
            assert (build/'custom_map').stat().st_mtime_ns > before['custom_map']
            assert (build/'default_map').stat().st_mtime_ns == before['default_map']
        print('PASS linker-script and DEPENDS relink only their own target', flush=True)
        error = run('cmake', '--build', build, '--target', 'missing_symbols', success=False)
        assert '_sp1' in error and 'undefined reference' in error
        error = run('cmake', '--build', build, '--target', 'overflow', success=False)
        assert 'overflow' in error or 'will not fit' in error or 'exceed RAM' in error
        error = run('cmake', '-S', source, '-B', root/'bad-path', '-G', 'Ninja',
                    f'-DK210_SDK_PATH={root}/missing', success=False)
        assert 'Set K210_SDK_PATH' in error
        print('PASS invalid SDK path, missing startup symbol, memory overflow', flush=True)


if __name__ == '__main__':
    main()
