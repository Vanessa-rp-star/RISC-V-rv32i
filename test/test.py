import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer, RisingEdge
 
CLK_FREQ_HZ = 10_000_000    
BAUD_RATE   = 115200
CLK_PERIOD_NS = round(1e9 / CLK_FREQ_HZ)
CLKS_PER_BIT  = CLK_FREQ_HZ // BAUD_RATE
BIT_NS        = CLKS_PER_BIT * CLK_PERIOD_NS
 
INSTR_DEPTH  = 8
BLOCK_WORDS  = INSTR_DEPTH
BLOCK_BYTES  = INSTR_DEPTH * 4      # 32
 
RX_BIT   = 3   # ui_in[3]          
TX_BIT   = 3   # uo_out[3]          
TXBUSY_BIT = 4 # uo_out[4]          
 
# uio_out: bit0=cs_n, bit1=mosi, bit3=sclk (salidas del maestro SPI)
# uio_in:  bit2=miso (entrada al chip, la maneja el esclavo emulado)
SPI_CS_BIT   = 0
SPI_MOSI_BIT = 1
SPI_SCLK_BIT = 3
SPI_MISO_BIT = 2
 

SPI_CLK_DIV = 4
SPI_BITS_PER_BLOCK = 24 + BLOCK_BYTES * 8
SPI_RELOAD_CYCLES = SPI_BITS_PER_BLOCK * 2 * SPI_CLK_DIV   # 2240 ciclos = 224us a 10MHz

UART_BYTE_TIMEOUT_CYCLES = SPI_RELOAD_CYCLES * 2 + 2000  # margen amplio
 

BLOQUES_TEST = [
    # bloque 0
    0x04000a13, 0x04c00a93, 0x00a00093, 0x00300113,
    0x00208333, 0x006a2023, 0x00100393, 0x007aa023,
    # bloque 1
    0x04000a13, 0x00a00093, 0x00300113, 0x40208333,
    0x006a2023, 0x04c00a93, 0x00200393, 0x007aa023,
    # bloque 2
    0x04000a13, 0x00c00093, 0x00a00113, 0x0020f333,
    0x006a2023, 0x04c00a93, 0x00300393, 0x007aa023,
    # bloque 3
    0x04000a13, 0x00100093, 0x00409313, 0x006a2023,
    0x04c00a93, 0x00400393, 0x007aa023, 0x00000013,
    # bloque 4
    0x04000a13, 0x00500093, 0x00500113, 0x0aa00313,
    0x00208463, 0x05500313, 0x006a2023, 0x00000063,
    # bloques 5-7: relleno NOP
    0x00000013, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013,
    0x00000013, 0x00000013, 0x00000013, 0x00000013,
]
EXPECTED_UART_SEQUENCE = [0x0D, 0x07, 0x08, 0x10, 0xAA]
 
 
def words_to_bytes(words):
    b = bytearray()
    for w in words:
        b += bytes([(w >> s) & 0xFF for s in (0, 8, 16, 24)])
    return bytes(b)
 
 
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
 
 
async def load_block0(dut, words):
    """Carga las 8 palabras de instruccion (32 bytes) del bloque 0, LSB
    primero por palabra -- protocolo del bootloader con INSTR_DEPTH=8.
    Los bloques 1..4 los trae el propio chip via SPI, no se envian aqui."""
    assert len(words) == BLOCK_WORDS
    for w in words:
        for shift in (0, 8, 16, 24):
            await uart_send_byte(dut, (w >> shift) & 0xFF)
 
 
