#!/usr/bin/env python3
"""
Generate a minimal STM32H755ZI blink binary for testing.
Creates a raw binary that toggles PG12 (LD1 Green LED) at ~2Hz.

This uses the STM32H755ZI-Q memory map:
- Flash at 0x08000000 (2MB)
- DTCM RAM at 0x20000000 (128KB)
- AXI SRAM at 0x24000000 (512KB)
- RCC at 0x58024400
- GPIOG at 0x58021800
"""

import struct

# Memory map
FLASH_BASE = 0x08000000
RAM_TOP = 0x20020000  # Top of DTCM
RCC_AHB4ENR = 0x580244E0
GPIOG_MODER = 0x58021800
GPIOG_BSRR = 0x58021818

# GPIOG clock enable bit
RCC_AHB4ENR_GPIOGEN = (1 << 6)

# PG12 bit positions
LED_PIN = 12

# Generate binary (1KB should be plenty)
binary = bytearray(1024)

# === Vector Table at 0x08000000 ===
# Initial stack pointer (end of DTCM)
struct.pack_into('<I', binary, 0x00, RAM_TOP)
# Reset handler (Thumb mode = address + 1)
struct.pack_into('<I', binary, 0x04, FLASH_BASE + 0x100 + 1)

# === Reset Handler at 0x08000100 ===
# Using Thumb-2 instructions

def write_instr32(offset, hw1, hw2):
    """Write 32-bit Thumb instruction as two little-endian halfwords"""
    struct.pack_into('<HH', binary, offset, hw1, hw2)

def write_instr16(offset, opcode):
    """Write 16-bit Thumb instruction"""
    struct.pack_into('<H', binary, offset, opcode)

code_offset = 0x100

# movw r0, #0x44e0  (RCC_AHB4ENR low half)
# Encoding: 11110i1 0000 imm4... imm3 rd imm8
i = (0x44e0 >> 11) & 1
imm4 = (0x44e0 >> 12) & 0xf
imm3 = (0x44e0 >> 8) & 7
imm8 = 0x44e0 & 0xff
hw1 = 0xf240 | (i << 10) | imm4
hw2 = (imm3 << 12) | (0 << 8) | imm8
write_instr32(code_offset, hw1, hw2)
code_offset += 4

# movt r0, #0x5802  (RCC_AHB4ENR high half)
i = (0x5802 >> 11) & 1
imm4 = (0x5802 >> 12) & 0xf
imm3 = (0x5802 >> 8) & 7
imm8 = 0x5802 & 0xff
hw1 = 0xf2c0 | (i << 10) | imm4
hw2 = (imm3 << 12) | (0 << 8) | imm8
write_instr32(code_offset, hw1, hw2)
code_offset += 4

# ldr r1, [r0]
write_instr16(code_offset, 0x6801)
code_offset += 2

# orr r1, r1, #0x40  (set GPIOGEN bit)
# Encoding T3: 11110x01110x... 0xxx...  0x44 = 0100 0100
# imm8 = 0x40, imm3 = 0, i = 0, imm4 = 0, rd = 1, rn = 1
write_instr32(code_offset, 0xf441, 0x7140)
code_offset += 4

# str r1, [r0]
write_instr16(code_offset, 0x6001)
code_offset += 2

# movw r0, #0x1800  (GPIOG_MODER low half)
i = (0x1800 >> 11) & 1
imm4 = (0x1800 >> 12) & 0xf
imm3 = (0x1800 >> 8) & 7
imm8 = 0x1800 & 0xff
hw1 = 0xf240 | (i << 10) | imm4
hw2 = (imm3 << 12) | (0 << 8) | imm8
write_instr32(code_offset, hw1, hw2)
code_offset += 4

# movt r0, #0x5802  (GPIOG_MODER high half)
i = (0x5802 >> 11) & 1
imm4 = (0x5802 >> 12) & 0xf
imm3 = (0x5802 >> 8) & 7
imm8 = 0x5802 & 0xff
hw1 = 0xf2c0 | (i << 10) | imm4
hw2 = (imm3 << 12) | (0 << 8) | imm8
write_instr32(code_offset, hw1, hw2)
code_offset += 4

# ldr r1, [r0]
write_instr16(code_offset, 0x6801)
code_offset += 2

# bic r1, r1, #0x3000000 would be complex, use register instead
# For simplicity, we'll just write the mode directly (assuming reset state)
# This is risky but works for a quick test
# movw r1, #0x0001  (output mode for pin 12)
write_instr32(code_offset, 0xf241, 0x7100)
code_offset += 4

# movt r1, #0x0100  (set the upper bits for MODER12 = 01)
write_instr32(code_offset, 0xf2c1, 0x7100)
code_offset += 4

