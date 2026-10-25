import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, Timer, RisingEdge
from cocotb.utils import get_sim_time
 
CLK_FREQ_HZ = 10_000_000     # frecuencia real del chip (ver info.yaml/config.json)
BAUD_RATE   = 115200
CLK_PERIOD_NS = round(1e9 / CLK_FREQ_HZ)
CLKS_PER_BIT  = CLK_FREQ_HZ // BAUD_RATE   # 86: igual que el RTL (divisor truncado, baud real 116279)
LOW_LINE_CYCLES = 30_000     # linea RX en bajo antes de cargar (el receptor original llenaba la imem con ceros en ~26 500 ciclos)
BIT_NS        = CLKS_PER_BIT * CLK_PERIOD_NS
 
INSTR_DEPTH  = 8
BLOCK_WORDS  = INSTR_DEPTH
BLOCK_BYTES  = INSTR_DEPTH * 4      # 32
 
RX_BIT   = 3   # ui_in[3]           -- sin cambios respecto al diseño de 24
TX_BIT   = 4   # uo_out[4]          -- ACTUALIZADO: alineado a la Opcion 1 de
                                     # TT para UART-to-USB (ui_in[3]=RX,
                                     # uo_out[4]=TX). Antes estaba en uo_out[3].
TXBUSY_BIT = 3 # uo_out[3]          -- tx_busy (status), antes en uo_out[4]
 
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
    clock = Clock(dut.clk, CLK_PERIOD_NS, unit="ns")
    cocotb.start_soon(clock.start())
 
 
async def reset_dut(dut):
    dut.ena.value = 1
    dut.ui_in.value = (1 << RX_BIT)
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    # El RTL NO tiene sincronizador de reset (rst_n se usa directo); se
    # esperan 5 ciclos antes de empezar a hablar por UART.
    await ClockCycles(dut.clk, 5)
 
 
async def uart_send_byte(dut, byte, cpb=None, bad_stop=False):
    """CORREGIDO: usa ClockCycles(CLKS_PER_BIT) en vez de Timer(BIT_NS).
    Numericamente son la misma duracion (CLKS_PER_BIT*CLK_PERIOD_NS==BIT_NS
    de forma exacta), pero Timer() espera un tiempo ABSOLUTO de simulacion
    mientras que la logica RTL del receptor cuenta CICLOS DE RELOJ
    (baud_cnt). Un modelo Python ciclo-exacto del diseño completo (CPU +
    FSM + spi_burst_master + bootloader) confirmo que el protocolo es
    correcto y que la secuencia esperada SI se recibe cuando todo se
    sincroniza estrictamente por ciclos -- por eso se elimina cualquier
    espera basada en Timer() en las rutinas de UART."""
    cpb = cpb or CLKS_PER_BIT
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, cpb)
    for i in range(8):
        bit = (byte >> i) & 1
        dut.ui_in.value = (bit << RX_BIT)
        await ClockCycles(dut.clk, cpb)
    # bit de parada: normalmente 1; con bad_stop=True se manda 0 (trama rota)
    dut.ui_in.value = 0 if bad_stop else (1 << RX_BIT)
    await ClockCycles(dut.clk, cpb)
    dut.ui_in.value = (1 << RX_BIT)
 
 
async def load_block0(dut, words, cpb=None):
    """Carga las 8 palabras de instruccion (32 bytes) del bloque 0, LSB
    primero por palabra -- protocolo del bootloader con INSTR_DEPTH=8.
    Los bloques 1..4 los trae el propio chip via SPI, no se envian aqui."""
    assert len(words) == BLOCK_WORDS
    for w in words:
        for shift in (0, 8, 16, 24):
            await uart_send_byte(dut, (w >> shift) & 0xFF, cpb)
 
 