async def uart_recv_byte(dut, max_cycles=UART_BYTE_TIMEOUT_CYCLES):
    """CORREGIDO: el timeout ahora se expresa en ciclos de clk directamente
    (no en 'bits' de UART) y por defecto cubre una recarga de bloque SPI
    completa (~224us) mas margen, no solo ~120us. Antes de este fix, el
    timeout expiraba a la mitad de una recarga de bloque real y el test
    fallaba aunque el chip siguiera funcionando correctamente."""
    for _ in range(max_cycles):
        if int(dut.uo_out.value) & (1 << TX_BIT) == 0:
            break
        await ClockCycles(dut.clk, 1)
    else:
        raise TimeoutError(
            f"No llego ningun byte por UART TX en {max_cycles} ciclos "
            f"({max_cycles*CLK_PERIOD_NS/1000:.1f} us)"
        )
    await Timer(BIT_NS // 2, units="ns")
    value = 0
    for i in range(8):
        await Timer(BIT_NS, units="ns")
        bit = (int(dut.uo_out.value) >> TX_BIT) & 1
        value |= (bit << i)
    await Timer(BIT_NS, units="ns")
    return value
 
 
async def wait_for_mode(dut, mode, max_cycles=200000):
    for _ in range(max_cycles):
        if ((int(dut.uo_out.value) >> 6) & 0b11) == mode:
            return
        await ClockCycles(dut.clk, 1)
    assert False, f"El chip nunca alcanzo mode={mode:02b}"
 
 
async def wait_for_run(dut, max_cycles=200000):
    await wait_for_mode(dut, 0b01, max_cycles)
 
 
def spi_ram_slave(dut, content_bytes):
    """Modelo de comportamiento (equivalente a spi_ram_slave_testfixture.v
    y, mas adelante, a spi-ram-emu en el RP2040 real): responde al
    protocolo READ(0x03)+direccion de 16 bits (MSB primero) que ya emite
    spi_burst_master, sirviendo bytes de 'content_bytes'."""
 
    async def _run():
        mem = bytearray(content_bytes)
        total_bits = 0
        header_shift = 0
        header_done = False
        read_ptr = 0
        out_byte = 0
        data_bit_cnt = 0
        prev_sclk = 0
 
        while True:
            await RisingEdge(dut.clk)
            uio_out = int(dut.uio_out.value)
            sclk = (uio_out >> SPI_SCLK_BIT) & 1
            mosi = (uio_out >> SPI_MOSI_BIT) & 1
            cs_n = (uio_out >> SPI_CS_BIT) & 1
 
            if cs_n:
                total_bits = 0
                header_done = False
                data_bit_cnt = 0
            else:
                if sclk == 1 and prev_sclk == 0:
                    if not header_done:
                        header_shift = ((header_shift << 1) | mosi) & 0xFFFFFF
                        total_bits += 1
                        if total_bits == 24:
                            read_ptr = header_shift & 0xFFFF
                            header_done = True
                            data_bit_cnt = 0
                    else:
                        if data_bit_cnt == 7:
                            data_bit_cnt = 0
                            read_ptr = (read_ptr + 1) & 0xFFFF
                        else:
                            data_bit_cnt += 1
                elif sclk == 0 and prev_sclk == 1:
                    if header_done:
                        out_byte = mem[read_ptr % len(mem)]
 
            prev_sclk = sclk
            miso_bit = (out_byte >> (7 - data_bit_cnt)) & 1
            cur = int(dut.uio_in.value) & ~(1 << SPI_MISO_BIT)
            dut.uio_in.value = cur | (miso_bit << SPI_MISO_BIT)
 
    return cocotb.start_soon(_run())
 
 
@cocotb.test()
async def test_instruction_set_multiblock(dut):
    """Valida ADD, SUB, AND, SLLI y BEQ encadenando 5 bloques (40
    instrucciones) por SPI sobre un procesador cuya instruction_mem solo
    tiene 8 palabras -- prueba formal de que el mecanismo de bloques
    extiende la capacidad logica de programa mas alla de la memoria
    fisica, sin romper el ciclo unico."""
    await start_clock(dut)
    await reset_dut(dut)
 
    # CORREGIDO: cocotb corre TODAS las funciones @cocotb.test() de este
    # archivo dentro de la MISMA simulacion continua (no reinicia el
    # simulador entre pruebas). Una tarea de fondo lanzada con
    # cocotb.start_soon() sigue viva despues de que su test termina, y
    # seguia compitiendo por uio_in con la tarea del siguiente test --
    # por eso test_boot_and_first_block_only recibia el resultado de
    # SUB (bloque 1) en vez de ADD (bloque 0). Ahora se mata la tarea al
    # salir de este test, pase lo que pase (try/finally).
    spi_task = spi_ram_slave(dut, words_to_bytes(BLOQUES_TEST))
    try:
        await load_block0(dut, BLOQUES_TEST[0:BLOCK_WORDS])
        await wait_for_run(dut)
 
        recibidos = []
        for _ in EXPECTED_UART_SEQUENCE:
            recibidos.append(await uart_recv_byte(dut))
 
        assert recibidos == EXPECTED_UART_SEQUENCE, (
            f"secuencia esperada {[hex(b) for b in EXPECTED_UART_SEQUENCE]}, "
            f"llego {[hex(b) for b in recibidos]}"
        )
    finally:
        spi_task.kill()
 
 
@cocotb.test()
async def test_boot_and_first_block_only(dut):
    """Sanity check minimo: solo el bootloader UART + bloque 0 (ADD),
    sin depender de que el esclavo SPI conteste (bloque 0 SI dispara una
    recarga, asi que igual se necesita el esclavo, pero aqui solo se
    verifica el primer byte por UART para aislar problemas de bootload
    puro de problemas de SPI)."""
    await start_clock(dut)
    await reset_dut(dut)
 
    spi_task = spi_ram_slave(dut, words_to_bytes(BLOQUES_TEST))
    try:
        await load_block0(dut, BLOQUES_TEST[0:BLOCK_WORDS])
        await wait_for_run(dut)
 
        b0 = await uart_recv_byte(dut)
        assert b0 == 0x0D, f"esperaba 0x0D (10+3 via ADD), llego 0x{b0:02X}"
    finally:
        spi_task.kill()
 
