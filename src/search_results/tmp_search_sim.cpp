
#include <iostream>
#include <vector>
#include <cstdint>
#include <fstream>
#include <cstring>
#include <algorithm>
#include <cstdio>

using namespace std;

// --- Architecture: RV32I ---
// --- Execution Model: scalar ---






// === Memory Spaces ===

vector<uint8_t> InstructionMem(16384, 0);

vector<uint8_t> DataMem(16384, 0);


// === Cache Hierarchy ===


struct L1_Cache {
    static const int SIZE = 256;
    static const int LINE_SIZE = 16;
    static const int ASSOCIATIVITY = 1;
    static const int NUM_SETS = 16;
    static const int HIT_LATENCY = 1;
    static const int MISS_PENALTY = 10;
    
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
    static const int SIZE = 1024;
    static const int LINE_SIZE = 32;
    static const int ASSOCIATIVITY = 4;
    static const int NUM_SETS = 8;
    static const int HIT_LATENCY = 5;
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






// === RISC-V RV32I Instruction Decoder ===
inline int32_t sign_extend(uint32_t val, int bit_width) {
    uint32_t sign_bit = 1U << (bit_width - 1);
    return (int32_t)((val ^ sign_bit) - sign_bit);
}

struct DecodedInst {
    uint32_t opcode;   // bits [6:0]
    uint32_t rd;       // bits [11:7]
    uint32_t funct3;   // bits [14:12]
    uint32_t rs1;      // bits [19:15]
    uint32_t rs2;      // bits [24:20]
    uint32_t funct7;   // bits [31:25]
    int32_t imm;       // decoded immediate (sign-extended)
};

DecodedInst decode(uint32_t inst) {
    DecodedInst d;
    d.opcode = inst & 0x7F;
    d.rd     = (inst >> 7) & 0x1F;
    d.funct3 = (inst >> 12) & 0x7;
    d.rs1    = (inst >> 15) & 0x1F;
    d.rs2    = (inst >> 20) & 0x1F;
    d.funct7 = (inst >> 25) & 0x7F;
    
    switch (d.opcode) {
        case 0x13: case 0x03: case 0x67: case 0x73: // I-type
            d.imm = sign_extend(inst >> 20, 12);
            break;
        case 0x23: // S-type
            d.imm = sign_extend(((inst >> 25) << 5) | ((inst >> 7) & 0x1F), 12);
            break;
        case 0x63: // B-type
            d.imm = sign_extend(
                ((inst >> 31) << 12) |
                (((inst >> 7) & 1) << 11) |
                (((inst >> 25) & 0x3F) << 5) |
                (((inst >> 8) & 0xF) << 1),
                13);
            break;
        case 0x37: case 0x17: // U-type
            d.imm = inst & 0xFFFFF000;
            break;
        case 0x6F: // J-type
            d.imm = sign_extend(
                ((inst >> 31) << 20) |
                (((inst >> 12) & 0xFF) << 12) |
                (((inst >> 20) & 1) << 11) |
                (((inst >> 21) & 0x3FF) << 1),
                21);
            break;
        default:
            d.imm = 0;
            break;
    }
    return d;
}

// Instruction name lookup
const char* inst_name(uint32_t opcode, uint32_t funct3, uint32_t funct7) {
    
    
    if (opcode == 51 && funct3 == 0 && funct7 == 0) return "ADD";
    
    
    
    if (opcode == 51 && funct3 == 0 && funct7 == 32) return "SUB";
    
    
    
    if (opcode == 51 && funct3 == 7 && funct7 == 0) return "AND";
    
    
    
    if (opcode == 51 && funct3 == 6 && funct7 == 0) return "OR";
    
    
    
    if (opcode == 51 && funct3 == 4 && funct7 == 0) return "XOR";
    
    
    
    if (opcode == 51 && funct3 == 2 && funct7 == 0) return "SLT";
    
    
    
    if (opcode == 51 && funct3 == 3 && funct7 == 0) return "SLTU";
    
    
    
    if (opcode == 51 && funct3 == 1 && funct7 == 0) return "SLL";
    
    
    
    if (opcode == 51 && funct3 == 5 && funct7 == 0) return "SRL";
    
    
    
    if (opcode == 51 && funct3 == 5 && funct7 == 32) return "SRA";
    
    
    
    if (opcode == 19 && funct3 == 0) return "ADDI";
    
    
    
    if (opcode == 19 && funct3 == 7) return "ANDI";
    
    
    
    if (opcode == 19 && funct3 == 6) return "ORI";
    
    
    
    if (opcode == 19 && funct3 == 4) return "XORI";
    
    
    
    if (opcode == 19 && funct3 == 2) return "SLTI";
    
    
    
    if (opcode == 19 && funct3 == 3) return "SLTIU";
    
    
    
    if (opcode == 19 && funct3 == 1 && funct7 == 0) return "SLLI";
    
    
    
    if (opcode == 19 && funct3 == 5 && funct7 == 0) return "SRLI";
    
    
    
    if (opcode == 19 && funct3 == 5 && funct7 == 32) return "SRAI";
    
    
    
    if (opcode == 3 && funct3 == 2) return "LW";
    
    
    
    if (opcode == 35 && funct3 == 2) return "SW";
    
    
    
    if (opcode == 99 && funct3 == 0) return "BEQ";
    
    
    
    if (opcode == 99 && funct3 == 1) return "BNE";
    
    
    
    if (opcode == 99 && funct3 == 4) return "BLT";
    
    
    
    if (opcode == 99 && funct3 == 5) return "BGE";
    
    
    
    if (opcode == 99 && funct3 == 6) return "BLTU";
    
    
    
    if (opcode == 99 && funct3 == 7) return "BGEU";
    
    
    
    if (opcode == 55) return "LUI";
    
    
    
    if (opcode == 23) return "AUIPC";
    
    
    
    if (opcode == 111) return "JAL";
    
    
    
    if (opcode == 103 && funct3 == 0) return "JALR";
    
    
    
    if (opcode == 115 && funct3 == 0) return "ECALL";
    
    
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
    
    int32_t x[32];
    uint32_t PC;
    
    
    int pipeline_cycle;
    int reg_available_at[32];
    int stall_cycles;
    int flush_count;
    vector<PipelineTraceEntry> pipeline_trace;
    
    
    CoreState(int id) : core_id(id), halt(false), total_cycles(0), PC(0) {
        memset(x, 0, sizeof(x));
        
        pipeline_cycle = 0;
        memset(reg_available_at, 0, sizeof(reg_available_at));
        stall_cycles = 0;
        flush_count = 0;
        
    }
    
    
    void reset_pipeline() {
        memset(reg_available_at, 0, sizeof(reg_available_at));
    }
    
};

int NUM_CORES = 1;
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
    uint32_t rd = d.rd, rs1 = d.rs1, rs2 = d.rs2;
    int32_t imm = d.imm;

    
    // Execute: dispatch
    

    
    if (d.opcode == 51 && d.funct3 == 0 && d.funct7 == 0) {
    

        // ADD
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
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
        
        
            core.x[rd] = core.x[rs1] + core.x[rs2];
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 51 && d.funct3 == 0 && d.funct7 == 32) {
    

        // SUB
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
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
        
        
            core.x[rd] = core.x[rs1] - core.x[rs2];
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 51 && d.funct3 == 7 && d.funct7 == 0) {
    

        // AND
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
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
        
        
            core.x[rd] = core.x[rs1] & core.x[rs2];
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 51 && d.funct3 == 6 && d.funct7 == 0) {
    

        // OR
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"OR", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = core.x[rs1] | core.x[rs2];
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 51 && d.funct3 == 4 && d.funct7 == 0) {
    

        // XOR
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"XOR", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = core.x[rs1] ^ core.x[rs2];
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 51 && d.funct3 == 2 && d.funct7 == 0) {
    

        // SLT
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SLT", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = ((int32_t)core.x[rs1] < (int32_t)core.x[rs2]) ? 1 : 0;
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 51 && d.funct3 == 3 && d.funct7 == 0) {
    

        // SLTU
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SLTU", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = ((uint32_t)core.x[rs1] < (uint32_t)core.x[rs2]) ? 1 : 0;
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 51 && d.funct3 == 1 && d.funct7 == 0) {
    

        // SLL
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SLL", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = core.x[rs1] << (core.x[rs2] & 0x1F);
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 51 && d.funct3 == 5 && d.funct7 == 0) {
    

        // SRL
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SRL", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = (uint32_t)core.x[rs1] >> (core.x[rs2] & 0x1F);
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 51 && d.funct3 == 5 && d.funct7 == 32) {
    

        // SRA
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SRA", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = (int32_t)core.x[rs1] >> (core.x[rs2] & 0x1F);
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 19 && d.funct3 == 0) {
    

        // ADDI
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"ADDI", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = core.x[rs1] + imm;
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 19 && d.funct3 == 7) {
    

        // ANDI
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"ANDI", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = core.x[rs1] & imm;
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 19 && d.funct3 == 6) {
    

        // ORI
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"ORI", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = core.x[rs1] | imm;
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 19 && d.funct3 == 4) {
    

        // XORI
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"XORI", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = core.x[rs1] ^ imm;
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 19 && d.funct3 == 2) {
    

        // SLTI
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SLTI", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = ((int32_t)core.x[rs1] < (int32_t)imm) ? 1 : 0;
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 19 && d.funct3 == 3) {
    

        // SLTIU
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SLTIU", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = ((uint32_t)core.x[rs1] < (uint32_t)imm) ? 1 : 0;
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 19 && d.funct3 == 1 && d.funct7 == 0) {
    

        // SLLI
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SLLI", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = core.x[rs1] << (imm & 0x1F);
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 19 && d.funct3 == 5 && d.funct7 == 0) {
    

        // SRLI
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SRLI", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = (uint32_t)core.x[rs1] >> (imm & 0x1F);
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 19 && d.funct3 == 5 && d.funct7 == 32) {
    

        // SRAI
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SRAI", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = (int32_t)core.x[rs1] >> (imm & 0x1F);
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 3 && d.funct3 == 2) {
    

        // LW
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"LW", _if_cycle, _stall});
            }
        }
        
        
            { uint32_t _addr = (uint32_t)((int32_t)core.x[rs1] + imm);
              _mem_addr = _addr;
              memcpy(&core.x[rd], &DataMem[_addr], 4); }
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 1;
        
        
        
        
        
        
        core.pipeline_cycle += simulate_memory_access(_mem_addr);
        
        
    }
    

    
    else if (d.opcode == 35 && d.funct3 == 2) {
    

        // SW
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"SW", _if_cycle, _stall});
            }
        }
        
        
            { uint32_t _addr = (uint32_t)((int32_t)core.x[rs1] + imm);
              _mem_addr = _addr;
              memcpy(&DataMem[_addr], &core.x[rs2], 4); }
        

        core.x[0] = 0;

        
        
        
        
        
        
        
        core.pipeline_cycle += simulate_memory_access(_mem_addr);
        
        
    }
    

    
    else if (d.opcode == 99 && d.funct3 == 0) {
    

        // BEQ
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"BEQ", _if_cycle, _stall});
            }
        }
        
        
            if (core.x[rs1] == core.x[rs2]) { core.PC = current_pc + imm; _branch_taken = true; }
        

        core.x[0] = 0;

        
        
        
        
        
        
    }
    

    
    else if (d.opcode == 99 && d.funct3 == 1) {
    

        // BNE
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"BNE", _if_cycle, _stall});
            }
        }
        
        
            if (core.x[rs1] != core.x[rs2]) { core.PC = current_pc + imm; _branch_taken = true; }
        

        core.x[0] = 0;

        
        
        
        
        
        
    }
    

    
    else if (d.opcode == 99 && d.funct3 == 4) {
    

        // BLT
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"BLT", _if_cycle, _stall});
            }
        }
        
        
            if ((int32_t)core.x[rs1] < (int32_t)core.x[rs2]) { core.PC = current_pc + imm; _branch_taken = true; }
        

        core.x[0] = 0;

        
        
        
        
        
        
    }
    

    
    else if (d.opcode == 99 && d.funct3 == 5) {
    

        // BGE
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"BGE", _if_cycle, _stall});
            }
        }
        
        
            if ((int32_t)core.x[rs1] >= (int32_t)core.x[rs2]) { core.PC = current_pc + imm; _branch_taken = true; }
        

        core.x[0] = 0;

        
        
        
        
        
        
    }
    

    
    else if (d.opcode == 99 && d.funct3 == 6) {
    

        // BLTU
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"BLTU", _if_cycle, _stall});
            }
        }
        
        
            if ((uint32_t)core.x[rs1] < (uint32_t)core.x[rs2]) { core.PC = current_pc + imm; _branch_taken = true; }
        

        core.x[0] = 0;

        
        
        
        
        
        
    }
    

    
    else if (d.opcode == 99 && d.funct3 == 7) {
    

        // BGEU
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            _src_avail = max(_src_avail, core.reg_available_at[rs2]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"BGEU", _if_cycle, _stall});
            }
        }
        
        
            if ((uint32_t)core.x[rs1] >= (uint32_t)core.x[rs2]) { core.PC = current_pc + imm; _branch_taken = true; }
        

        core.x[0] = 0;

        
        
        
        
        
        
    }
    

    
    else if (d.opcode == 55) {
    

        // LUI
        
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
                core.pipeline_trace.push_back({"LUI", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = imm;
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 23) {
    

        // AUIPC
        
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
                core.pipeline_trace.push_back({"AUIPC", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = current_pc + imm;
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 111) {
    

        // JAL
        
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
                core.pipeline_trace.push_back({"JAL", _if_cycle, _stall});
            }
        }
        
        
            core.x[rd] = core.PC;
            core.PC = current_pc + imm;
            _branch_taken = true;
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 103 && d.funct3 == 0) {
    

        // JALR
        
        {
            int _src_avail = 0;
            
            _src_avail = max(_src_avail, core.reg_available_at[rs1]);
            
            int _if_cycle = core.pipeline_cycle;
            int _stall = 0;
            if (_src_avail > core.pipeline_cycle) {
                _stall = _src_avail - core.pipeline_cycle;
                core.stall_cycles += _stall;
                core.pipeline_cycle = _src_avail;
            }
            core.pipeline_cycle++;
            if (core.pipeline_trace.size() < 30) {
                core.pipeline_trace.push_back({"JALR", _if_cycle, _stall});
            }
        }
        
        
            { int32_t _ret = core.PC;
              core.PC = ((int32_t)core.x[rs1] + imm) & ~1;
              core.x[rd] = _ret;
              _branch_taken = true; }
        

        core.x[0] = 0;

        
        
        
        
        core.reg_available_at[rd] = core.pipeline_cycle + 0;
        
        
        
        
        
    }
    

    
    else if (d.opcode == 115 && d.funct3 == 0) {
    

        // ECALL
        
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
                core.pipeline_trace.push_back({"ECALL", _if_cycle, _stall});
            }
        }
        
        
            core.halt = true;
        

        core.x[0] = 0;

        
        
        
        
        
        
    }
    
    else {
        cerr << "Unknown instruction at PC=" << current_pc << " raw=0x" << hex << raw_inst << dec << endl;
        core.halt = true;
    }
    
    
    
    
    if (_branch_taken) {
        core.pipeline_cycle += 2;
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
        for (int i = 0; i < 32; i++) {
            if (cores[c].x[i] != 0) {
                cout << "  x[" << i << "]: " << cores[c].x[i] << endl;
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