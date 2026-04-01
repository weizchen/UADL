
#include <iostream>
#include <vector>
#include <cstdint>
#include <fstream>
#include <cstring>
#include <algorithm>
#include <cstdio>

using namespace std;

// --- Architecture: ARMv7 ---
// --- Execution Model: scalar ---






// === Memory Spaces ===

vector<uint8_t> InstructionMem(16384, 0);

vector<uint8_t> DataMem(16384, 0);


// === Cache Hierarchy ===


struct L1_Cache {
    static const int SIZE = 4096;
    static const int LINE_SIZE = 32;
    static const int ASSOCIATIVITY = 4;
    static const int NUM_SETS = 32;
    static const int HIT_LATENCY = 1;
    static const int MISS_PENALTY = 5;
    
    uint32_t tags[NUM_SETS][ASSOCIATIVITY];
    bool valid[NUM_SETS][ASSOCIATIVITY];
    int lru_counter[NUM_SETS][ASSOCIATIVITY];
    int access_count, hit_count, miss_count;
    
    L1_Cache() : access_count(0), hit_count(0), miss_count(0) {
        memset(valid, 0, sizeof(valid));
        memset(tags, 0, sizeof(tags));
        memset(lru_counter, 0, sizeof(lru_counter));
    }
    
    int access(uint32_t addr) {
        access_count++;
        uint32_t line_addr = addr / LINE_SIZE;
        uint32_t set_idx = line_addr % NUM_SETS;
        uint32_t tag = line_addr / NUM_SETS;
        
        for (int w = 0; w < ASSOCIATIVITY; w++) {
            if (valid[set_idx][w] && tags[set_idx][w] == tag) {
                hit_count++;
                lru_counter[set_idx][w] = access_count;
                return HIT_LATENCY;
            }
        }
        
        miss_count++;
        int victim = 0;
        int min_lru = lru_counter[set_idx][0];
        for (int w = 0; w < ASSOCIATIVITY; w++) {
            if (!valid[set_idx][w]) { victim = w; break; }
            if (lru_counter[set_idx][w] < min_lru) {
                min_lru = lru_counter[set_idx][w];
                victim = w;
            }
        }
        valid[set_idx][victim] = true;
        tags[set_idx][victim] = tag;
        lru_counter[set_idx][victim] = access_count;
        return HIT_LATENCY + MISS_PENALTY;
    }
};
L1_Cache cache_L1;



struct L2_Cache {
    static const int SIZE = 16384;
    static const int LINE_SIZE = 64;
    static const int ASSOCIATIVITY = 8;
    static const int NUM_SETS = 32;
    static const int HIT_LATENCY = 3;
    static const int MISS_PENALTY = 50;
    
    uint32_t tags[NUM_SETS][ASSOCIATIVITY];
    bool valid[NUM_SETS][ASSOCIATIVITY];
    int lru_counter[NUM_SETS][ASSOCIATIVITY];
    int access_count, hit_count, miss_count;
    
    L2_Cache() : access_count(0), hit_count(0), miss_count(0) {
        memset(valid, 0, sizeof(valid));
        memset(tags, 0, sizeof(tags));
        memset(lru_counter, 0, sizeof(lru_counter));
    }
    
    int access(uint32_t addr) {
        access_count++;
        uint32_t line_addr = addr / LINE_SIZE;
        uint32_t set_idx = line_addr % NUM_SETS;
        uint32_t tag = line_addr / NUM_SETS;
        
        for (int w = 0; w < ASSOCIATIVITY; w++) {
            if (valid[set_idx][w] && tags[set_idx][w] == tag) {
                hit_count++;
                lru_counter[set_idx][w] = access_count;
                return HIT_LATENCY;
            }
        }
        
        miss_count++;
        int victim = 0;
        int min_lru = lru_counter[set_idx][0];
        for (int w = 0; w < ASSOCIATIVITY; w++) {
            if (!valid[set_idx][w]) { victim = w; break; }
            if (lru_counter[set_idx][w] < min_lru) {
                min_lru = lru_counter[set_idx][w];
                victim = w;
            }
        }
        valid[set_idx][victim] = true;
        tags[set_idx][victim] = tag;
        lru_counter[set_idx][victim] = access_count;
        return HIT_LATENCY + MISS_PENALTY;
    }
};
L2_Cache cache_L2;



