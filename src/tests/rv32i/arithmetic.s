# RISC-V RV32I: Basic Arithmetic Test
# Tests: addi, add, sub, and, or, xor, slt

addi x1, zero, 10      # x1 = 10
addi x2, zero, 20      # x2 = 20
add  x3, x1, x2        # x3 = 30
sub  x4, x2, x1        # x4 = 10
and  x5, x1, x2        # x5 = 10 & 20 = 0
or   x6, x1, x2        # x6 = 10 | 20 = 30
xor  x7, x1, x2        # x7 = 10 ^ 20 = 30
slt  x8, x1, x2        # x8 = (10 < 20) = 1
slt  x9, x2, x1        # x9 = (20 < 10) = 0
ecall
