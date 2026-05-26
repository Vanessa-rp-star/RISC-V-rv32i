# 4-bit ALU

## Description
This project implements a simple 4-bit Arithmetic Logic Unit (ALU) capable of performing arithmetic and logical operations between two 4-bit operands.

## How it works
The ALU receives two 4-bit inputs:
- A = ui_in[3:0]
- B = ui_in[7:4]

The operation is selected using:
- op = uio_in[2:0]

Supported operations:
- 000 → Addition (A + B)
- 001 → Subtraction (A - B)
- 010 → Bitwise AND
- 011 → Bitwise OR
- 100 → Bitwise XOR
- 101 → Less-than comparison (A < B)

The result is displayed on:
- uo_out[7:0]

## How to test
1. Set operand A using `ui_in[3:0]`
2. Set operand B using `ui_in[7:4]`
3. Select the operation using `uio_in[2:0]`
4. Observe the output on `uo_out[7:0]`

Example:
- A = 5
- B = 3
- op = 000

Expected result:
- uo_out = 8