def start_uart_monitor(dut):
    """CAUSA RAIZ REAL (confirmada con el log de GitHub Actions): bloque0
    ejecuta sus 8 instrucciones en solo 8 ciclos (800ns, ciclo unico) y
    dispara la recarga del bloque1 CASI DE INMEDIATO. Mientras tanto,
    Python sigue ocupado terminando las esperas de margen de
    uart_send_byte() del propio bootloader (~4000ns mas) y solo DESPUES
    llama wait_for_run() -- que para cuando empieza a preguntar, el chip
    YA paso por RUN una vez y esta en BLOCKLOAD cargando el bloque 1.
    El byte de ADD (0x0D) se transmite y se pierde sin que nadie lo este
    observando: por eso ambos tests reciben la secuencia CORRIDA UNA
    POSICION (0x07,0x08,0x10,0xAA en vez de 0x0D,0x07,0x08,0x10,0xAA).
    Ni el RTL ni el protocolo estan mal (un modelo Python ciclo-exacto del
    diseño completo confirma la secuencia correcta) -- el bug era que el
    testbench empezaba a "escuchar" demasiado tarde.
 
    FIX: un monitor de fondo que arranca ANTES de mandar el bootload y
    detecta cada flanco de bajada real de TX (1->0), sin importar que la
    corrutina principal siga ocupada haciendo otra cosa. Cada byte
    decodificado se agrega, en orden, a la lista que esta funcion regresa."""
    received = []
 
    async def _run():
        prev_txd = (int(dut.uo_out.value) >> TX_BIT) & 1
        while True:
            await ClockCycles(dut.clk, 1)
            txd = (int(dut.uo_out.value) >> TX_BIT) & 1
            if txd == 0 and prev_txd == 1:
                # flanco de bajada real = inicio de una trama UART nueva.
                await ClockCycles(dut.clk, CLKS_PER_BIT // 2)
                value = 0
                for i in range(8):
                    await ClockCycles(dut.clk, CLKS_PER_BIT)
                    bit = (int(dut.uo_out.value) >> TX_BIT) & 1
                    value |= (bit << i)
                await ClockCycles(dut.clk, CLKS_PER_BIT)
                received.append(value)
                dut._log.info(
                    f"[DEBUG] monitor UART: byte #{len(received)} = 0x{value:02X} "
                    f"en t={get_sim_time(unit='ns')}ns"
                )
                prev_txd = (int(dut.uo_out.value) >> TX_BIT) & 1
            else:
                prev_txd = txd
 
    task = cocotb.start_soon(_run())
    return received, task
 
 
async def wait_for_n_bytes(dut, received, n, max_cycles=UART_BYTE_TIMEOUT_CYCLES * 6):
    for _ in range(max_cycles):
        if len(received) >= n:
            return
        await ClockCycles(dut.clk, 1)
    raise TimeoutError(
        f"Solo llegaron {len(received)} de {n} bytes esperados: "
        f"{[hex(b) for b in received]}"
    )
 
 
async def monitor_mode(dut):
    """Tarea de diagnostico: imprime cada cambio de 'mode' (uo_out[7:6]) con
    marca de tiempo de simulacion, para poder comparar linea por linea
    contra el modelo Python ciclo-exacto y encontrar exactamente donde
    diverge el comportamiento real de icarus."""
    prev = None
    while True:
        await ClockCycles(dut.clk, 1)
        mode = (int(dut.uo_out.value) >> 6) & 0b11
        if mode != prev:
            dut._log.info(f"[DEBUG] t={get_sim_time(unit='ns')}ns mode {prev} -> {mode} (PC~uo_out[2:0]={int(dut.uo_out.value)&7})")
            prev = mode
 
 
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
    mode_task = cocotb.start_soon(monitor_mode(dut))
    # El monitor de UART arranca ANTES de mandar el bootload -- asi no
    # importa que bloque0 termine de ejecutarse mientras Python sigue
    # ocupado en el bit-banging del propio envio.
    received, uart_task = start_uart_monitor(dut)
    dut._log.info(f"[DEBUG] === INICIO test_instruction_set_multiblock, t={get_sim_time(unit='ns')}ns ===")
    try:
        await load_block0(dut, BLOQUES_TEST[0:BLOCK_WORDS])
        dut._log.info(f"[DEBUG] bloque0 enviado por UART, t={get_sim_time(unit='ns')}ns")
 
        await wait_for_n_bytes(dut, received, len(EXPECTED_UART_SEQUENCE))
        recibidos = received[:len(EXPECTED_UART_SEQUENCE)]
 
        assert recibidos == EXPECTED_UART_SEQUENCE, (
            f"secuencia esperada {[hex(b) for b in EXPECTED_UART_SEQUENCE]}, "
            f"llego {[hex(b) for b in recibidos]}"
        )
    finally:
        spi_task.cancel()
        mode_task.cancel()
        uart_task.cancel()
 
 
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
    mode_task = cocotb.start_soon(monitor_mode(dut))
    received, uart_task = start_uart_monitor(dut)
    dut._log.info(f"[DEBUG] === INICIO test_boot_and_first_block_only, t={get_sim_time(unit='ns')}ns ===")
    try:
        await load_block0(dut, BLOQUES_TEST[0:BLOCK_WORDS])
        dut._log.info(f"[DEBUG] bloque0 enviado por UART, t={get_sim_time(unit='ns')}ns")
 
        await wait_for_n_bytes(dut, received, 1)
        b0 = received[0]
        assert b0 == 0x0D, f"esperaba 0x0D (10+3 via ADD), llego 0x{b0:02X}"
    finally:
        spi_task.cancel()
        mode_task.cancel()
        uart_task.cancel()
 
 
# =============================================================================
# PRUEBAS NUEVAS (validan receptor con sincronizador + stop, divisor 86 y
# reset sin sincronizador). Con el RTL original T3 y T5 deben FALLAR.
# =============================================================================
def _mode(dut):
    return (int(dut.uo_out.value) >> 6) & 0b11
 
 
async def _arrancar_y_comprobar(dut, cpb=None, antes=None):
    """Lanza esclavo SPI y monitor UART, carga el bloque 0 y comprueba la
    secuencia completa. 'antes' es una corrutina opcional que se ejecuta
    justo antes de cargar (ruido, trama rota, etc.)."""
    spi_task = spi_ram_slave(dut, words_to_bytes(BLOQUES_TEST))
    received, uart_task = start_uart_monitor(dut)
    try:
        if antes is not None:
            await antes()
        await load_block0(dut, BLOQUES_TEST[0:BLOCK_WORDS], cpb)
        await wait_for_n_bytes(dut, received, len(EXPECTED_UART_SEQUENCE))
        recibidos = received[:len(EXPECTED_UART_SEQUENCE)]
        assert recibidos == EXPECTED_UART_SEQUENCE, (
            f"secuencia esperada {[hex(b) for b in EXPECTED_UART_SEQUENCE]}, "
            f"llego {[hex(b) for b in recibidos]}"
        )
    finally:
        spi_task.cancel()
        uart_task.cancel()
 
 
@cocotb.test()
async def test_rx_linea_baja_antes_de_cargar(dut):
    """T3: RX en BAJO al liberar el reset durante LOW_LINE_CYCLES ciclos.
    El chip debe seguir en LOAD (sin bytes fantasma) y, al subir la linea,
    cargar y ejecutar el programa normalmente."""
    await start_clock(dut)
    dut.ena.value = 1
    dut.uio_in.value = 0
    dut.ui_in.value = 0                 # RX en bajo: el peor caso
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
 
    async def linea_baja_y_subir():
        await ClockCycles(dut.clk, LOW_LINE_CYCLES)
        assert _mode(dut) == 0b00, f"con RX en bajo el chip salio de LOAD (mode={_mode(dut):02b})"
        dut.ui_in.value = (1 << RX_BIT)
        await ClockCycles(dut.clk, 4 * CLKS_PER_BIT)
 
    await _arrancar_y_comprobar(dut, antes=linea_baja_y_subir)
 
 
@cocotb.test()
async def test_rx_tolerancia_baudios(dut):
    """T4: el PC manda con +-3 % de error de baudios."""
    await start_clock(dut)
    for err in (-0.03, 0.03):
        await reset_dut(dut)
        cpb = round(CLKS_PER_BIT * (1 + err))
        dut._log.info(f"[T4] bit del PC = {cpb} ciclos (RTL usa {CLKS_PER_BIT})")
        await _arrancar_y_comprobar(dut, cpb=cpb)
 
 
@cocotb.test()
async def test_rx_stop_invalido_se_descarta(dut):
    """T5: una trama con bit de parada en 0 NO debe contar como byte del
    bootloader (si contara, todo el bloque quedaria desplazado un byte)."""
    await start_clock(dut)
    await reset_dut(dut)
 
    async def trama_rota():
        await uart_send_byte(dut, 0x55, bad_stop=True)
        await ClockCycles(dut.clk, 4 * CLKS_PER_BIT)
 
    await _arrancar_y_comprobar(dut, antes=trama_rota)
 
 
@cocotb.test()
async def test_reset_en_run_y_recarga(dut):
    """T6: reset a mitad de la vida del chip (modo RUN). Debe volver a LOAD,
    dejar el SPI en reposo y poder cargar y ejecutar otra vez."""
    await start_clock(dut)
    await reset_dut(dut)
    spi_task = spi_ram_slave(dut, words_to_bytes(BLOQUES_TEST))
    received, uart_task = start_uart_monitor(dut)
    try:
        await load_block0(dut, BLOQUES_TEST[0:BLOCK_WORDS])
        await wait_for_n_bytes(dut, received, len(EXPECTED_UART_SEQUENCE))
        await ClockCycles(dut.clk, 2 * CLKS_PER_BIT)      # TX en reposo
 
        dut.rst_n.value = 0
        await ClockCycles(dut.clk, 4)
        assert _mode(dut) == 0b00, f"tras el reset el modo es {_mode(dut):02b}"
        uio = int(dut.uio_out.value)
        assert (uio >> SPI_CS_BIT) & 1 == 1 and (uio >> SPI_SCLK_BIT) & 1 == 0, "SPI no quedo en reposo"
        await ClockCycles(dut.clk, 6)
        dut.rst_n.value = 1
        await ClockCycles(dut.clk, 5)
 
        received.clear()
        await load_block0(dut, BLOQUES_TEST[0:BLOCK_WORDS])
        await wait_for_n_bytes(dut, received, len(EXPECTED_UART_SEQUENCE))
        assert received[:len(EXPECTED_UART_SEQUENCE)] == EXPECTED_UART_SEQUENCE, (
            f"tras el reset llego {[hex(b) for b in received]}"
        )
    finally:
        spi_task.cancel()
        uart_task.cancel()
 
 