# str r1, [r0]
write_instr16(code_offset, 0x6001)
code_offset += 2

# movw r0, #0x1818  (GPIOG_BSRR low half)
i = (0x1818 >> 11) & 1
imm4 = (0x1818 >> 12) & 0xf
imm3 = (0x1818 >> 8) & 7
imm8 = 0x1818 & 0xff
hw1 = 0xf240 | (i << 10) | imm4
hw2 = (imm3 << 12) | (0 << 8) | imm8
write_instr32(code_offset, hw1, hw2)
code_offset += 4

# movt r0, #0x5802  (GPIOG_BSRR high half)
i = (0x5802 >> 11) & 1
imm4 = (0x5802 >> 12) & 0xf
imm3 = (0x5802 >> 8) & 7
imm8 = 0x5802 & 0xff
hw1 = 0xf2c0 | (i << 10) | imm4
hw2 = (imm3 << 12) | (0 << 8) | imm8
write_instr32(code_offset, hw1, hw2)
code_offset += 4

# Mark loop start
loop_offset = code_offset

# mov r1, #0x1000  (set bit 12 - LED on)
# T3 encoding: 11110x0100x imm3 rd imm8
# rd=1, imm3=1, imm8=0x00, i=0
write_instr32(code_offset, 0xf44f, 0x7180)
code_offset += 4

# str r1, [r0]
write_instr16(code_offset, 0x6001)
code_offset += 2

# movw r2, #0xffff  (delay count low)
write_instr32(code_offset, 0xf64f, 0x72ff)
code_offset += 4

# movt r2, #0x000f  (delay count high - ~1M iterations)
write_instr32(code_offset, 0xf6c0, 0x020f)
code_offset += 4

# delay1_loop:
delay1_offset = code_offset

# subs r2, r2, #1
write_instr16(code_offset, 0x1e52)
code_offset += 2

# bne delay1_loop (branch -4 bytes = offset -2 from next instruction)
# D1 FC = bne .-4
write_instr16(code_offset, 0xd1fc)
code_offset += 2

# movw r1, #0x0000  (for BSRR high half - reset bit 12)
write_instr32(code_offset, 0xf240, 0x7100)
code_offset += 4

# movt r1, #0x1000  (set bit 28 = bit 12 in upper half)
i = (0x1000 >> 11) & 1
imm4 = (0x1000 >> 12) & 0xf
imm3 = (0x1000 >> 8) & 7
imm8 = 0x1000 & 0xff
hw1 = 0xf2c0 | (i << 10) | imm4
hw2 = (imm3 << 12) | (1 << 8) | imm8
write_instr32(code_offset, hw1, hw2)
code_offset += 4

# str r1, [r0]
write_instr16(code_offset, 0x6001)
code_offset += 2

# movw r2, #0xffff  (delay count)
write_instr32(code_offset, 0xf64f, 0x72ff)
code_offset += 4

# movt r2, #0x000f
write_instr32(code_offset, 0xf6c0, 0x020f)
code_offset += 4

# delay2_loop:
delay2_offset = code_offset

# subs r2, r2, #1
write_instr16(code_offset, 0x1e52)
code_offset += 2

# bne delay2_loop
write_instr16(code_offset, 0xd1fc)
code_offset += 2

# b loop_start (unconditional branch back)
# Calculate offset: target - (current + 4) / 2
# We want to go to loop_offset from code_offset + 4
branch_target = loop_offset
branch_source = code_offset + 4
offset = (branch_target - branch_source) // 2
# B encoding: 11100xxxxxxxxxxx (11-bit signed offset)
b_opcode = 0xe000 | (offset & 0x7ff)
write_instr16(code_offset, b_opcode)
code_offset += 2

# Write the binary
output_path = "/home/alial/.openclaw/workspace/mcp-boardfarm/test_firmware/h755_blink/h755_blink.bin"
with open(output_path, 'wb') as f:
    f.write(binary)

print(f"Created {output_path}")
print(f"Size: {len(binary)} bytes")
print(f"Reset handler: 0x{FLASH_BASE + 0x100:08x}")
print(f"Initial SP: 0x{RAM_TOP:08x}")
print()
print("Hex dump (first 128 bytes):")
for i in range(0, 128, 16):
    line = binary[i:i+16]
    hex_str = ' '.join(f'{b:02x}' for b in line)
    ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in line)
    print(f"  {i:04x}: {hex_str}  {ascii_str}")
print()
print("Vector table:")
print(f"  SP: 0x{struct.unpack_from('<I', binary, 0)[0]:08x}")
print(f"  PC: 0x{struct.unpack_from('<I', binary, 4)[0]:08x}")
