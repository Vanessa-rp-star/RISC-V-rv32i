/*
 * Copyright (c) 2024 Your Name
 * SPDX-License-Identifier: Apache-2.0
 */
`default_nettype none

// =============================================================================
// MÓDULO PRINCIPAL (WRAPPER PARA TINY TAPEOUT)
// =============================================================================
module tt_um_vanessa_rocha (
    input  wire [7:0] ui_in,    // Entradas dedicadas
    output wire [7:0] uo_out,   // Salidas dedicadas
    input  wire [7:0] uio_in,   // IOs: Entradas
    output wire [7:0] uio_out,  // IOs: Salidas
    output wire [7:0] uio_oe,   // IOs: Enable (1=salida, 0=entrada)
    input  wire       ena,      // Habilitador general
    input  wire       clk,      // Reloj
    input  wire       rst_n     // Reset activo en BAJO
);

    // 1. Acondicionamiento de señales
    // Tiny Tapeout usa reset activo en bajo (rst_n), pero tu CPU usa reset activo en alto.
    wire reset_cpu = ~rst_n; 

    // Cables internos para extraer los datos de 32 bits de tu CPU
    wire [31:0] pc_out;
    wire [31:0] data_addr_out;
    wire [31:0] data_write_out;
    wire [3:0]  mem_write_mask;

    // 2. Instanciación de tu procesador RISC-V
    single_cycle_rv32i_vr mi_procesador (
        .clk(clk),
        .reset(reset_cpu),
        .en(ena),
        // IMPORTANTE: Al no tener pines suficientes para meter 32 bits de instrucción,
        // por ahora inyectamos un NOP (addi x0, x0, 0) o deberás conectar una ROM interna aquí.
        .instr_bus_in(32'h00000013),       
        .data_read_bus_in(32'h00000000),   
        .pc_bus_out(pc_out),
        .data_addr_bus_out(data_addr_out),
        .data_write_bus_out(data_write_out),
        .mem_write_mask_out(mem_write_mask)
    );

    // 3. Multiplexor de Salida (Ver 32 bits a través de 8 pines)
    // Usamos los primeros 2 interruptores de entrada (ui_in[1:0]) para elegir qué byte del PC ver.
    reg [7:0] salida_mux;
    
    always @(*) begin
        case (ui_in[1:0])
            2'b00: salida_mux = pc_out[7:0];    // Byte 0 (LBS)
            2'b01: salida_mux = pc_out[15:8];   // Byte 1
            2'b10: salida_mux = pc_out[23:16];  // Byte 2
            2'b11: salida_mux = pc_out[31:24];  // Byte 3 (MSB)
        endcase
    end

    // Asignamos el resultado del multiplexor a los pines de salida dedicados
    assign uo_out = salida_mux;

    // Configuramos los pines bidireccionales como salidas para ver más datos
    assign uio_oe  = 8'b11111111; // 1 = Todos configurados como salida
    assign uio_out = data_addr_out[7:0]; // Aquí mostramos los 8 bits bajos de la ALU/Dirección

    // Silenciamos advertencias de Yosys/OpenLane sobre pines no usados
    wire _unused = &{ui_in[7:2], uio_in, 1'b0};

//endmodule


// =============================================================================
// TU CÓDIGO: CORE RISC-V Y SUBMÓDULOS
// =============================================================================

module single_cycle_rv32i_vr (
    input  wire clk,
    input  wire reset,
    input  wire en,
    input  wire [31:0] instr_bus_in,
    input  wire [31:0] data_read_bus_in,
    output wire [31:0] pc_bus_out,
    output wire [31:0] data_addr_bus_out,
    output wire [31:0] data_write_bus_out,
    output wire [3:0]  mem_write_mask_out
);

    reg [31:0] instr_reg;
    reg [31:0] data_read_reg;

    always @(posedge clk) begin
        if (reset) begin
            instr_reg <= 32'h00000000;
            data_read_reg <= 32'h00000000;
        end else begin
            instr_reg <= instr_bus_in;
            data_read_reg <= data_read_bus_in;
        end
    end

    wire [31:0] PC, PC_next, imm32, rd1, rd2, SrcA, SrcB, ALUResult, Result_mux_out;
    wire [31:0] csr_rdata, trap_pc, LoadData;
    wire        trap_taken, CSRWrite, is_ecall, is_mret, Zero, lt, ltu;
    wire [1:0]  ResultSrc, ALUSrcA;
    wire [2:0]  ImmSrc;
    wire        ALUSrc, RegWrite, PCSrc, JALR_Src, MemWrite;
    wire [3:0]  ALUControl;

    assign pc_bus_out         = PC;
    assign data_addr_bus_out  = ALUResult;
    assign data_write_bus_out = rd2 << (ALUResult[1:0] * 8);

    wire [31:0] pc_plus_4    = PC + 4;
    wire [31:0] pc_plus_imm  = PC + imm32;
    wire [31:0] rd1_plus_imm = (rd1 + imm32) & 32'hFFFFFFFE;

    reg [31:0] next_pc_logic;
    always @(*) begin
        if (trap_taken)      next_pc_logic = trap_pc;
        else if (JALR_Src)   next_pc_logic = rd1_plus_imm;
        else if (PCSrc)      next_pc_logic = pc_plus_imm;
        else                 next_pc_logic = pc_plus_4;
    end
    assign PC_next = next_pc_logic;

    ProgramCounter u_pc (clk, en, reset, PC_next, PC);

    controller u_control (
        instr_reg[6:0], instr_reg[14:12], instr_reg[30], instr_reg[31:20],
        Zero, lt, ltu, PCSrc, JALR_Src, MemWrite, ALUSrc, RegWrite,
        CSRWrite, is_ecall, is_mret, ResultSrc, ALUSrcA, ImmSrc, ALUControl
    );

    sign_extend u_sext (instr_reg, ImmSrc, imm32);

    wire valid_RegWrite = RegWrite && !trap_taken && en;
    regfile u_rf (clk, reset, valid_RegWrite, instr_reg[19:15], instr_reg[24:20], instr_reg[11:7], Result_mux_out, rd1, rd2);

    csr_unit u_csr (
        clk, reset, instr_reg[31:20], rd1, instr_reg[14:12],
        CSRWrite && en && !trap_taken, PC, is_ecall, is_mret,
        1'b0, 1'b0, csr_rdata, trap_pc, trap_taken
    );

    assign SrcA = (ALUSrcA == 2'b01) ? PC : (ALUSrcA == 2'b10) ? 32'b0 : rd1;
    assign SrcB = ALUSrc ? imm32 : rd2;

    ALU u_alu (SrcA, SrcB, ALUControl, ALUResult, Zero, lt, ltu);

    load_unit u_load (instr_reg[14:12], data_read_reg, ALUResult[1:0], LoadData);

    reg [3:0] wm;
    always @(*) begin
        if (!MemWrite || !en || trap_taken) wm = 4'b0000;
        else case (instr_reg[14:12])
            3'b000: wm = 4'b0001 << ALUResult[1:0];
            3'b001: wm = 4'b0011 << ALUResult[1:0];
            3'b010: wm = 4'b1111;
            default: wm = 4'b0000;
        endcase
    end
    assign mem_write_mask_out = wm;

    assign Result_mux_out = (ResultSrc == 2'b00) ? ALUResult :
                            (ResultSrc == 2'b01) ? LoadData :
                            (ResultSrc == 2'b10) ? pc_plus_4 : csr_rdata;
endmodule

module ProgramCounter(input clk, en, reset, input [31:0] PC_next, output reg [31:0] PC);
   always @(posedge clk) if (reset) PC <= 32'h80000000; else if (en) PC <= PC_next;
endmodule

module ALU(input [31:0] SrcA, SrcB, input [3:0] ALUControl, output reg [31:0] ALUResult, output Zero, lt, ltu);
    wire signed [31:0] a_sig = SrcA;
    wire signed [31:0] b_sig = SrcB;
    always @(*) case (ALUControl)
        4'b0000: ALUResult = SrcA + SrcB;
        4'b0001: ALUResult = SrcA - SrcB;
        4'b0010: ALUResult = SrcA & SrcB;
        4'b0011: ALUResult = SrcA | SrcB;
        4'b0100: ALUResult = SrcA ^ SrcB;
        4'b0101: ALUResult = (a_sig < b_sig) ? 1 : 0;
        4'b0110: ALUResult = SrcA << SrcB[4:0];
        4'b0111: ALUResult = (SrcA < SrcB) ? 1 : 0;
        4'b1000: ALUResult = SrcA >> SrcB[4:0];
        4'b1001: ALUResult = a_sig >>> SrcB[4:0];
        default: ALUResult = 0;
    endcase
    assign Zero = (SrcA == SrcB);
    assign lt   = (a_sig < b_sig);
    assign ltu  = (SrcA < SrcB);
endmodule

module controller(input [6:0] op, input [2:0] funct3, input funct7b5, input [11:0] funct12, input Zero, lt, ltu, output PCSrc, JALR_Src, MemWrite, ALUSrc, RegWrite, CSRWrite, is_ecall, is_mret, output [1:0] ResultSrc, ALUSrcA, output [2:0] ImmSrc, output [3:0] ALUControl);
    wire [1:0] ALUOp; wire Branch, Jump; reg TakeBranch;
    main_decoder md (op, funct3, funct12, ResultSrc, ALUSrcA, ALUOp, ImmSrc, MemWrite, Branch, ALUSrc, RegWrite, Jump, CSRWrite, is_ecall, is_mret);
    alu_decoder ad (op, op[5], funct3, funct7b5, ALUOp, ALUControl);
    always @(*) case(funct3)
        3'b000: TakeBranch = Zero;  3'b001: TakeBranch = !Zero;
        3'b100: TakeBranch = lt;    3'b101: TakeBranch = !lt;
        3'b110: TakeBranch = ltu;   3'b111: TakeBranch = !ltu;
        default: TakeBranch = 0;
    endcase
    assign JALR_Src = (op == 7'b1100111); assign PCSrc = Jump | (Branch & TakeBranch);
endmodule

module main_decoder(input [6:0] op, input [2:0] funct3, input [11:0] funct12, output reg [1:0] ResultSrc, ALUSrcA, ALUOp, output reg [2:0] ImmSrc, output reg MemWrite, Branch, ALUSrc, RegWrite, Jump, CSRWrite, is_ecall, is_mret);
    always @(*) begin
        RegWrite = 0; ImmSrc = 3'b000; ALUSrc = 0; ALUSrcA = 2'b00; MemWrite = 0; ResultSrc = 2'b00; Branch = 0; ALUOp = 2'b00; Jump = 0; CSRWrite = 0; is_ecall = 0; is_mret = 0;
        case(op)
            7'b0000011: begin RegWrite = 1; ALUSrc = 1; ResultSrc = 2'b01; end
            7'b0100011: begin ImmSrc = 3'b001; ALUSrc = 1; MemWrite = 1; end
            7'b0110011: begin RegWrite = 1; ALUOp = 2'b10; end
            7'b0010011: begin RegWrite = 1; ALUSrc = 1; ALUOp = 2'b10; end
            7'b1100011: begin Branch = 1; ImmSrc = 3'b010; ALUOp = 2'b01; end
            7'b1101111: begin RegWrite = 1; Jump = 1; ImmSrc = 3'b011; ResultSrc = 2'b10; ALUSrcA = 2'b01; end
            7'b1100111: begin RegWrite = 1; Jump = 1; ALUSrc = 1; ResultSrc = 2'b10; end
            7'b0010111: begin RegWrite = 1; ImmSrc = 3'b100; ALUSrc = 1; ALUSrcA = 2'b01; end
            7'b0110111: begin RegWrite = 1; ImmSrc = 3'b100; ALUSrc = 1; ALUSrcA = 2'b10; end
            7'b1110011: begin if (funct3 == 0) begin if (funct12 == 12'h000) is_ecall = 1; else if (funct12 == 12'h302) is_mret = 1; end else CSRWrite = 1; end
        endcase
    end
endmodule

module alu_decoder(input [6:0] op, input opb5, input [2:0] funct3, input funct7b5, input [1:0] ALUOp, output reg [3:0] ALUControl);
    always @(*) case(ALUOp)
        2'b00: ALUControl = 4'b0000; 2'b01: ALUControl = 4'b0001;
        2'b10: case(funct3)
            3'b000: ALUControl = (opb5 && funct7b5 && op==7'b0110011) ? 4'b0001 : 4'b0000;
            3'b001: ALUControl = 4'b0110; 3'b010: ALUControl = 4'b0101; 3'b011: ALUControl = 4'b0111;
            3'b100: ALUControl = 4'b0100; 3'b101: ALUControl = funct7b5 ? 4'b1001 : 4'b1000;
            3'b110: ALUControl = 4'b0011; 3'b111: ALUControl = 4'b0010;
        endcase
        default: ALUControl = 0;
    endcase
endmodule

module regfile(input clk, reset, we, input [4:0] rs1, rs2, rd, input [31:0] wd, output [31:0] rd1, rd2);
    reg [31:0] regs [0:31];
    integer i;
    assign rd1 = (rs1 == 0) ? 0 : regs[rs1];
    assign rd2 = (rs2 == 0) ? 0 : regs[rs2];
    always @(posedge clk) if (reset)  for (i=0; i<32; i=i+1) regs[i] <= 0;
    else if (we && rd != 0) regs[rd] <= wd;
endmodule

module sign_extend(input [31:0] instr, input [2:0] ImmSrc, output reg [31:0] imm32);
    always @(*) begin
        case(ImmSrc)
            3'b000: imm32 = { {20{instr[31]}}, instr[31:20] };
            3'b001: imm32 = { {20{instr[31]}}, instr[31:25], instr[11:7] };
            3'b010: imm32 = { {20{instr[31]}}, instr[7], instr[30:25], instr[11:8], 1'b0 };
            3'b011: imm32 = { {12{instr[31]}}, instr[19:12], instr[20], instr[30:21], 1'b0 };
            3'b100: imm32 = { instr[31:12], 12'b0 };
            default: imm32 = 32'b0;
        endcase
    end
endmodule

module load_unit (input [2:0] funct3, input [31:0] ReadData, input [1:0] byte_sel, output reg [31:0] LoadData);
    reg [7:0] b; reg [15:0] h;
    always @(*) begin
        case(byte_sel) 2'b00: b=ReadData[7:0]; 2'b01: b=ReadData[15:8]; 2'b10: b=ReadData[23:16]; 2'b11: b=ReadData[31:24]; endcase
        h = byte_sel[1] ? ReadData[31:16] : ReadData[15:0];
        case(funct3) 3'b000: LoadData = {{24{b[7]}}, b}; 3'b001: LoadData = {{16{h[15]}}, h}; 3'b010: LoadData = ReadData; 3'b100: LoadData = {24'b0, b}; 3'b101: LoadData = {16'b0, h}; default: LoadData = 32'b0; endcase
    end
endmodule

module csr_unit(input clk, reset, input [11:0] csr_addr, input [31:0] wdata, input [2:0] funct3, input csr_we, input [31:0] pc_current, input is_ecall, is_mret, external_interrupt, pc_misaligned, output reg [31:0] rdata, trap_pc, output trap_taken);
    reg [31:0] mtvec, mepc, mcause;
    assign trap_taken = is_ecall | is_mret | external_interrupt | pc_misaligned;
    assign trap_pc = is_mret ? mepc : mtvec;
    always @(*) case(csr_addr) 12'h305: rdata = mtvec; 12'h341: rdata = mepc; 12'h342: rdata = mcause; default: rdata = 0; endcase
    always @(posedge clk) if (reset) begin mtvec<=0; mepc<=0; mcause<=0; end else begin
        if (pc_misaligned) begin mepc <= pc_current; mcause <= 0; end
        else if (is_ecall) begin mepc <= pc_current; mcause <= 11; end
        else if (csr_we) case(csr_addr) 12'h305: mtvec <= wdata; 12'h341: mepc <= wdata; 12'h342: mcause <= wdata; endcase
    end
endmodule
endmodule

     
           


