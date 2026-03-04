# UADL
Unified Architectural Description Language

1. Motivation and Context
The project is driven by the need for a standardized way to communicate hardware capabilities to high-level software and Large Language Models (LLMs).
LLM Integration: While LLMs can benefit from hardware knowledge, research is needed to quantify this benefit.


Architectural Variance: Hardware architectures vary significantly and see frequent new releases, making it difficult for LLMs to stay updated without a unified description format (e.g., .td files, MLIR, or ADL).


Standardization Gap: ASIC designs are highly varied, and a lack of unified standards has led to a "mess" of custom simulators.


Software Optimization: There is currently no standardized method to write specialized, optimized software code for diverse accelerators.


Relevant Projects: This work builds upon or relates to existing projects like LISA and CIRCT.


2. Language Selection for LLM Optimization
The choice of data format is critical for ensuring LLMs can accurately parse and process architectural data efficiently.
Format
Strengths
Use Case
YAML
Strongest for accuracy in complex nested data; visual hierarchy via indentation is highly readable for LLMs.


Core structural definitions.
Markdown
Most token-efficient format (34–38% fewer tokens than JSON) while maintaining high accuracy.


General documentation and reporting.
JSON
Industry standard for APIs and data exchange.


Inter-tool communication.
XML
Uses tags (e.g., <Instructions>) to create clear conceptual boundaries that prevent instruction drift, despite being token-inefficient.


Prompt structuring and instructions.

3. Memory Requirements and Consistency
UADL must define the memory consistency model and address space layout to ensure software compatibility.

Partitioned Memory: Features distinct physical and virtual memory spaces, requiring the generation of explicit data synchronization calls.


Unified Main Memory: Utilizes shared physical memory combined with partitioned virtual spaces.


Fully Unified Virtual Memory: Employs shared page tables to allow for zero-copy operations.


Optimization: Support is required to optimize for pointer-based sharing within these models.


4. Key Requirements of UADL
To be effective, the UADL must support several layers of abstraction and formal specification.
Structural Decomposition
The language must model a system as an assembly of three primary elements:

Components: Functional blocks such as CPU cores, Tensor cores, Memory controllers, and DMA engines.


Connectors: Communication paths defined by protocols, bandwidth, and latency (e.g., AXI, NVLink, PCIe).


Configurations: The specific arrangement and interconnection topology of these components.


Behavioral and Physical Constraints
Behavioral Semantics: Defines instruction sets or logic operations, including register file definitions, opcode mappings, and state-transition semantics.


Constraint Specification: Formally describes non-functional requirements such as:
Timing: Critical path delays, clock domains, and setup/hold requirements.
+1


Resources: Physical counts of LUTs, DSPs, ALUs, and memory capacity.


Power: Thermal Design Power (TDP) and energy-per-operation profiles.


Hierarchical Abstraction: Allows users to view architecture from a high-level SoC topology down to cycle-accurate pipeline interactions.


5. Implementation Layers
The UADL implementation is divided into four distinct layers of abstraction.
Layer 1: Structural Layer (The Netlist of Abstractions)
This YAML-based layer describes the hardware topology.

Processing Units: Includes core types (Scalar/Vector/Tensor), thread handling (SMT/Warp), and ISA pointers.


Memory Entities: Specifies capacity, bandwidth, and cache policies (Write-through vs. Write-back).


Interconnect Entities: Describes topologies like Mesh, Ring, or Crossbar and their arbitration protocols.


Layer 2: Behavioral Layer (The Semantic Contract)
This layer defines the "meaning" of operations.

CPUs/ASIPs: Focuses on the instruction set.


ASICs: Defined via functional primitives.


Operations: Specifies inputs, outputs, side effects, and resource requirements.


State Machines: Models pipeline stages and control logic for cycle-accurate simulation.


Layer 3: Constraint Layer (The Physical Boundaries)
Defines the "reality" of the implementation.

Metrics: Includes peak GFLOPS, memory bandwidth, and power consumption per instruction.


Synthesizability: Details timing arcs and area footprints for FPGA and ASIC implementations.


Layer 4: Software Interface Layer (The Developer's View)
Provides metadata for the software stack.

Driver/API Metadata: Covers register offsets, interrupt vectors, and DMA descriptors.


Compiler Pragmas: Standardized tags to guide loop unrolling, vectorization, and memory partitioning.


6. UADL Compiler and Simulation
A primary goal of the UADL framework is the creation of a Simulation Compiler. This tool is intended to auto-generate a simulator directly from the UADL specification, streamlining the hardware-software co-design process.
+1

Would you like me to generate a sample YAML file based on these Structural Layer requirements to see how the code might look?
