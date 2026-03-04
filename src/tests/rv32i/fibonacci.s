# RISC-V RV32I: Fibonacci F(10) = 55
# Tests: branches, loops, register data flow

li   t0, 0             # F(n-2) = 0
li   t1, 1             # F(n-1) = 1
li   t2, 2             # counter = 2
li   t3, 11            # limit = 11

fib_loop:
    add  t4, t0, t1    # F(n) = F(n-2) + F(n-1)
    mv   t0, t1        # shift: F(n-2) = old F(n-1)
    mv   t1, t4        # shift: F(n-1) = new F(n)
    addi t2, t2, 1     # counter++
    blt  t2, t3, fib_loop  # if counter < limit, loop

# t1 = F(10) = 55
# Store result
li   t5, 200           # base addr
sw   t1, 0(t5)         # DataMem[200] = 55
ecall