// === Memory Access (follows connection graph) ===



int access_instruction_mem(uint32_t addr) {
    int total = 0;
    
    {
        int result = cache_L1.access(addr);
        total += result;
        if (result == L1_Cache::HIT_LATENCY) return total;
    }
    
    {
        int result = cache_L2.access(addr);
        total += result;
        if (result == L2_Cache::HIT_LATENCY) return total;
    }
    
    return total;
}



int access_data_mem(uint32_t addr) {
    int total = 0;
    
    {
        int result = cache_L1.access(addr);
        total += result;
        if (result == L1_Cache::HIT_LATENCY) return total;
    }
    
    {
        int result = cache_L2.access(addr);
        total += result;
        if (result == L2_Cache::HIT_LATENCY) return total;
    }
    
    return total;
}



// Generic access (for backward compat / when chains not specified)
int simulate_memory_access(uint32_t addr) {
    
    return access_data_mem(addr);
    
}






// === ARMv7 Instruction Decoder ===
inline int32_t sign_extend(uint32_t val, int bit_width) {
    uint32_t sign_bit = 1U << (bit_width - 1);
    return (int32_t)((val ^ sign_bit) - sign_bit);
}

// ARM condition codes
enum ArmCond {
    COND_EQ = 0, COND_NE = 1, COND_CS = 2, COND_CC = 3,
    COND_MI = 4, COND_PL = 5, COND_VS = 6, COND_VC = 7,
    COND_HI = 8, COND_LS = 9, COND_GE = 10, COND_LT = 11,
    COND_GT = 12, COND_LE = 13, COND_AL = 14
};

struct DecodedInst {
    uint32_t cond;
    uint32_t type_;
    uint32_t opcode;
    uint32_t S;
    uint32_t rd;
    uint32_t rn;
    uint32_t rm;
    uint32_t funct3;
    uint32_t funct7;
    uint32_t rs1;
    uint32_t rs2;
    int32_t imm;
    bool is_imm;
};

// CPSR flags
uint32_t cpsr_N = 0, cpsr_Z = 0, cpsr_C = 0, cpsr_V = 0;

bool check_condition(uint32_t cond) {
    switch (cond) {
        case 0:  return cpsr_Z == 1;           // EQ
        case 1:  return cpsr_Z == 0;           // NE
        case 2:  return cpsr_C == 1;           // CS/HS
        case 3:  return cpsr_C == 0;           // CC/LO
        case 10: return cpsr_N != cpsr_V;      // LT
        case 11: return cpsr_N == cpsr_V;      // GE
        case 12: return !cpsr_Z && (cpsr_N == cpsr_V); // GT
        case 13: return cpsr_Z || (cpsr_N != cpsr_V);  // LE
        case 14: return true;                  // AL
        default: return true;
    }
}

// Apply barrel shifter to a register value
inline int32_t apply_shift(int32_t val, uint32_t shift_type, uint32_t shift_amount) {
    if (shift_amount == 0) return val;
    switch (shift_type) {
        case 0: return val << shift_amount;                          // LSL
        case 1: return (int32_t)((uint32_t)val >> shift_amount);     // LSR
        case 2: return val >> shift_amount;                          // ASR
        default: return val;
    }
}

