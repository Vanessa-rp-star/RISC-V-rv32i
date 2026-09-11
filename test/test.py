PROGRAM_A = [
    0x00500093, 0x00A00113, 0x002081B3, 0x40110233, 0x00000293, 0x0032A023, 0x0002A303, 0x04000513,
    0x00652023, 0x00052603, 0x00167613, 0xFE061CE3, 0x04800593, 0x0AA00713, 0x00E5A023, 0x0005A783,
    0x1007F813, 0xFE081CE3, 0x0FF7F893, 0x01152023, 0x00000063, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013,
]
 
PROGRAM_B = [
    0x0CC00093, 0x0AA00113, 0x00400193, 0x01C00213, 0xFFF00293, 0x04000A13, 0x0020F333, 0x006A2023,
    0x000A2A83, 0x001AFA93, 0xFE0A9CE3, 0x0020E333, 0x006A2023, 0x000A2A83, 0x001AFA93, 0xFE0A9CE3,
    0x0020C333, 0x006A2023, 0x000A2A83, 0x001AFA93, 0xFE0A9CE3, 0x00113333, 0x006A2023, 0x000A2A83,
    0x001AFA93, 0xFE0A9CE3, 0x0020A333, 0x006A2023, 0x000A2A83, 0x001AFA93, 0xFE0A9CE3, 0x00311333,
    0x006A2023, 0x000A2A83, 0x001AFA93, 0xFE0A9CE3, 0x00315333, 0x006A2023, 0x000A2A83, 0x001AFA93,
    0xFE0A9CE3, 0x4042D333, 0x006A2023, 0x000A2A83, 0x001AFA93, 0xFE0A9CE3, 0x0042D333, 0x006A2023,
    0x000A2A83, 0x001AFA93, 0xFE0A9CE3, 0x00000063, 0x00000013, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013,
]
 
PROGRAM_D = [
    0x04000A13, 0x00500093, 0x00A00113, 0xFFF00193, 0x0020C463, 0x00000313, 0x0AA00313, 0x006A2023,
    0x000A2A83, 0x001AFA93, 0xFE0A9CE3, 0x00115463, 0x00000313, 0x0BB00313, 0x006A2023, 0x000A2A83,
    0x001AFA93, 0xFE0A9CE3, 0x0030E463, 0x00000313, 0x0CC00313, 0x006A2023, 0x000A2A83, 0x001AFA93,
    0xFE0A9CE3, 0x0011F463, 0x00000313, 0x0DD00313, 0x006A2023, 0x000A2A83, 0x001AFA93, 0xFE0A9CE3,
    0x000AB3B7, 0x007A2023, 0x000A2A83, 0x001AFA93, 0xFE0A9CE3, 0x0080046F, 0x00000313, 0x0EE00313,
    0x006A2023, 0x000A2A83, 0x001AFA93, 0xFE0A9CE3, 0x0FA00513, 0x00AA2023, 0x000A2A83, 0x001AFA93,
    0xFE0A9CE3, 0x00000063, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013, 0x00000013,
]
 
 
# =============================================================================
# test.py -- Testbench cocotb para tt_um_vanessa_riscv
#
# Reproduce en simulacion el mismo protocolo UART que ya validamos a mano en
# la Basys3 (Programas A, B y D del proceso de validacion en FPGA), byte por
# byte, bit por bit -- no se inspeccionan senales internas, todo pasa por
# ui_in[3] (RX) y uo_out[4] (TX), exactamente como lo hara el chip real.
#
# NOTA DE VELOCIDAD: para simular mas rapido, este testbench sobreescribe
# CLK_FREQ_HZ a 2 MHz (en vez de los 20 MHz reales del chip) via el Makefile
# (ver -P en COMPILE_ARGS). Esto NO cambia el comportamiento funcional -- el
# modulo recalcula CLKS_PER_BIT automaticamente a partir del parametro, asi
# que el protocolo sigue siendo correcto, solo mas rapido de simular. El
# reloj real del chip (20 MHz, ver info.yaml/config.json) se usa en gate-level
# sim y en el chip fabricado, nunca aqui.
# =============================================================================
 
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer, RisingEdge, FallingEdge
 
