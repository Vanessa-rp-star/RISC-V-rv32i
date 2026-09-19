`default_nettype none
`timescale 1ns / 1ps

module tb ();
 
  // Vuelca las señales a un VCD para poder verlas con gtkwave/surfer.
  initial begin
    $dumpfile("tb.vcd");
    $dumpvars(0, tb);
    #1;
  end
 
  // Señales de entrada/salida, expuestas directamente como ui_in, uo_out,
  // etc. -- test.py las accede como dut.ui_in, dut.uo_out, ...
  reg clk;
  reg rst_n;
  reg ena;
  reg [7:0] ui_in;
  reg [7:0] uio_in;
  wire [7:0] uo_out;
  wire [7:0] uio_out;
  wire [7:0] uio_oe;
 
`ifdef GL_TEST
  wire VPWR = 1'b1;
  wire VGND = 1'b0;
`endif
 
  tt_um_vanessa_riscv user_project (
 
`ifdef GL_TEST
      .VPWR(VPWR),
      .VGND(VGND),
`endif
 
      .ui_in  (ui_in),    // Entradas dedicadas
      .uo_out (uo_out),   // Salidas dedicadas
      .uio_in (uio_in),   // IOs: entrada
      .uio_out(uio_out),  // IOs: salida
      .uio_oe (uio_oe),   // IOs: direccion (1=salida, 0=entrada)
      .ena    (ena),      // habilitador del proyecto
      .clk    (clk),      // reloj
      .rst_n  (rst_n)     // reset activo en bajo
  );
 
endmodule
 
