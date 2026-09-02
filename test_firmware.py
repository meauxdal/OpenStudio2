#!/usr/bin/env python3
"""Focused execution checks for the distributable Studio II firmware."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from build import SOURCE, assemble, define_symbols


class Cpu1802:
    def __init__(self, rom: bytes):
        self.memory = bytearray([0xFF] * 0x10000)
        self.memory[: len(rom)] = rom
        self.r = [0] * 16
        self.d = 0
        self.df = 0
        self.p = 0
        self.x = 0
        self.q = 0
        self.t = 0
        self.ie = 1
        self.ef = [0, 0, 0, 0, 0]
        self.last_output = [0] * 8
        self.video_on = False

    def read(self, address: int) -> int:
        return self.memory[address]

    def write(self, address: int, value: int) -> None:
        if 0x0800 <= address <= 0x09FF:
            self.memory[address] = value & 0xFF

    def fetch(self) -> int:
        value = self.read(self.r[self.p])
        self.r[self.p] = (self.r[self.p] + 1) & 0xFFFF
        return value

    def interrupt(self) -> None:
        assert self.ie
        self.t = (self.x << 4) | self.p
        self.x, self.p, self.ie = 2, 1, 0

    def step(self) -> None:
        opcode = self.fetch()
        high, low = opcode >> 4, opcode & 15
        if high == 0x0:
            self.d = self.read(self.r[low])
        elif high == 0x1:
            self.r[low] = (self.r[low] + 1) & 0xFFFF
        elif high == 0x2:
            self.r[low] = (self.r[low] - 1) & 0xFFFF
        elif high == 0x3:
            if low == 8:
                self.r[self.p] = (self.r[self.p] + 1) & 0xFFFF
                return
            target = self.fetch()
            take = {
                0x0: True, 0x1: self.q != 0, 0x2: self.d == 0,
                0x3: self.df != 0, 0x4: self.ef[1] != 0,
                0x5: self.ef[2] != 0, 0x6: self.ef[3] != 0,
                0x7: self.ef[4] != 0, 0x9: self.q == 0,
                0xA: self.d != 0, 0xB: self.df == 0,
                0xC: self.ef[1] == 0, 0xD: self.ef[2] == 0,
                0xE: self.ef[3] == 0, 0xF: self.ef[4] == 0,
            }.get(low)
            if take is None:
                raise AssertionError(f"unsupported test branch ${opcode:02X}")
            if take:
                self.r[self.p] = (self.r[self.p] & 0xFF00) | target
        elif high == 0x4:
            self.d = self.read(self.r[low])
            self.r[low] = (self.r[low] + 1) & 0xFFFF
        elif high == 0x5:
            self.write(self.r[low], self.d)
        elif high == 0x6:
            if 1 <= low <= 7:
                self.last_output[low] = self.read(self.r[self.x])
                self.r[self.x] = (self.r[self.x] + 1) & 0xFFFF
            elif 9 <= low <= 15:
                if low == 9:
                    self.video_on = True
                self.write(self.r[self.x], 0)
                self.d = 0
            else:
                raise AssertionError(f"unsupported test I/O opcode ${opcode:02X}")
        elif high == 0x7:
            if low == 0x0:
                value = self.read(self.r[self.x])
                self.r[self.x] = (self.r[self.x] + 1) & 0xFFFF
                self.x, self.p, self.ie = value >> 4, value & 15, 1
            elif low == 0x3:
                self.write(self.r[self.x], self.d)
                self.r[self.x] = (self.r[self.x] - 1) & 0xFFFF
            elif low == 0x8:
                self.write(self.r[self.x], self.t)
            elif low == 0x6:
                old_df = self.df
                self.df = self.d & 1
                self.d = (self.d >> 1) | (old_df << 7)
            elif low == 0xA:
                self.q = 0
            elif low == 0xB:
                self.q = 1
            elif low == 0xE:
                old_df = self.df
                self.df = self.d >> 7
                self.d = ((self.d << 1) & 0xFF) | old_df
            else:
                raise AssertionError(f"unsupported test 7x opcode ${opcode:02X}")
        elif high == 0x8:
            self.d = self.r[low] & 0xFF
        elif high == 0x9:
            self.d = self.r[low] >> 8
        elif high == 0xA:
            self.r[low] = (self.r[low] & 0xFF00) | self.d
        elif high == 0xB:
            self.r[low] = (self.d << 8) | (self.r[low] & 0xFF)
        elif high == 0xC:
            if low == 4:
                return
            target = (self.fetch() << 8) | self.fetch()
            take = {
                0x0: True, 0x1: self.q != 0, 0x2: self.d == 0,
                0x3: self.df != 0, 0x9: self.q == 0,
                0xA: self.d != 0, 0xB: self.df == 0,
            }.get(low)
            if take is None:
                raise AssertionError(f"unsupported test long branch ${opcode:02X}")
            if take:
                self.r[self.p] = target
        elif high == 0xD:
            self.p = low
        elif high == 0xE:
            self.x = low
        elif high == 0xF:
            if low == 0x0:
                self.d = self.read(self.r[self.x])
            elif low == 0x1:
                self.d |= self.read(self.r[self.x])
            elif low == 0x2:
                self.d &= self.read(self.r[self.x])
            elif low == 0x3:
                self.d ^= self.read(self.r[self.x])
            elif low == 0x4:
                total = self.d + self.read(self.r[self.x])
                self.d, self.df = total & 0xFF, total >> 8
            elif low == 0x5:
                value = self.read(self.r[self.x]) - self.d
                self.df = int(value >= 0)
                self.d = value & 0xFF
            elif low == 0x6:
                self.df, self.d = self.d & 1, self.d >> 1
            elif low == 0x7:
                value = self.d - self.read(self.r[self.x])
                self.df = int(value >= 0)
                self.d = value & 0xFF
            elif low == 0x8:
                self.d = self.fetch()
            elif low == 0x9:
                self.d |= self.fetch()
            elif low == 0xA:
                self.d &= self.fetch()
            elif low == 0xB:
                self.d ^= self.fetch()
            elif low == 0xC:
                total = self.d + self.fetch()
                self.d, self.df = total & 0xFF, total >> 8
            elif low == 0xD:
                value = self.fetch() - self.d
                self.df = int(value >= 0)
                self.d = value & 0xFF
            elif low == 0xE:
                self.df, self.d = self.d >> 7, (self.d << 1) & 0xFF
            elif low == 0xF:
                value = self.d - self.fetch()
                self.df = int(value >= 0)
                self.d = value & 0xFF
        else:
            raise AssertionError(f"unsupported test opcode ${opcode:02X}")

    def run_until(self, predicate, limit: int = 20000) -> None:
        for _ in range(limit):
            if predicate(self):
                return
            self.step()
        raise AssertionError("firmware did not reach expected state")


def firmware() -> bytes:
    return assemble(SOURCE.read_text(encoding="utf-8").splitlines())


def cartridge_cpu(
    segments: dict[int, Iterable[int]],
    setup: Callable[[Cpu1802], None] | None = None,
) -> Cpu1802:
    image = bytearray(firmware())
    for address, values in segments.items():
        payload = bytes(values)
        assert 0x0400 <= address and address + len(payload) <= 0x0800
        image[address:address + len(payload)] = payload
    cpu = Cpu1802(bytes(image))
    if setup is not None:
        setup(cpu)
    return cpu


def run_cartridge(
    segments: dict[int, Iterable[int]],
    setup: Callable[[Cpu1802], None] | None = None,
) -> Cpu1802:
    cpu = cartridge_cpu(segments, setup)
    cpu.run_until(lambda state: state.p == 3 and state.r[3] == 0x0700)
    return cpu


def test_builtin_splash() -> None:
    cpu = Cpu1802(firmware())
    cpu.run_until(
        lambda state: state.p == 3
        and state.read(state.r[3]) == 0x30
        and state.read(state.r[3] + 1) == (state.r[3] & 0xFF)
    )
    assert cpu.video_on
    assert cpu.memory[0x08D2] == 0xF8
    assert cpu.memory[0x08D4:0x08D6] == bytes([0x15, 0x11])
    assert cpu.memory[0x08D8:0x08DE] == bytes([4, 4, 1, 2, 5, 5])
    assert any(cpu.memory[0x0900:0x0A00])


def test_display_enable_does_not_alias_dma_register() -> None:
    symbols = define_symbols(SOURCE.read_text(encoding="utf-8").splitlines())
    cpu = Cpu1802(firmware())
    cpu.run_until(lambda state: state.video_on)
    assert cpu.p == 4

    # Model an immediately accepted eight-byte CDP1861 DMA burst. R0 may
    # advance, but the firmware entry PC must remain independent of it.
    cpu.r[0] = (cpu.r[0] + 8) & 0xFFFF
    cpu.run_until(lambda state: state.p == 3 and state.r[3] == symbols["splash_idle"])


def test_interrupt_vector_reenters_handler() -> None:
    symbols = define_symbols(SOURCE.read_text(encoding="utf-8").splitlines())
    image = firmware()
    assert symbols["irq_return"] + 1 == symbols["irq"]
    assert image[symbols["irq_return"]] == 0x70

    cpu = Cpu1802(image)
    cpu.run_until(lambda state: state.p == 3 and state.r[3] == symbols["splash_idle"])

    for _ in range(2):
        saved_x, saved_p = cpu.x, cpu.p
        cpu.ef[1] = 1
        cpu.interrupt()
        for _ in range(2000):
            if cpu.p == 1 and cpu.r[1] == symbols["wait_display_end"]:
                cpu.ef[1] = 0
            cpu.step()
            if cpu.ie and cpu.x == saved_x and cpu.p == saved_p:
                break
        else:
            raise AssertionError("interrupt handler did not return")
        assert cpu.r[1] == symbols["irq"]


def test_native_cartridge_entry() -> None:
    image = bytearray(firmware())
    image[0x0400:0x0402] = bytes([0x04, 0x20])
    image[0x0420:0x042B] = bytes([
        0xF8, 0x08, 0xB6, 0xF8, 0xF0, 0xA6,
        0xF8, 0xA5, 0x56, 0x30, 0x29,
    ])
    cpu = Cpu1802(bytes(image))
    cpu.run_until(lambda state: state.memory[0x08F0] == 0xA5)
    assert cpu.p == 3
    assert cpu.r[3] == 0x0429


def test_dispatch_table_and_bytecode_routes() -> None:
    symbols = define_symbols(SOURCE.read_text(encoding="utf-8").splitlines())
    handlers = [
        "unsupported", "op_jump", "op_call", "op_jnz",
        "op_jz", "op_skip_imm", "op_load_imm", "op_add_imm",
        "op_alu", "op_memory", "op_index", "op_store_indexed",
        "op_return_random", "op_key", "op_graphics", "op_extended",
    ]
    table = firmware()[symbols["dispatch_table"]:symbols["dispatch_table"] + 32]
    expected = b"".join(symbols[name].to_bytes(2, "big") for name in handlers)
    assert table == expected

    cpu = run_cartridge({
        0x0400: [0x14, 0x10],
        0x0410: [0x24, 0x30, 0x07, 0x00],
        0x0430: [
            0x61, 0x01,       # V1 = 1
            0x31, 0x36,       # branch because V1 is nonzero
            0x61, 0xEE,
            0x41, 0x3A,       # do not branch because V1 is nonzero
            0x51, 0xFF,       # skip the next two bytes
            0x61, 0xEE,
            0x61, 0x00,
            0x41, 0x42,       # branch because V1 is zero
            0x61, 0xEE,
            0x51, 0x00,       # equal, so do not skip
            0x64, 0x3C,
            0x62, 0xA5,
            0x63, 0x5A,
            0x82, 0x33,       # V2 ^= V3
            0x94, 0x21,       # V4 -> V2
            0x60, 0x02,
            0x70, 0x50,       # loop until V0 reaches its terminal value
            0xA8, 0x80,
            0xB0, 0xA5,
            0xF5, 0xA6,
            0x66, 0xFF,
            0x67, 0x82,
            0x96, 0x78,       # BCD V6 at page-8 address in V7
            0xC8, 0x00,
            0xC0,
        ],
    })
    assert cpu.memory[0x08C0] == 1
    assert cpu.memory[0x08C1] == 0
    assert cpu.memory[0x08C2] == 0x3C
    assert cpu.memory[0x08C5] == 0xA5
    assert cpu.memory[0x08C7] == 0x84
    assert cpu.memory[0x08C8] == 0
    assert cpu.memory[0x08CB] == 0
    assert cpu.memory[0x0880] == 0xA5
    assert cpu.memory[0x0882:0x0885] == bytes([2, 5, 5])

    for program in ([0x81, 0x20], [0x91, 0x23]):
        trapped = cartridge_cpu({0x0400: program})
        trapped.run_until(
            lambda state: state.p == 3
            and state.r[3] == symbols["unsupported"]
        )


def test_key_dispatch() -> None:
    cpu = run_cartridge(
        {
            0x0400: [
                0x6A, 0x01,
                0xD5, 0x0A,
                0x61, 0x11,
                0x07, 0x00,
            ],
            0x040A: [0x61, 0x22, 0x07, 0x00],
        },
        lambda state: state.ef.__setitem__(3, 1),
    )
    assert cpu.last_output[2] == 5
    assert cpu.memory[0x08CB] == 5
    assert cpu.memory[0x08C1] == 0x22


def test_graphics_load_draw_and_collision() -> None:
    setup = [
        0x69, 0x00,
        0xA8, 0xD0,
        0xB0, 0x10,
        0xA8, 0xD8,
        0xB0, 0x04,
        0xA4, 0x80,
        0xE4,
    ]
    source = [0x80, 0x40, 0x20, 0x10]

    drawn = run_cartridge({
        0x0400: setup + [0xE8, 0xFF, 0x07, 0x00],
        0x0480: source,
    })
    assert drawn.r[10] == 0x0484
    assert drawn.memory[0x0800:0x0808:2] == bytes(source)
    assert [drawn.memory[address] for address in (0x0910, 0x0918, 0x0920, 0x0928)] == source

    collided = run_cartridge({
        0x0400: setup + [
            0xE8, 0xFF,
            0xE8, 0x15,
            0x61, 0xEE,
            0xFF, 0xFF,
            0x61, 0x22,
            0x07, 0x00,
        ],
        0x0480: source,
    })
    assert collided.memory[0x08C1] == 0x22
    assert not any(collided.memory[0x0900:0x0A00])


def test_graphics_move_and_clear() -> None:
    cpu = run_cartridge({
        0x0400: [
            0x69, 0x00,
            0xA8, 0xD0,
            0xB0, 0x10,
            0xA8, 0xD8,
            0xB0, 0x01,
            0xA8, 0xE0,
            0xB0, 0x06,
            0xA4, 0x80,
            0xE4,
            0xE1,
            0x6C, 0x08,
            0xE2,
            0xE8, 0xFF,
            0xE0,
            0x6C, 0x03,
            0xE2,
            0x61, 0xEE,
            0x61, 0x22,
            0x07, 0x00,
        ],
        0x0480: [0xFF],
    })
    assert cpu.memory[0x08D0] == 0x19
    assert cpu.memory[0x08D8] == 0x81
    assert cpu.memory[0x08E0] == 0x06
    assert cpu.memory[0x08E8] == 0xFF
    assert cpu.memory[0x08F0] == 0xFF
    assert cpu.memory[0x0918:0x091A] == bytes([0x7F, 0x80])
    assert not any(cpu.memory[0x0800:0x0810]), cpu.memory[0x0800:0x0810]
    assert cpu.memory[0x08C1] == 0x22


def test_graphics_move_left_and_up() -> None:
    cpu = run_cartridge({
        0x0400: [
            0x69, 0x00,
            0xA8, 0xD0,
            0xB0, 0x40,
            0xA8, 0xD8,
            0xB0, 0x01,
            0xA4, 0x80,
            0xE4,
            0x6C, 0x04,
            0xE2,
            0x6C, 0x02,
            0xE2,
            0xE8, 0xFF,
            0x07, 0x00,
        ],
        0x0480: [0xFF],
    })
    assert cpu.memory[0x0800:0x0802] == bytes([0xFE, 0x01])
    assert cpu.memory[0x08D0] == 0x38
    assert cpu.memory[0x08D8] == 0x01
    assert cpu.memory[0x08E8] == 0xFF
    assert cpu.memory[0x08F0] == 0xFF
    assert cpu.memory[0x0937:0x0939] == bytes([0x01, 0xFE])


if __name__ == "__main__":
    test_builtin_splash()
    test_display_enable_does_not_alias_dma_register()
    test_interrupt_vector_reenters_handler()
    test_native_cartridge_entry()
    test_dispatch_table_and_bytecode_routes()
    test_key_dispatch()
    test_graphics_load_draw_and_collision()
    test_graphics_move_and_clear()
    test_graphics_move_left_and_up()
    print("OpenStudio2 focused execution checks passed")