CLK_FREQ_HZ = 2_000_000      # debe coincidir con el override del Makefile
BAUD_RATE   = 115200
# CRITICO: usar division ENTERA, exactamente como lo hace el modulo Verilog
# (localparam CLKS_PER_BIT = CLK_FREQ_HZ / BAUD_RATE;). Si aqui se usara la
# formula "ideal" 1e9/BAUD_RATE, el testbench se desincroniza del receptor
# real en unos pocos nanosegundos por bit -- poco por byte, pero se acumula
# sin control a lo largo de los 256 bytes del bootloader.
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
    dut.ui_in.value = (1 << RX_BIT)   # RX en reposo = 1 (idle alto)
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 2)
 
 
async def uart_send_byte(dut, byte):
    """Manda un byte 8N1 bit a bit por ui_in[3], igual que RealTerm."""
    # start bit (0)
    dut.ui_in.value = 0
    await Timer(BIT_NS, units="ns")
    for i in range(8):
        bit = (byte >> i) & 1
        dut.ui_in.value = (bit << RX_BIT)
        await Timer(BIT_NS, units="ns")
    # stop bit (1) = reposo
    dut.ui_in.value = (1 << RX_BIT)
    await Timer(BIT_NS, units="ns")
 
 
async def load_program(dut, words):
    """Carga las 64 palabras de instruccion, LSB primero por palabra --
    identico al protocolo que uart_bootloader espera y que ya validamos
    manualmente enviando los .bin por RealTerm."""
    assert len(words) == 64
    for w in words:
        for shift in (0, 8, 16, 24):
            await uart_send_byte(dut, (w >> shift) & 0xFF)
 
 
async def uart_recv_byte(dut, timeout_bits=20):
    """Escucha uo_out[4] (TX) y decodifica un byte 8N1, tal como lo hace
    RealTerm del otro lado del cable."""
    # Espera el flanco de bajada del start bit
    for _ in range(timeout_bits * 20):
        if int(dut.uo_out.value) & (1 << TX_BIT) == 0:
            break
        await ClockCycles(dut.clk, 1)
    else:
        raise TimeoutError("No llego ningun byte por UART TX")
 
    await Timer(BIT_NS // 2, units="ns")  # centrar en el start bit
    value = 0
    for i in range(8):
        await Timer(BIT_NS, units="ns")
        bit = (int(dut.uo_out.value) >> TX_BIT) & 1
        value |= (bit << i)
    await Timer(BIT_NS, units="ns")  # stop bit
    return value
 
 
@cocotb.test()
async def test_program_a_core_uart_spi(dut):
    """Programa A: ALU basica, memoria de datos, UART TX/mapeo MMIO, y SPI
    en loopback (emulado conectando uio_in[2]=MISO al ultimo valor de
    uio_out[1]=MOSI, igual que el jumper fisico JA1-JA3 en la Basys3)."""
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
 
    for _ in range(50000):
        if (int(dut.uo_out.value) >> 7) & 1:
            break
        await ClockCycles(dut.clk, 1)
    else:
        assert False, "El chip nunca paso a modo RUN tras cargar el programa"
 
    b1 = await uart_recv_byte(dut)
    assert b1 == 0x0F, f"esperaba 0x0F (5+10), llego 0x{b1:02X}"
 
    b2 = await uart_recv_byte(dut)
    assert b2 == 0xAA, f"esperaba 0xAA (loopback SPI), llego 0x{b2:02X}"
 
 
@cocotb.test()
async def test_program_b_alu_rtype(dut):
    """Programa B: cobertura completa de ALU R-type (and,or,xor,sltu,slt,
    sll,srl,sra), incluyendo la distincion critica sra vs srl."""
    await start_clock(dut)
    await reset_dut(dut)
    await load_program(dut, PROGRAM_B)
 
    for _ in range(50000):
        if (int(dut.uo_out.value) >> 7) & 1:
            break
        await ClockCycles(dut.clk, 1)
    else:
        assert False, "Nunca paso a modo RUN"
 
    esperado = [0x88, 0xEE, 0x66, 0x01, 0x00, 0xA0, 0x0A, 0xFF, 0x0F]
    for i, exp in enumerate(esperado):
        got = await uart_recv_byte(dut)
        assert got == exp, f"byte {i}: esperaba 0x{exp:02X}, llego 0x{got:02X}"
 
 
@cocotb.test()
async def test_program_d_branches_jumps(dut):
    """Programa D: blt,bge,bltu,bgeu,lui,jal -- la prueba de fuego del
    bug de desfase PC/instruccion que se corrigio en el datapath."""
    await start_clock(dut)
    await reset_dut(dut)
    await load_program(dut, PROGRAM_D)
 
    for _ in range(50000):
        if (int(dut.uo_out.value) >> 7) & 1:
            break
        await ClockCycles(dut.clk, 1)
    else:
        assert False, "Nunca paso a modo RUN"
 
    esperado = [0xAA, 0xBB, 0xCC, 0xDD, 0x00, 0xEE, 0xFA]
    for i, exp in enumerate(esperado):
        got = await uart_recv_byte(dut)
        assert got == exp, f"byte {i}: esperaba 0x{exp:02X}, llego 0x{got:02X}"
 
