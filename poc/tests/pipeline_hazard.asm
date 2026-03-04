# Pipeline Hazard Test
# LOAD_MEM followed immediately by ADD_IMM (uses ACC = R[0])
# With forwarding: should cause 1 stall cycle (load-use hazard)
# Without forwarding: should cause 2 stall cycles

LOAD_IMM 42
STORE 10
LOAD_MEM 10
ADD_IMM 1
HALT
