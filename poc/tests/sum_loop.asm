# Sum of 1..10 using register loop
# Exercises: loops (JNZ with labels), register arithmetic, branch flushes, cache
#
# R1 = counter (1..10), R2 = running sum, R3 = limit (11)
# R5 = increment constant (1), R6 = temp comparison
#
# Expected: R2 = 55, DataMem[50] = 55

# Initialize
LOAD_R R1, 1        # counter = 1
LOAD_R R2, 0        # sum = 0
LOAD_R R3, 11       # limit = 11 (loop while counter < 11)
LOAD_R R5, 1        # constant 1

# Also store values 1-10 into DataMem[0..9] to exercise memory+cache
LOAD_IMM 1
STORE 0
LOAD_IMM 2
STORE 1
LOAD_IMM 3
STORE 2
LOAD_IMM 4
STORE 3
LOAD_IMM 5
STORE 4
LOAD_IMM 6
STORE 5
LOAD_IMM 7
STORE 6
LOAD_IMM 8
STORE 7
LOAD_IMM 9
STORE 8
LOAD_IMM 10
STORE 9

# Sum loop using registers only
sum_loop:
    ADD_R R2, R2, R1     # sum += counter
    ADD_R R1, R1, R5     # counter++
    SUB_R R6, R3, R1     # R6 = limit - counter
    ADD_R R0, R6, R2     # ACC = R6 + R2... wait, we need ACC = R6
    # Move R6 to ACC for JNZ check
    LOAD_IMM 0           # ACC = 0
    ADD_R R0, R6, R0     # ACC = R6 + 0 = R6, but R0 IS ACC... 
    # Simpler: just subtract to set ACC
    LOAD_IMM 0
    ADD_R R0, R6, R0     # R0 = R6 + R0, but R0 was just set to 0
    JNZ sum_loop

# Store final sum
STORE_R R2, 50

HALT
