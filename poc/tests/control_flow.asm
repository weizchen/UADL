# 0: Initialize ACC = 5
LOAD_IMM 5
# 1: Loop start - subtract 1
SUB_IMM 1
# 2: Jump back to 1 if ACC != 0
JNZ 1
# 3: Halt
HALT
