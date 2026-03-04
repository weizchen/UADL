# Main Thread (starts at PC 0)
LOAD_IMM 100
STORE 50
FORK 5
FORK 8
HALT 

# Thread 2 (Starts at PC 5)
LOAD_IMM 200
STORE 51
HALT

# Thread 3 (Starts at PC 8)
LOAD_IMM 300
STORE 52
HALT
