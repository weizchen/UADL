# Store 42 in mem[10], load it back, add 1, store in mem[11]
LOAD_IMM 42
STORE 10
LOAD_MEM 10
ADD_IMM 1
STORE 11
HALT
