import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Timer


@cocotb.test()
async def test_project(dut):

    # Clock (aunque no se use)
    clock = Clock(dut.clk, 10, unit="us")
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.rst_n.value = 1

    await Timer(1, unit="ns")

    # =========================
    # TEST 1: 3 + 2 = 5
    # =========================
    dut.ui_in.value = (2 << 4) | 3   # B=2, A=3
    dut.uio_in.value = 0             # op = ADD

    await Timer(1, unit="ns")
    assert dut.uo_out.value == 5

    # =========================
    # TEST 2: AND
    # =========================
    dut.ui_in.value = (1 << 4) | 3   # B=1, A=3
    dut.uio_in.value = 2             # op = AND

    await Timer(1, unit="ns")
    assert dut.uo_out.value == 1

    # =========================
    # TEST 3: OR
    # =========================
    dut.ui_in.value = (3 << 4) | 2   # B=3, A=2
    dut.uio_in.value = 3             # op = OR

    await Timer(1, unit="ns")
    assert dut.uo_out.value == 3