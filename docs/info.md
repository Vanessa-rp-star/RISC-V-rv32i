
## How it works

This project is a **single-cycle RISC-V RV32I processor** that is programmed over UART. It has no program stored in silicon. After reset the chip is in LOAD mode and waits for a first program block of 32 bytes (8 instructions) on the UART. When the block is complete the chip switches to RUN mode and executes it at one instruction per clock cycle, with no pipeline. When the program needs more instructions, it asks an external SPI memory for the next block and keeps running, with the register file intact.

It implements the RV32I base instruction set: register-register and register-immediate arithmetic and logic, shifts, signed and unsigned comparisons, jumps and branches, byte / halfword / word loads and stores, `lui` and `auipc`.

### Block-chained program memory

The physical instruction memory holds only 8 words of 32 bits (one 32-byte block) and the data memory holds 4 words. A longer program is split into 32-byte blocks stored in an external SPI memory: block `n` lives at address `n*32`. Block 0 is sent over UART; the program itself requests every other block.

The chip has three modes, shown on `uo_out[7:6]`:

| `uo_out[7:6]` | Mode | What happens |
| --- | --- | --- |
| `00` | LOAD | Waits for the 32 bytes of block 0 on the UART |
| `01` | RUN | Executes the current block, one instruction per cycle |
| `10` | BLOCKLOAD | Reads 32 bytes from the SPI memory, then returns to RUN with the PC at 0 |

The modes are mutually exclusive: the UART bootloader, instruction execution and the SPI block read never happen at the same time.

### Peripheral memory map

| Address | Read | Write |
| --- | --- | --- |
| `0x40` | Bit 0 = `tx_busy` | Sends the low byte over UART TX |
| `0x44` | Bit 8 = received-data flag, bits 7:0 = data | Acknowledges the received byte |
| `0x4C` | -- | Requests the block whose number is written; starts the SPI read |
| `0x50` | Inputs `ui_in[7:0]` | -- |

### Validated specifications

| Metric | Value |
| --- | --- |
| RV32I instructions verified | 30/30 (base set) |
| Verification methods | Cycle-accurate Python model, cocotb, gate-level test and Basys3 FPGA |
| Mutual-exclusion invariant | 0 violations in 136,353 simulated cycles |
| Category programs validated on FPGA | 10/10 (A, B, C, D, D2, E, F2, G, H_suma, H_resta) |
| Clock | 10 MHz |
| UART | 115200 baud, 8N1 |
| Physical instruction memory | 8 words, chained in blocks over SPI |
| Size | 4x2 tiles |

Silicon validation is pending. Everything above was verified in simulation, at gate level and on FPGA.

## How to test

### Requirements

| Requirement | Detail |
| --- | --- |
| Board | Tiny Tapeout demo board with the project enabled |
| Clock | 10 MHz |
| Reset | `rst_n` low at start |
| USB | USB-C cable from the demo board to the computer |
| Serial terminal | RealTerm or similar, 115200 baud, 8 data bits, no parity, 1 stop bit |
| Chip UART | RX on `ui_in[3]`, TX on `uo_out[4]` |
| SPI memory | `0x03` read with a 16-bit address (mode 0 or 3) on `uio[0:3]`, holding the full program image from address 0 |
| Files | `bloque0_<program>.bin` (32 bytes, sent over UART) and `spi_image_<program>.bin` (loaded into the SPI memory) |

### Steps

1. Connect the USB-C cable. The demo board bridges the chip UART to a serial port through its RP2350, as described in the Tiny Tapeout pinout page (UART to USB).
2. Enable the project, set the clock to 10 MHz and reset. `uo_out[7:6]` should read `00` (LOAD).
3. Load the full program image into the SPI memory: block 0 at address 0 and block `n` at `n*32`.
4. Open the serial terminal on the port that reaches the chip UART.
5. Send the file `bloque0_<program>.bin` (32 bytes) unmodified. Each word is sent least significant byte first, and the file is already in that order.
6. After the last byte the chip enters RUN (`uo_out[7:6]` = `01`) and executes block 0.
7. When the program requests a block, the chip enters BLOCKLOAD (`10`) during the SPI read and returns to RUN (`01`).
8. Read the bytes the program sends over UART in the terminal.

To repeat a test, reset the chip and send block 0 again.

### What to expect

| Observation | Where | Expected value |
| --- | --- | --- |
| After reset | `uo_out[7:6]` | `00` (LOAD) |
| While block 0 is received | `uo_out[5]` (`loading_any`) | 1 while the 32 bytes arrive |
| After the last byte | `uo_out[7:6]` | `01` (RUN) |
| Execution | `uo_out[2:0]` | Low bits of the PC changing (debug) |
| UART transmission | `uo_out[3]` (`tx_busy`) | 1 while each byte is sent |
| Each block read | `uo_out[7:6]` and `uio[0]` (CS_n) | `10`, with CS_n low during the read |
| Test program output | Serial terminal | `0x0D`, `0x07`, `0x08`, `0x10`, `0xAA`, in that order |

The test program (`bloque0_test.bin` with its 8-block image) computes 10+3, 10-3, 12 AND 10 and 1 shifted left by 4, then ends with `0xAA` in an infinite loop. The first four blocks each request the next one before finishing. At 10 MHz each UART byte lasts about 86 microseconds and each block read takes on the order of 0.2 milliseconds (estimate).

After `0xAA` the processor stays in an infinite loop. That is the expected behavior, not a failure.

### Notes

- The byte `0x03` appears in the programs. If your terminal or serial bridge treats it as Ctrl-C, disable that behavior or bytes will be lost.
- If the SPI memory is not loaded, the chip executes whatever it reads and the output after block 0 is not valid.

## External hardware

- A serial path between the computer and the chip UART (`ui_in[3]` RX, `uo_out[4]` TX). The demo board provides it over USB-C. As an alternative, a 3.3 V USB-Serial adapter works: adapter TX to `ui_in[3]`, adapter RX to `uo_out[4]` and a common ground.
- An external SPI memory on `uio[0:3]` in standard Pmod order (CS_n, MOSI, MISO, SCK), supporting the `0x03` read with a 16-bit address. On the demo board it can be emulated by the board's microcontroller. SCK is the clock divided by 8 (1.25 MHz at 10 MHz).
- An oscilloscope or logic analyzer is optional, to watch `uo_out[7:6]` and the SPI lines.
