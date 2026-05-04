#!/usr/bin/env python3
"""ELF → flat UADL memory image.

Also emits a sidecar `<output>.symtab.json` mapping each instruction PC to its
source `(file, line)` if the ELF carries DWARF debug info (compile with `-g`).
This sidecar drives Phase D's per-line telemetry annotation.
"""
import json
import os
import sys
import struct
from elftools.elf.elffile import ELFFile


def emit_symtab(elf, sidecar_path):
    """Walk DWARF .debug_line and produce a {pc_hex: [file, line]} map."""
    if not elf.has_dwarf_info():
        return False
    dwarf = elf.get_dwarf_info()
    pc_to_loc = {}
    for cu in dwarf.iter_CUs():
        lp = dwarf.line_program_for_CU(cu)
        if lp is None:
            continue
        file_entries = lp['file_entry']
        for entry in lp.get_entries():
            state = entry.state
            if state is None or state.end_sequence:
                continue
            file_idx = state.file
            # DWARF v2/3 uses 1-based; v5 uses 0-based.
            try:
                fe = file_entries[file_idx - 1] if file_idx > 0 else file_entries[file_idx]
            except IndexError:
                continue
            fname = fe.name.decode('utf-8', errors='replace') if isinstance(fe.name, bytes) else fe.name
            pc_to_loc[f"0x{state.address:08x}"] = [fname, state.line]
    if not pc_to_loc:
        return False
    with open(sidecar_path, 'w') as f:
        json.dump(pc_to_loc, f, separators=(',', ':'))
    return True


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.elf> <output.mem>")
        sys.exit(1)

    in_file = sys.argv[1]
    out_file = sys.argv[2]

    with open(in_file, 'rb') as f_in, open(out_file, 'wb') as f_out:
        elf = ELFFile(f_in)

        f_out.write(b'UADL')

        for segment in elf.iter_segments():
            if segment['p_type'] != 'PT_LOAD':
                continue
            vaddr = segment['p_vaddr']
            memsz = segment['p_memsz']
            filesz = segment['p_filesz']

            if memsz == 0:
                continue

            # Skip the ELF-header-only segment (vaddr 0, no sections).
            if segment['p_offset'] == 0 and filesz > 0:
                has_sections = any(
                    segment.section_in_segment(sec) for sec in elf.iter_sections()
                )
                if not has_sections:
                    continue

            data = segment.data()
            if memsz > filesz:
                data += b'\x00' * (memsz - filesz)

            f_out.write(struct.pack('<I', vaddr))
            f_out.write(struct.pack('<I', memsz))
            f_out.write(data)

        print(f"Extracted PT_LOAD segments to {out_file}")

        sidecar = out_file + '.symtab.json'
        if emit_symtab(elf, sidecar):
            print(f"Symtab sidecar: {sidecar}")
        elif os.path.exists(sidecar):
            os.remove(sidecar)


if __name__ == '__main__':
    main()