DecodedInst decode(uint32_t inst) {
    DecodedInst d;
    d.cond   = (inst >> 28) & 0xF;
    d.type_  = (inst >> 25) & 0x7;
    d.opcode = (inst >> 21) & 0xF;
    d.S      = (inst >> 20) & 1;
    d.rn     = (inst >> 16) & 0xF;
    d.rd     = (inst >> 12) & 0xF;
    d.rm     = inst & 0xF;
    d.is_imm = (inst >> 25) & 1;
    
    d.rs1 = d.rn;
    d.rs2 = d.rm;
    d.funct3 = d.opcode;
    d.funct7 = 0;
    
    if ((d.type_ & 0x6) == 0x0) {
        // Data processing
        if (d.is_imm) {
            if (d.opcode == 0x8 && d.S == 0) {
                // MOVW (16-bit immediate: imm4 | imm12)
                uint32_t imm4 = (inst >> 16) & 0xF;
                uint32_t imm12 = inst & 0xFFF;
                d.imm = (imm4 << 12) | imm12;
            } else {
                uint32_t rotate = ((inst >> 8) & 0xF) * 2;
                uint32_t imm8 = inst & 0xFF;
                if (rotate == 0) {
                    d.imm = (int32_t)imm8;
                } else {
                    d.imm = (int32_t)((imm8 >> rotate) | (imm8 << (32 - rotate)));
                }
            }
        } else {
            // Register with optional shift
            d.imm = 0;
        }
    } else if ((d.type_ & 0x6) == 0x2) {
        // Load/Store (immediate or register offset)
        if (!d.is_imm) {
            // type_=010: immediate offset
            d.imm = inst & 0xFFF;
            if (!((inst >> 23) & 1)) d.imm = -d.imm;
        } else {
            // type_=011: register offset — computed at execution time
            d.imm = 0;
        }
    } else if ((d.type_ & 0x6) == 0x4) {
        if ((inst >> 25) & 1) {
            // Branch
            d.imm = sign_extend((inst & 0xFFFFFF) << 2, 26) + 8;
        } else {
            // Block data transfer (LDM/STM)
            d.imm = inst & 0xFFFF;
        }
    } else {
        d.imm = 0;
    }
    
    return d;
}

// Instruction name lookup
const char* inst_name(uint32_t opcode, uint32_t funct3, uint32_t funct7) {
    
    
    if (funct3 == 4) return "ADD";
    
    
    
    if (funct3 == 2) return "SUB";
    
    
    
    if (funct3 == 0) return "AND";
    
    
    
    if (funct3 == 12) return "ORR";
    
    
    
    if (funct3 == 1) return "EOR";
    
    
    
    if (funct3 == 13) return "MOV";
    
    
    
    if (funct3 == 10) return "CMP";
    
    
    
    if (funct3 == 13) return "LSL";
    
    
    
    if (funct3 == 13) return "LSR";
    
    
    
    if (funct3 == 13) return "ASR";
    
    
    
    if (funct3 == 4) return "ADD_IMM";
    
    
    
    if (funct3 == 2) return "SUB_IMM";
    
    
    
    if (funct3 == 13) return "MOV_IMM";
    
    
    
    if (funct3 == 8) return "MOVW";
    
    
    
    if (funct3 == 10) return "CMP_IMM";
    
    
    
    if (funct3 == 1) return "LDR";
    
    
    
    if (funct3 == 0) return "STR";
    
    
    
    if (funct3 == 10) return "B";
    
    
    
    if (funct3 == 11) return "BL";
    
    
    
    if (funct3 == 0) return "BX";
    
    
    
    if (funct3 == 0) return "SVC";
    
    
    return "???";
}



















// === Pipeline Trace ===

struct PipelineTraceEntry {
    const char* name;
    int if_cycle;
    int stall;
};


// === Core State ===
struct CoreState {
    int core_id;
    bool halt;
    uint64_t total_cycles;
    
    int32_t r[16];
    uint32_t PC;
    
    
    int pipeline_cycle;
    int reg_available_at[16];
    int stall_cycles;
    int flush_count;
    vector<PipelineTraceEntry> pipeline_trace;
    
    
    CoreState(int id) : core_id(id), halt(false), total_cycles(0), PC(0) {
        memset(r, 0, sizeof(r));
        
        pipeline_cycle = 0;
        memset(reg_available_at, 0, sizeof(reg_available_at));
        stall_cycles = 0;
        flush_count = 0;
        
    }
    
    
    void reset_pipeline() {
        memset(reg_available_at, 0, sizeof(reg_available_at));
    }
    
};

int NUM_CORES = 2;
vector<CoreState> cores;

