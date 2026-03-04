# RISC-V RV32I: Function call test
# Tests: jal, jalr (ret), stack push/pop

# Main: call add_func(10, 20), store result
    li   a0, 10         # arg0 = 10
    li   a1, 20         # arg1 = 20
    call add_func       # jal ra, add_func
    # a0 now has return value (30)
    li   t0, 300
    sw   a0, 0(t0)      # DataMem[300] = 30
    ecall

add_func:
    # a0 = arg0, a1 = arg1
    add  a0, a0, a1     # return a0 + a1
    ret                 # jalr zero, ra, 0
