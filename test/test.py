PROGRAM_A = [
    0x00500093, 0x00A00113, 0x002081B3, 0x40110233, 0x00000293, 0x0032A023, 0x0002A303, 0x04000513,
    0x00652023, 0x00052603, 0x00167613, 0xFE061CE3, 0x04800593, 0x0AA00713, 0x00E5A023, 0x0005A783,
    0x1007F813, 0xFE081CE3, 0x0FF7F893, 0x01152023, 0x00000063, 0x00000013, 0x00000013, 0x00000013,
]
 
PROGRAM_B = [
    0x04000A13, 0x00100F13, 0x00300113, 0x0CC00093, 0x0AA00193, 0x0030F333, 0x08834393, 0x00038463,
    0x00000F13, 0x00500093, 0x00209333, 0x02834393, 0x00038463, 0x00000F13, 0xFFF00093, 0x4020D333,
    0xFFF34393, 0x00038463, 0x00000F13, 0x01EA2023, 0x000A2483, 0x0014F493, 0xFE049CE3, 0x00000063,
]
 
PROGRAM_D = [
    0x04000A13, 0x00100F13, 0x00500093, 0x00A00113, 0xFFF00193, 0x00900313, 0x0020C463, 0x00100313,
    0x00934393, 0x00038463, 0x00000F13, 0x00900313, 0x0030E463, 0x00100313, 0x00934393, 0x00038463,
    0x00000F13, 0x01EA2023, 0x000A2483, 0x0014F493, 0xFE049CE3, 0x00000063, 0x00000013, 0x00000013,
]
 
 
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer, RisingEdge
 
CLK_FREQ_HZ = 20_000_000     # frecuencia real del chip (ver info.yaml/config.json)
BAUD_RATE   = 115200
CLK_PERIOD_NS = round(1e9 / CLK_FREQ_HZ)
CLKS_PER_BIT  = CLK_FREQ_HZ // BAUD_RATE
BIT_NS        = CLKS_PER_BIT * CLK_PERIOD_NS
 
RX_BIT = 3   # ui_in[3]
TX_BIT = 4   # uo_out[4]
 
 
async def start_clock(dut):
    clock = Clock(dut.clk, CLK_PERIOD_NS, units="ns")
    cocotb.start_soon(clock.start())
 
 
async def reset_dut(dut):
    dut.ena.value = 1
    dut.ui_in.value = (1 << RX_BIT)
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
 
 
async def uart_send_byte(dut, byte):
    dut.ui_in.value = 0
    await Timer(BIT_NS, units="ns")
    for i in range(8):
        bit = (byte >> i) & 1
        dut.ui_in.value = (bit << RX_BIT)
        await Timer(BIT_NS, units="ns")
    dut.ui_in.value = (1 << RX_BIT)
    await Timer(BIT_NS, units="ns")
 
 
async def load_program(dut, words):
    """Carga las 24 palabras de instruccion (96 bytes), LSB primero por
    palabra -- protocolo actual del bootloader con INSTR_DEPTH=24."""
    assert len(words) == 24
    for w in words:
        for shift in (0, 8, 16, 24):
            await uart_send_byte(dut, (w >> shift) & 0xFF)
 
 
async def uart_recv_byte(dut, timeout_bits=20):
    for _ in range(timeout_bits * 20):
        if int(dut.uo_out.value) & (1 << TX_BIT) == 0:
            break
        await ClockCycles(dut.clk, 1)
    else:
        raise TimeoutError("No llego ningun byte por UART TX")
    await Timer(BIT_NS // 2, units="ns")
    value = 0
    for i in range(8):
        await Timer(BIT_NS, units="ns")
        bit = (int(dut.uo_out.value) >> TX_BIT) & 1
        value |= (bit << i)
    await Timer(BIT_NS, units="ns")
    return value
 
 
async def wait_for_run(dut, max_cycles=100000):
    for _ in range(max_cycles):
        if (int(dut.uo_out.value) >> 7) & 1:
            return
        await ClockCycles(dut.clk, 1)
    assert False, "El chip nunca paso a modo RUN tras cargar el programa"
 
 
@cocotb.test()
async def test_program_a_core_uart_spi(dut):
    """Programa A (24 instr): ALU basica, memoria, UART TX, y SPI en
    loopback emulado (uio_in[2] <- uio_out[1], igual que el jumper
    fisico JA1-JA3 que ya validamos en la Basys3)."""
    await start_clock(dut)
    await reset_dut(dut)
 
    async def spi_loopback():
        while True:
            await RisingEdge(dut.clk)
            mosi = (int(dut.uio_out.value) >> 1) & 1
            cur = int(dut.uio_in.value) & ~(1 << 2)
            dut.uio_in.value = cur | (mosi << 2)
    cocotb.start_soon(spi_loopback())
 
    await load_program(dut, PROGRAM_A)
    await wait_for_run(dut)
 
    b1 = await uart_recv_byte(dut)
    assert b1 == 0x0F, f"esperaba 0x0F (5+10), llego 0x{b1:02X}"
    b2 = await uart_recv_byte(dut)
    assert b2 == 0xAA, f"esperaba 0xAA (loopback SPI), llego 0x{b2:02X}"
 
 
@cocotb.test()
async def test_program_b_alu_rtype(dut):
    """Programa B (24 instr, bandera acumulada): and, sll, sra.
    Un solo byte de resultado: 0x01 = todo paso, 0x00 = alguna fallo."""
    await start_clock(dut)
    await reset_dut(dut)
    await load_program(dut, PROGRAM_B)
    await wait_for_run(dut)
 
    result = await uart_recv_byte(dut)
    assert result == 0x01, f"esperaba 0x01 (todo paso), llego 0x{result:02X}"
 
 
@cocotb.test()
async def test_program_d_branches_jumps(dut):
    """Programa D (24 instr, bandera acumulada): blt, bltu.
    Un solo byte de resultado: 0x01 = todo paso, 0x00 = alguna fallo."""
    await start_clock(dut)
    await reset_dut(dut)
    await load_program(dut, PROGRAM_D)
    await wait_for_run(dut)
 
    result = await uart_recv_byte(dut)
    assert result == 0x01, f"esperaba 0x01 (todo paso), llego 0x{result:02X}"
 