// === Instruction Execution (Scalar) ===
void step(CoreState& core) {
    if (core.halt) return;
    
    bool _branch_taken = false;
    uint32_t _mem_addr = 0;
    
    // Fetch
    uint32_t current_pc = core.PC;
    uint32_t raw_inst = 0;
    if (current_pc + 4 <= InstructionMem.size()) {
        memcpy(&raw_inst, &InstructionMem[current_pc], 4);
    }
    
    // Increment PC
    core.PC += 4;
    
    // Decode

    DecodedInst d = decode(raw_inst);
    uint32_t rd = d.rd, rn = d.rn, rm = d.rm;
    uint32_t rs1 = d.rn, rs2 = d.rm;
    int32_t imm = d.imm;
    
    // Check condition code
    if (!check_condition(d.cond)) {
        return;
    }
    
    // === PUSH (STMDB sp!, {reglist}) ===
    if ((raw_inst & 0x0FFF0000) == 0x092D0000) {
        uint32_t reglist = raw_inst & 0xFFFF;
        for (int i = 15; i >= 0; i--) {
            if (reglist & (1 << i)) {
                core.r[13] -= 4;
                uint32_t addr = (uint32_t)core.r[13];
                int32_t val = (i == 15) ? (int32_t)core.PC : core.r[i];
                memcpy(&DataMem[addr], &val, 4);
            }
        }
        
        core.pipeline_cycle++;
        if (core.pipeline_trace.size() < 30) {
            core.pipeline_trace.push_back({"PUSH", core.pipeline_cycle - 1, 0});
        }
        
        return;
    }
    // === POP (LDMIA sp!, {reglist}) ===
    if ((raw_inst & 0x0FFF0000) == 0x08BD0000) {
        uint32_t reglist = raw_inst & 0xFFFF;
        bool pop_pc = false;
        for (int i = 0; i <= 15; i++) {
            if (reglist & (1 << i)) {
                uint32_t addr = (uint32_t)core.r[13];
                int32_t val;
                memcpy(&val, &DataMem[addr], 4);
                if (i == 15) {
                    core.PC = (uint32_t)val;
                    pop_pc = true;
                } else {
                    core.r[i] = val;
                }
                core.r[13] += 4;
            }
        }
        
        core.pipeline_cycle++;
        if (core.pipeline_trace.size() < 30) {
            core.pipeline_trace.push_back({"POP", core.pipeline_cycle - 1, 0});
        }
        if (pop_pc) {
            core.pipeline_cycle += 1;
            core.flush_count++;
        }
        
        _branch_taken = pop_pc;
        return;
    }
    
    // === MVN (data processing, opcode=0xF) ===
    if ((d.type_ & 0x6) == 0x0 && d.opcode == 0xF) {
        if (d.is_imm) {
            core.r[rd] = ~imm;
        } else {
            uint32_t shift_type = (raw_inst >> 5) & 0x3;
            uint32_t shift_amt = (raw_inst >> 7) & 0x1F;
            core.r[rd] = ~apply_shift(core.r[rm], shift_type, shift_amt);
        }
        
        core.pipeline_cycle++;
        if (core.pipeline_trace.size() < 30) {
            core.pipeline_trace.push_back({"MVN", core.pipeline_cycle - 1, 0});
        }
        
        return;
    }
    
    // === LDR/STR with register offset (type_=011) ===
    if (d.type_ == 0x3) {
        uint32_t shift_type = (raw_inst >> 5) & 0x3;
        uint32_t shift_amt = (raw_inst >> 7) & 0x1F;
        int32_t offset = apply_shift(core.r[rm], shift_type, shift_amt);
        bool U = (raw_inst >> 23) & 1;
        bool P = (raw_inst >> 24) & 1;  // pre-index
        bool W = (raw_inst >> 21) & 1;  // writeback
        
        uint32_t base = (uint32_t)core.r[rn];
        uint32_t addr = U ? (base + (uint32_t)offset) : (base - (uint32_t)offset);
        
        if ((raw_inst >> 20) & 1) {
            // LDR (register offset)
            int32_t val;
            memcpy(&val, &DataMem[addr], 4);
            core.r[rd] = val;
            _mem_addr = addr;
            
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"LDR_R", core.pipeline_cycle - 1, 0});
            }
            
        } else {
            // STR (register offset)
            int32_t val = core.r[rd];
            memcpy(&DataMem[addr], &val, 4);
            _mem_addr = addr;
            
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"STR_R", core.pipeline_cycle - 1, 0});
            }
            
        }
        // Handle writeback
        if (W || !P) {
            core.r[rn] = (int32_t)addr;
        }
        return;
    }
    
    // === Data processing with barrel-shifted register operand ===
    // Temporarily patch r[rm] with shifted value for dispatch
    // EXCLUDE BX instructions — BX has a unique encoding that looks like DP
    // but the shift bits are part of the BX encoding, not an actual shift.
    int32_t _saved_rm = 0;
    bool _has_shift = false;
    bool _is_bx = ((raw_inst & 0x0FFFFFF0) == 0x012FFF10);
    if ((d.type_ & 0x6) == 0x0 && !d.is_imm && !_is_bx) {
        uint32_t shift_type = (raw_inst >> 5) & 0x3;
        uint32_t shift_amt = (raw_inst >> 7) & 0x1F;
        if (shift_amt != 0) {
            _saved_rm = core.r[rm];
            core.r[rm] = apply_shift(_saved_rm, shift_type, shift_amt);
            _has_shift = true;
        }
    }

    
    // Execute: dispatch
    

    
    if ((d.type_ & 0x6) == 0x0 && !d.is_imm && d.opcode == 4) {
    

        // ADD
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rm]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"ADD", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = core.r[rn] + core.r[rm];
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && !d.is_imm && d.opcode == 2) {
    

        // SUB
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rm]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SUB", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = core.r[rn] - core.r[rm];
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && !d.is_imm && d.opcode == 0) {
    

        // AND
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rm]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"AND", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = core.r[rn] & core.r[rm];
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && !d.is_imm && d.opcode == 12) {
    

        // ORR
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rm]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"ORR", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = core.r[rn] | core.r[rm];
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && !d.is_imm && d.opcode == 1) {
    

        // EOR
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rm]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"EOR", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = core.r[rn] ^ core.r[rm];
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && !d.is_imm && d.opcode == 13) {
    

        // MOV
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rm]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"MOV", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = core.r[rm];
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && !d.is_imm && d.opcode == 10) {
    

        // CMP
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rm]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"CMP", _if_cycle, _stall});
            }
        }
        
        
            { int32_t _result = (int32_t)core.r[rn] - (int32_t)core.r[rm];
              cpsr_N = (_result < 0) ? 1 : 0;
              cpsr_Z = (_result == 0) ? 1 : 0;
              cpsr_V = (((int32_t)core.r[rn] ^ (int32_t)core.r[rm]) & ((int32_t)core.r[rn] ^ _result)) >> 31;
              cpsr_C = ((uint32_t)core.r[rn] >= (uint32_t)core.r[rm]) ? 1 : 0; }
        


        
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && !d.is_imm && d.opcode == 13 && ((raw_inst >> 5) & 0x3) == 0) {
    

        // LSL
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rm]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"LSL", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = core.r[rn] << (core.r[rm] & 0x1F);
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && !d.is_imm && d.opcode == 13 && ((raw_inst >> 5) & 0x3) == 1) {
    

        // LSR
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rm]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"LSR", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = (uint32_t)core.r[rn] >> (core.r[rm] & 0x1F);
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && !d.is_imm && d.opcode == 13 && ((raw_inst >> 5) & 0x3) == 2) {
    

        // ASR
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rm]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"ASR", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = (int32_t)core.r[rn] >> (core.r[rm] & 0x1F);
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && d.is_imm && d.opcode == 4) {
    

        // ADD_IMM
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"ADD_IMM", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = core.r[rn] + imm;
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && d.is_imm && d.opcode == 2) {
    

        // SUB_IMM
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SUB_IMM", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = core.r[rn] - imm;
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && d.is_imm && d.opcode == 13) {
    

        // MOV_IMM
        
        {
            int _src_avail = 0;
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"MOV_IMM", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = imm;
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && d.is_imm && d.opcode == 8) {
    

        // MOVW
        
        {
            int _src_avail = 0;
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"MOVW", _if_cycle, _stall});
            }
        }
        
        
            core.r[rd] = imm;
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x0 && d.is_imm && d.opcode == 10) {
    

        // CMP_IMM
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"CMP_IMM", _if_cycle, _stall});
            }
        }
        
        
            { int32_t _result = (int32_t)core.r[rn] - (int32_t)imm;
              cpsr_N = (_result < 0) ? 1 : 0;
              cpsr_Z = (_result == 0) ? 1 : 0;
              cpsr_V = (((int32_t)core.r[rn] ^ (int32_t)imm) & ((int32_t)core.r[rn] ^ _result)) >> 31;
              cpsr_C = ((uint32_t)core.r[rn] >= (uint32_t)imm) ? 1 : 0; }
        


        
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x2 && !d.is_imm && ((raw_inst >> 20) & 1) == 1) {
    

        // LDR
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"LDR", _if_cycle, _stall});
            }
        }
        
        
            { uint32_t _addr = (uint32_t)((int32_t)core.r[rn] + imm);
              _mem_addr = _addr;
              memcpy(&core.r[rd], &DataMem[_addr], 4); }
        


        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 1;
        
        
        
        
        
        
        core.pipeline_cycle += simulate_memory_access(_mem_addr);
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x2 && !d.is_imm && ((raw_inst >> 20) & 1) == 0) {
    

        // STR
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rd]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rn]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"STR", _if_cycle, _stall});
            }
        }
        
        
            { uint32_t _addr = (uint32_t)((int32_t)core.r[rn] + imm);
              _mem_addr = _addr;
              memcpy(&DataMem[_addr], &core.r[rd], 4); }
        


        
        
        
        
        
        
        
        core.pipeline_cycle += simulate_memory_access(_mem_addr);
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x4 && ((raw_inst >> 24) & 0xF) == 10) {
    

        // B
        
        {
            int _src_avail = 0;
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"B", _if_cycle, _stall});
            }
        }
        
        
            core.PC = current_pc + imm;
            _branch_taken = true;
        


        
        
        
        
        
        
    }
    

    
    else if ((d.type_ & 0x6) == 0x4 && ((raw_inst >> 24) & 0xF) == 11) {
    

        // BL
        
        {
            int _src_avail = 0;
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"BL", _if_cycle, _stall});
            }
        }
        
        
            core.r[14] = core.PC;
            core.PC = current_pc + imm;
            _branch_taken = true;
        


        
        
        
        
        core.reg_available_at[14] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if ((raw_inst & 0x0FFFFFF0) == 0x012FFF10) {
    

        // BX
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rm]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"BX", _if_cycle, _stall});
            }
        }
        
        
            core.PC = core.r[rm] & ~1;
            _branch_taken = true;
        


        
        
        
        
        
        
    }
    

    
    else if ((raw_inst & 0x0F000000) == 0x0F000000) {
    

        // SVC
        
        {
            int _src_avail = 0;
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SVC", _if_cycle, _stall});
            }
        }
        
        
            core.halt = true;
        


        
        
        
        
        
        
    }
    
    else {
        cerr << "Unknown instruction at PC=" << current_pc << " raw=0x" << hex << raw_inst << dec << endl;
        core.halt = true;
    }
    
    
    // Restore barrel-shifted register
    if (_has_shift) {
        core.r[rm] = _saved_rm;
    }
    
    
    
    if (_branch_taken) {
        core.pipeline_cycle += 1;
        core.flush_count++;
    }
    
}







