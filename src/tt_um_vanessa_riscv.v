// Single Cycle RV32I 
// By: Vanessa RP

`default_nettype none

// =============================================================================
// MÓDULO PRINCIPAL (WRAPPER PARA TINY TAPEOUT)
// =============================================================================
module tt_um_vanessa_riscv #(
   
    parameter CLK_FREQ_HZ = 10_000_000,
    parameter BAUD_RATE   = 115200
) (
    // ---- Pinout fisico en el board de Tiny Tapeout ----
    // ui_in[3]  = UART RX: conectar al pin TX de tu adaptador USB-Serial
    //            
    input  wire [7:0] ui_in,
    // uo_out[4] = UART TX: conectar al pin RX de tu adaptador USB-Serial.
    //             uo_out[7]=modo(1=RUN) [6]=cargando [5]=tx_busy
    //             [3:0]=PC bajo
    output wire [7:0] uo_out,
    // uio_in[2] = SPI MISO (entrada, desde el periferico SPI externo)
    input  wire [7:0] uio_in,
    // uio_out[0]=CS  uio_out[1]=MOSI  uio_out[3]=SCK  (convencion Pmod SPI
    // estandar: CS,MOSI,MISO,SCK en la fila del header). Conectar al header
    // PMOD "standard" de la demoboard (sigue el spec de Digilent) 
    // usar un Pmod SPI real; para loopback de prueba, puente MOSI<->MISO.
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire        ena,
    input  wire        clk,     // Reloj del RP2040 de la demoboard, 20 MHz
    input  wire        rst_n    // Reset del RP2040 de la demoboard, activo en bajo
);
 
    localparam CLKS_PER_BIT = CLK_FREQ_HZ / BAUD_RATE;
 
    localparam INSTR_DEPTH = 24;  // 24 instrucciones de 32b = 96 bytes de programa
    // NOTA: reducido de 64 a 24 para bajar el conteo de flip-flops de la
    // memoria de instrucciones (64->24 palabras ahorra (64-24)*32=1280
    
    localparam DATA_DEPTH  = 16;  // 16 words de 32b = 64 bytes de datos
    localparam IAWIDTH = $clog2(INSTR_DEPTH);
    localparam DAWIDTH = $clog2(DATA_DEPTH);
    localparam RAM_BYTES = DATA_DEPTH * 4;
 
    wire sys_rst = ~rst_n;
 
    // =====================================================================
    // FSM de arranque: LOAD (recibiendo programa) -> RUN (ejecutando)
    // =====================================================================
    localparam S_LOAD = 1'b0, S_RUN = 1'b1;
    reg  state;
    wire load_complete;
 
    always @(posedge clk) begin
        if (sys_rst)
            state <= S_LOAD;
        else if (state == S_LOAD && load_complete)
            state <= S_RUN;
    end
 
    wire cpu_reset = sys_rst | (state == S_LOAD);
    wire cpu_en    = ena & (state == S_RUN);
 
    // =====================================================================
    // UART fisico compartido (bootloader durante LOAD, periferico durante RUN)
    // =====================================================================
    wire [7:0] rx_data;
    wire       rx_done;
 
    Receiver_RxD #(.CLKS_PER_BIT(CLKS_PER_BIT)) mi_rx (
        .clk    (clk),
        .reset  (sys_rst),
        .RxD    (ui_in[3]),
        .RxData (rx_data),
        .rx_done(rx_done)
    );
 
  
    reg rx_flag;
    always @(posedge clk) begin
        if (sys_rst || state == S_LOAD)
            rx_flag <= 1'b0;
        else if (rx_done)
            rx_flag <= 1'b1;
        else if (uart_rx_ack)
            rx_flag <= 1'b0;
    end
 
    wire       tx_pin;
    wire       tx_busy;
    wire       tx_start;
    wire [7:0] tx_data;
 
    Transmitter_TxD #(.CLKS_PER_BIT(CLKS_PER_BIT)) mi_tx (
        .clk     (clk),
        .reset   (sys_rst),
        .tx_start(tx_start),
        .tx_data (tx_data),
        .tx_busy (tx_busy),
        .TxD     (tx_pin)
    );
 
    // =====================================================================
    // Bootloader: arma words de 32b desde bytes UART y los escribe en imem
    // =====================================================================
    wire                  imem_we_boot;
    wire [IAWIDTH-1:0]    imem_waddr_boot;
    wire [31:0]           imem_wdata_boot;
    wire                  loading;
 
    uart_bootloader #(.DEPTH(INSTR_DEPTH)) mi_boot (
        .clk     (clk),
        .rst     (sys_rst),
        .rx_done (rx_done),
        .rx_data (rx_data),
        .imem_we   (imem_we_boot),
        .imem_waddr(imem_waddr_boot),
        .imem_wdata(imem_wdata_boot),
        .loading   (loading),
        .done      (load_complete)
    );
 
    // =====================================================================
    // Memoria de instrucciones (cargable, lectura combinacional)
    // =====================================================================
    wire [31:0] pc_out;
    wire [31:0] current_instruction;
 
    instruction_mem #(.DEPTH(INSTR_DEPTH)) mi_imem (
        .clk   (clk),
        .we    (imem_we_boot),
        .waddr (imem_waddr_boot),
        .wdata (imem_wdata_boot),
        .raddr (pc_out),
        .instr (current_instruction)
    );
 
    // =====================================================================
    // Memoria de datos + I/O mapeado en memoria (RAM, UART, SPI, GPIO-in)
    // =====================================================================
    wire [31:0] data_addr_out;
    wire [31:0] data_write_out;
    wire [3:0]  mem_write_mask;
    wire [31:0] data_read_from_ram;
 
    localparam ADDR_UART_TX  = 32'h00000040;
    localparam ADDR_UART_RX  = 32'h00000044;
    localparam ADDR_SPI_DATA = 32'h00000048;
    localparam ADDR_GPIO_IN  = 32'h00000050;
 
    wire is_ram      = (data_addr_out < RAM_BYTES);
    wire is_uart_tx  = (data_addr_out == ADDR_UART_TX);
    wire is_uart_rx  = (data_addr_out == ADDR_UART_RX);
    wire is_spi_data = (data_addr_out == ADDR_SPI_DATA);
    wire is_gpio_in  = (data_addr_out == ADDR_GPIO_IN);
 
    wire [DAWIDTH-1:0] ram_word_addr = data_addr_out[2 +: DAWIDTH];
    wire mem_write_active = (mem_write_mask != 4'b0000);
    wire ram_write_enable = mem_write_active && is_ram;
 
    assign tx_start = mem_write_active && is_uart_tx && (state == S_RUN);
    assign tx_data  = data_write_out[7:0];
 
    // Escribir cualquier valor a 0x44 (UART RX) es el "acknowledge" que el
    // software usa para bajar rx_flag despues de leer el byte recibido.
    wire uart_rx_ack = mem_write_active && is_uart_rx && (state == S_RUN);
 
    data_mem #(.DEPTH(DATA_DEPTH)) mi_dmem (
        .clk     (clk),
        .we      (ram_write_enable),
        .addr    (ram_word_addr),
        .data_in (data_write_out),
        .data_out(data_read_from_ram)
    );
 
    // ---- SPI maestro ----
    wire        spi_start = mem_write_active && is_spi_data && (state == S_RUN);
    wire [7:0]  spi_tx_byte = data_write_out[7:0];
    wire [7:0]  spi_rx_byte;
    wire        spi_busy;
    wire        spi_sclk, spi_mosi, spi_cs_n;
    wire        spi_miso = uio_in[2];
 
    spi_master #(.CLK_DIV(4)) mi_spi (
        .clk    (clk),
        .rst    (sys_rst),
        .start  (spi_start),
        .tx_byte(spi_tx_byte),
        .rx_byte(spi_rx_byte),
        .busy   (spi_busy),
        .sclk   (spi_sclk),
        .mosi   (spi_mosi),
        .miso   (spi_miso),
        .cs_n   (spi_cs_n)
    );
 
    //  Mux de lectura de datos hacia el CPU 
    wire [31:0] final_data_read =
        is_uart_rx  ? {23'b0, rx_flag, rx_data}       :
        is_uart_tx  ? {31'b0, tx_busy}                :
        is_spi_data ? {23'b0, spi_busy, spi_rx_byte}  :
        is_gpio_in  ? {24'b0, ui_in}                  :
                      data_read_from_ram;
 

    // Procesador RISC-V (fetch/lectura de datos combinacionales 
 
    single_cycle_rv32i_vr mi_procesador (
        .clk               (clk),
        .reset             (cpu_reset),
        .en                (cpu_en),
        .instr_bus_in      (current_instruction),
        .data_read_bus_in  (final_data_read),
        .pc_bus_out        (pc_out),
        .data_addr_bus_out (data_addr_out),
        .data_write_bus_out(data_write_out),
        .mem_write_mask_out(mem_write_mask)
    );
 

    // Salidas fisicas
    // =====================================================================
    // uo_out[7]=modo(1=RUN) [6]=cargando [5]=tx_busy [4]=UART TX [3:0]=PC bajo
    assign uo_out = {state, loading, tx_busy, tx_pin, pc_out[3:0]};
 
    // uio: SPI en uio[3:0] = SCK,MISO(entrada),MOSI,CS. uio[7:4] libres (entrada).
    assign uio_out = {4'b0000, spi_sclk, 1'b0, spi_mosi, spi_cs_n};
    assign uio_oe  = 8'b0000_1011; // [3]=out(SCK) [2]=in(MISO) [1]=out(MOSI) [0]=out(CS)
 
endmodule
 
 
// =============================================================================
// BOOTLOADER: arma instrucciones de 32b desde bytes UART (LSB primero) y las
// escribe en la memoria de instrucciones. Al llenar INSTR_DEPTH palabras,
// levanta 'done' y se congela hasta el siguiente reset del chip.
// =============================================================================
module uart_bootloader #(
    parameter DEPTH  = 64,
    parameter AWIDTH = $clog2(DEPTH)
)(
    input  wire clk,
    input  wire rst,
    input  wire rx_done,
    input  wire [7:0] rx_data,
    output reg          imem_we,
    output reg [AWIDTH-1:0] imem_waddr,
    output reg [31:0]   imem_wdata,
    output reg          loading,
    output reg          done
);
    reg [1:0]        byte_idx;
    reg [31:0]        shift_word;
    reg [AWIDTH-1:0] waddr_cnt;
 
    always @(posedge clk) begin
        if (rst) begin
            byte_idx   <= 2'd0;
            shift_word <= 32'd0;
            waddr_cnt  <= {AWIDTH{1'b0}};
            imem_we    <= 1'b0;
            loading    <= 1'b1;
            done       <= 1'b0;
        end else begin
            imem_we <= 1'b0; // pulso de un solo ciclo por palabra completa
            if (loading && rx_done) begin
                if (byte_idx == 2'd3) begin
                    imem_we    <= 1'b1;
                    imem_waddr <= waddr_cnt;
                    imem_wdata <= {rx_data, shift_word[23:0]};
                    byte_idx   <= 2'd0;
                    if (waddr_cnt == DEPTH-1) begin
                        loading <= 1'b0;
                        done    <= 1'b1;
                    end else begin
                        waddr_cnt <= waddr_cnt + 1'b1;
                    end
                end else begin
                    shift_word[byte_idx*8 +: 8] <= rx_data;
                    byte_idx <= byte_idx + 1'b1;
                end
            end
        end
    end
endmodule
 
 
// =============================================================================
// MEMORIA DE INSTRUCCIONES: escritura sincrona (bootloader), lectura
// combinacional (necesaria para fetch de ciclo unico real).
// =============================================================================
module instruction_mem #(
    parameter DEPTH  = 64,
    parameter AWIDTH = $clog2(DEPTH)
)(
    input  wire clk,
    input  wire            we,
    input  wire [AWIDTH-1:0] waddr,
    input  wire [31:0]     wdata,
    input  wire [31:0]     raddr,   // direccion de byte (PC)
    output wire [31:0]     instr
);
    reg [31:0] mem [0:DEPTH-1];
    integer i;
 
    initial begin
        for (i = 0; i < DEPTH; i = i + 1)
            mem[i] = 32'h00000013; // NOP: addi x0,x0,0
    end
 
    always @(posedge clk)
        if (we) mem[waddr] <= wdata;
 
    assign instr = mem[raddr[AWIDTH+1:2]];
endmodule
 
 
// =============================================================================
// MEMORIA DE DATOS: escritura sincrona, lectura combinacional (ciclo unico).
// =============================================================================
module data_mem #(
    parameter DEPTH  = 16,
    parameter AWIDTH = $clog2(DEPTH)
)(
    input  wire clk,
    input  wire we,
    input  wire [AWIDTH-1:0] addr,
    input  wire [31:0] data_in,
    output wire [31:0] data_out
);
    reg [31:0] mem [0:DEPTH-1];
    integer i;
 
    initial begin
        for (i = 0; i < DEPTH; i = i + 1)
            mem[i] = 32'h00000000;
    end
 
    always @(posedge clk)
        if (we) mem[addr] <= data_in;
 
    assign data_out = mem[addr]; // lectura asincrona: dato listo en el mismo ciclo
endmodule
 
 
// =============================================================================
// RECEPTOR UART (parametrizado por CLKS_PER_BIT, calculado a partir de
// CLK_FREQ_HZ/BAUD_RATE en el modulo top)
// =============================================================================
module Receiver_RxD #(
    parameter CLKS_PER_BIT = 104
)(
    input  wire clk,
    input  wire reset,
    input  wire RxD,
    output wire [7:0] RxData,
    output reg  rx_done
);
    localparam HALF_BIT = CLKS_PER_BIT / 2;
 
    reg [$clog2(CLKS_PER_BIT+1)-1:0] baud_cnt;
    reg [2:0] bit_ptr;
    reg [7:0] rx_reg;
    reg [1:0] state; // 0=idle 1=recibiendo bits 2=stop bit
 
    assign RxData = rx_reg;
 
    always @(posedge clk) begin
        if (reset) begin
            state <= 0; rx_done <= 0; baud_cnt <= 0; bit_ptr <= 0; rx_reg <= 0;
        end else begin
            rx_done <= 0;
            case (state)
                0: begin // esperando flanco de bajada del start bit
                    if (!RxD) begin
                        if (baud_cnt == HALF_BIT) begin
                            state <= 1; baud_cnt <= 0; bit_ptr <= 0;
                        end else baud_cnt <= baud_cnt + 1;
                    end else baud_cnt <= 0;
                end
                1: begin // 8 bits de datos, LSB primero
                    if (baud_cnt == CLKS_PER_BIT-1) begin
                        baud_cnt <= 0; rx_reg[bit_ptr] <= RxD;
                        if (bit_ptr == 7) state <= 2; else bit_ptr <= bit_ptr + 1;
                    end else baud_cnt <= baud_cnt + 1;
                end
                2: begin // stop bit
                    if (baud_cnt == CLKS_PER_BIT-1) begin
                        state <= 0; baud_cnt <= 0; rx_done <= 1;
                    end else baud_cnt <= baud_cnt + 1;
                end
                default: state <= 0;
            endcase
        end
    end
endmodule
 
 
// =============================================================================
// TRANSMISOR UART (parametrizado por CLKS_PER_BIT)
// =============================================================================
module Transmitter_TxD #(
    parameter CLKS_PER_BIT = 104
)(
    input  wire clk, reset, tx_start,
    input  wire [7:0] tx_data,
    output reg  tx_busy,
    output reg  TxD
);
    reg [3:0] bit_counter;
    reg [$clog2(CLKS_PER_BIT+1)-1:0] baud_cnt;
    reg [9:0] shift_reg;
    reg       state;
 
    always @(posedge clk) begin
        if (reset) begin
            state <= 0; TxD <= 1; tx_busy <= 0; baud_cnt <= 0; bit_counter <= 0;
        end else begin
            case (state)
                0: begin
                    tx_busy <= 0; TxD <= 1;
                    if (tx_start) begin
                        state <= 1; tx_busy <= 1;
                        shift_reg <= {1'b1, tx_data, 1'b0}; // stop,data,start
                        baud_cnt <= 0; bit_counter <= 0;
                    end
                end
                1: begin
                    tx_busy <= 1;
                    if (baud_cnt >= CLKS_PER_BIT-1) begin
                        baud_cnt <= 0; TxD <= shift_reg[0];
                        shift_reg <= {1'b1, shift_reg[9:1]};
                        if (bit_counter == 9) state <= 0; else bit_counter <= bit_counter + 1;
                    end else baud_cnt <= baud_cnt + 1;
                end
            endcase
        end
    end
endmodule
 
 
// =============================================================================
// SPI MAESTRO simple: modo 0 (CPOL=0,CPHA=0), 8 bits, un solo CS.
// =============================================================================
module spi_master #(
    parameter CLK_DIV = 4
)(
    input  wire clk, rst,
    input  wire start,
    input  wire [7:0] tx_byte,
    output reg  [7:0] rx_byte,
    output reg  busy,
    output reg  sclk,
    output reg  mosi,
    input  wire miso,
    output reg  cs_n
);
    reg [2:0] bit_cnt;
    reg [7:0] shreg;
    reg [$clog2(CLK_DIV+1)-1:0] div_cnt;
 
    always @(posedge clk) begin
        if (rst) begin
            busy <= 0; sclk <= 0; cs_n <= 1; bit_cnt <= 0; div_cnt <= 0;
            mosi <= 0; rx_byte <= 0; shreg <= 0;
        end else if (start && !busy) begin
            busy   <= 1;
            cs_n   <= 0;
            shreg  <= tx_byte;
            mosi   <= tx_byte[7];
            bit_cnt<= 0;
            div_cnt<= 0;
            sclk   <= 0;
        end else if (busy) begin
            if (div_cnt == CLK_DIV-1) begin
                div_cnt <= 0;
                sclk <= ~sclk;
                if (sclk) begin
                    // flanco de bajada: se acaba de muestrear MISO en el flanco de subida anterior
                    if (bit_cnt == 7) begin
                        busy    <= 0;
                        cs_n    <= 1;
                        rx_byte <= {shreg[6:0], miso};
                    end else begin
                        shreg   <= {shreg[6:0], miso};
                        bit_cnt <= bit_cnt + 1;
                        mosi    <= shreg[6];
                    end
                end
            end else begin
                div_cnt <= div_cnt + 1;
            end
        end
    end
endmodule
 
 

// CORE RISC-V 
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
        instr_bus_in[6:0], instr_bus_in[14:12], instr_bus_in[30], instr_bus_in[31:20],
        Zero, lt, ltu, PCSrc, JALR_Src, MemWrite, ALUSrc, RegWrite,
        CSRWrite, is_ecall, is_mret, ResultSrc, ALUSrcA, ImmSrc, ALUControl
    );
 
    sign_extend u_sext (instr_bus_in, ImmSrc, imm32);
 
    wire valid_RegWrite = RegWrite && !trap_taken && en;
    regfile u_rf (clk, reset, valid_RegWrite, instr_bus_in[19:15], instr_bus_in[24:20], instr_bus_in[11:7], Result_mux_out, rd1, rd2);
 
    csr_unit u_csr (
        clk, reset, instr_bus_in[31:20], rd1, instr_bus_in[14:12],
        CSRWrite && en && !trap_taken, PC, is_ecall, is_mret,
        1'b0, 1'b0, csr_rdata, trap_pc, trap_taken
    );
 
    assign SrcA = (ALUSrcA == 2'b01) ? PC : (ALUSrcA == 2'b10) ? 32'b0 : rd1;
    assign SrcB = ALUSrc ? imm32 : rd2;
 
    ALU u_alu (SrcA, SrcB, ALUControl, ALUResult, Zero, lt, ltu);
 
    load_unit u_load (instr_bus_in[14:12], data_read_bus_in, ALUResult[1:0], LoadData);
 
    reg [3:0] wm;
    always @(*) begin
        if (!MemWrite || !en || trap_taken) wm = 4'b0000;
        else case (instr_bus_in[14:12])
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
   always @(posedge clk) if (reset) PC <= 32'h00000000; else if (en) PC <= PC_next;
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
 
module csr_unit(input clk, reset, input [11:0] csr_addr, input [31:0] wdata, input [2:0] funct3, input csr_we, input [31:0] pc_current, input is_ecall, is_mret, external_interrupt, pc_misaligned, output reg [31:0] rdata, output wire [31:0] trap_pc, output wire trap_taken);
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
