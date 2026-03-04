# Register Operations Test
# Uses R1-R4 instead of accumulator round-trips through memory
# R1 = 10, R2 = 20, R3 = R1 + R2 (=30), R4 = R3 * R1 (actually SUB: R3 - R1 = 20)
# Store results to DataMem for verification

LOAD_R R1, 10
LOAD_R R2, 20
ADD_R R3, R1, R2
SUB_R R4, R3, R1
STORE_R R3, 50
STORE_R R4, 51
HALT
