# Fibonacci: Compute fib(10) = 55 using registers
# F(0)=0, F(1)=1, F(n)=F(n-1)+F(n-2)
#
# R1 = F(n-2), R2 = F(n-1), R3 = F(n) (current)
# R4 = iteration counter, R5 = limit (10)
# R6 = temp for comparison

# Initialize
LOAD_R R1, 0        # F(0) = 0
LOAD_R R2, 1        # F(1) = 1
LOAD_R R4, 2        # counter = 2 (we already have F(0) and F(1))
LOAD_R R5, 11       # limit = 11 (compute up to F(10))

fib_loop:
    ADD_R R3, R1, R2     # F(n) = F(n-1) + F(n-2)
    # Shift: R1 = R2, R2 = R3
    LOAD_R R7, 0
    ADD_R R1, R2, R7     # R1 = R2 (F(n-2) = old F(n-1))
    ADD_R R2, R3, R7     # R2 = R3 (F(n-1) = new F(n))
    # counter++
    LOAD_R R6, 1
    ADD_R R4, R4, R6     # counter++
    # Check: counter < limit?
    SUB_R R6, R5, R4     # R6 = limit - counter
    ADD_R R0, R6, R7     # ACC = R6 (for JNZ check)
    JNZ fib_loop

# R2 = F(10) = 55
# Store results to memory for verification
STORE_R R2, 60       # DataMem[60] = fib(10)

HALT
