#!/usr/bin/env python3
import sys
import struct
from elftools.elf.elffile import ELFFile
from elftools.elf.constants import P_FLAGS

def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <input.elf> <output.mem>")
        sys.exit(1)
        
    in_file = sys.argv[1]
    out_file = sys.argv[2]
    
    with open(in_file, 'rb') as f_in, open(out_file, 'wb') as f_out:
        elf = ELFFile(f_in)
        
        # Write magic "UADL"
        f_out.write(b'UADL')
        
        for segment in elf.iter_segments():
            if segment['p_type'] == 'PT_LOAD':
                vaddr = segment['p_vaddr']
                memsz = segment['p_memsz']
                filesz = segment['p_filesz']
                
                if memsz == 0:
                    continue
                
                # Exclude the segment that just loads the ELF headers (often mapped at 0 with no sections)
                # We can detect it if it has no sections mapped to it, or if it explicitly maps the ELF header
                # A safer way: if the segment starts at file offset 0 and vaddr 0, it's the header segment.
                # However, the .text segment usually starts at file offset > 0 (e.g. 0x10000).
                if segment['p_offset'] == 0 and filesz > 0:
                    # Check if this segment actually contains any sections
                    has_sections = False
                    for sec in elf.iter_sections():
                        if segment.section_in_segment(sec):
                            has_sections = True
                            break
                    if not has_sections:
                        continue
                    
                data = segment.data()
                # Pad with zeros if bss (memsz > filesz)
                if memsz > filesz:
                    data += b'\x00' * (memsz - filesz)
                    
                # Write vaddr (uint32) and size (uint32)
                f_out.write(struct.pack('<I', vaddr))
                f_out.write(struct.pack('<I', memsz))
                # Write data
                f_out.write(data)
                
        print(f"Extracted PT_LOAD segments to {out_file}")

if __name__ == '__main__':
    main()