int main(int argc, char** argv) {
    if (argc < 2) {
        cerr << "Usage: " << argv[0] << " <binary_file>" << endl;
        return 1;
    }

    // Load .mem format
    FILE* f = fopen(argv[1], "rb");
    if (!f) { cerr << "Error opening file " << argv[1] << endl; return 1; }
    
    char magic[4];
    if (fread(magic, 1, 4, f) != 4 || strncmp(magic, "UADL", 4) != 0) {
        cerr << "Invalid memory format (missing UADL magic)" << endl;
        fclose(f); return 1;
    }
    
    uint32_t vaddr, size_bytes;
    while (fread(&vaddr, 1, 4, f) == 4 && fread(&size_bytes, 1, 4, f) == 4) {
        vector<uint8_t> buf(size_bytes);
        if (fread(buf.data(), 1, size_bytes, f) != size_bytes) break;
        
        
        if (vaddr < InstructionMem.size()) {
            uint32_t copy_size = min(size_bytes, (uint32_t)InstructionMem.size() - vaddr);
            memcpy(&InstructionMem[vaddr], buf.data(), copy_size);
        }
        if (vaddr < DataMem.size()) {
            uint32_t copy_size = min(size_bytes, (uint32_t)DataMem.size() - vaddr);
            memcpy(&DataMem[vaddr], buf.data(), copy_size);
        }
        
    }
    fclose(f);

    
    
    for (int c = 0; c < NUM_CORES; c++) cores.push_back(CoreState(c));
    
    bool active = true;
    while (active) {
        active = false;
        for (int c = 0; c < NUM_CORES; c++) {
            if (!cores[c].halt) { active = true; step(cores[c]); }
        }
    }

    // Output
    
    uint64_t max_cycles = 0;
    cout << "--- Final CPU State ---" << endl;
    for (int c = 0; c < NUM_CORES; c++) {
        
        cores[c].total_cycles = cores[c].pipeline_cycle;
        
        cout << "[Core " << c << "]" << endl;
        cout << "  PC: " << cores[c].PC << endl;
        for (int i = 0; i < 16; i++) {
            if (cores[c].r[i] != 0) {
                cout << "  r[" << i << "]: " << cores[c].r[i] << endl;
            }
        }
        cout << "  Total Cycles: " << cores[c].total_cycles << endl;
        
        cout << "  Pipeline Stalls: " << cores[c].stall_cycles << endl;
        cout << "  Pipeline Flushes: " << cores[c].flush_count << endl;
        
        if (cores[c].total_cycles > max_cycles) max_cycles = cores[c].total_cycles;
    }
    cout << "--- Performance Data ---" << endl;
    cout << "Total Workload Cycles: " << max_cycles << endl;
    
    
    cout << "L1 Cache: " << cache_L1.hit_count << " hits, " 
         << cache_L1.miss_count << " misses ("
         << (cache_L1.access_count > 0 ? (100.0 * cache_L1.hit_count / cache_L1.access_count) : 0) 
         << "% hit rate)" << endl;
    
    
    
    cout << "L2 Cache: " << cache_L2.hit_count << " hits, " 
         << cache_L2.miss_count << " misses ("
         << (cache_L2.access_count > 0 ? (100.0 * cache_L2.hit_count / cache_L2.access_count) : 0) 
         << "% hit rate)" << endl;
    
    
    cout << "--- Data Memory Dump ---" << endl;
    for (int j = 0; j < 1024; j += 4) {
        int32_t val;
        memcpy(&val, &DataMem[j], 4);
        if (val != 0) cout << "DataMem[" << j << "]: " << val << endl;
    }
    
    
    if (!cores[0].pipeline_trace.empty()) {
        cout << "--- Pipeline Diagram ---" << endl;
        
        int _max_c = 0;
        for (auto& e : cores[0].pipeline_trace) {
            int wb = e.if_cycle + e.stall + 5;
            if (wb > _max_c) _max_c = wb;
        }
        if (_max_c > 40) _max_c = 40;
        
        printf("%-8s", "Instr");
        for (int c = 0; c < _max_c; c++) printf("%3d ", c + 1);
        printf("\n");
        printf("%-8s", "--------");
        for (int c = 0; c < _max_c; c++) printf("----");
        printf("\n");
        
        for (auto& e : cores[0].pipeline_trace) {
            printf("%-8s", e.name);
            for (int c = 0; c < _max_c; c++) {
                
                
                
                if (c == e.if_cycle) printf(" FE ");
                
                
                
                else if (c == e.if_cycle + 1) printf(" DE ");
                
                
                
                else if (c == e.if_cycle + 2 + e.stall) printf(" EX ");
                
                
                
                else if (c == e.if_cycle + 3 + e.stall) printf(" ME ");
                
                
                
                else if (c == e.if_cycle + 4 + e.stall) printf(" WR ");
                
                
                else if (e.stall > 0 && c > e.if_cycle + 1 && c <= e.if_cycle + 1 + e.stall) printf(" ** ");
                else printf("    ");
            }
            printf("\n");
        }
    }
    

    

    return 0;
}