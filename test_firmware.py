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
        self.keypad_a: set[int] = set()
        self.keypad_b: set[int] = set()
        self.key_selections: list[int] = []

    def read(self, address: int) -> int:
        return self.memory[address]

    def write(self, address: int, value: int) -> None:
        if 0x0800 <= address <= 0x09FF or 0x1000 <= address <= 0x1FFF:
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
        selection = self.last_output[2] & 15
        self.ef[3] = int(selection < 10 and selection in self.keypad_a)
        self.ef[4] = int(selection < 10 and selection in self.keypad_b)
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
                if low == 2:
                    self.key_selections.append(self.last_output[2] & 15)
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
            elif low == 0xC:
                immediate = self.fetch()
                total = self.d + immediate + self.df
                self.d, self.df = total & 0xFF, total >> 8
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


def chip8_physical(address: int) -> int:
    if 0x0000 <= address <= 0x0FFF:
        return 0x1000 | address
    raise AssertionError(f"CHIP-8 address outside 4 KiB space: ${address:04X}")


def chip8_cpu(segments: dict[int, Iterable[int]]) -> Cpu1802:
    cpu = Cpu1802(firmware())
    for logical, values in segments.items():
        payload = bytes(values)
        for offset, value in enumerate(payload):
            cpu.memory[chip8_physical(logical + offset)] = value
    return cpu


def run_until(cpu: Cpu1802, predicate, limit: int = 20000) -> Cpu1802:
    cpu.run_until(predicate, limit)
    return cpu


def test_firmware_fits_native_rom() -> None:
    image = firmware()
    assert len(image) == 0x0800


def test_boot_and_basic_chip8_execution() -> None:
    cpu = chip8_cpu({
        0x0200: [
            0x60, 0x01,       # V0 = 1
            0x70, 0x02,       # V0 = 3
            0x30, 0x03,       # skip next because V0 == 3
            0x61, 0xEE,
            0x61, 0x22,       # V1 = 0x22
            0xA4, 0x56,       # I = 0x456
            0x12, 0x0C,       # loop here
        ],
    })
    run_until(cpu, lambda s: s.memory[0x08A1] == 0x22 and s.r[10] == 0x1456)
    assert cpu.video_on
    assert cpu.memory[0x08A0] == 3
    assert cpu.memory[0x08A1] == 0x22
    assert cpu.r[10] == 0x1456


def test_call_and_return() -> None:
    cpu = chip8_cpu({
        0x0200: [
            0x22, 0x08,       # call 0x208
            0x61, 0x22,       # V1 = 0x22 after return
            0x12, 0x04,
        ],
        0x0208: [
            0x60, 0x33,       # V0 = 0x33
            0x00, 0xEE,
        ],
    })
    run_until(cpu, lambda s: s.memory[0x08A0] == 0x33 and s.memory[0x08A1] == 0x22)
    assert cpu.memory[0x08B4] == 0


def test_register_skips() -> None:
    cpu = chip8_cpu({
        0x0200: [
            0x60, 0x44,
            0x61, 0x44,
            0x50, 0x10,       # equal: skip V2 = 0xEE
            0x62, 0xEE,
            0x90, 0x10,       # equal: do not skip
            0x62, 0x22,
            0x41, 0x45,       # V1 != 0x45: skip V3 = 0xEE
            0x63, 0xEE,
            0x63, 0x33,
            0x12, 0x12,
        ],
    })
    run_until(cpu, lambda s: s.memory[0x08A2] == 0x22 and s.memory[0x08A3] == 0x33)
    assert cpu.memory[0x08A2] == 0x22
    assert cpu.memory[0x08A3] == 0x33



def test_register_equality_ignores_low_nibble() -> None:
    for nibble in range(16):
        for right in (0x15, 0x02):
            cpu = chip8_cpu({
                0x0200: [
                    0x67, 0x02,
                    0x6A, right,
                    0x6F, 0xA5,
                    0x57, 0xA0 | nibble,
                    0x61, 0x01,
                    0x62, 0x01,
                    0x12, 0x0C,
                ],
            })
            run_until(cpu, lambda s: s.memory[0x08A2] == 1)
            assert cpu.memory[0x08A1] == int(right != 0x02)
            assert cpu.memory[0x08A7] == 0x02
            assert cpu.memory[0x08AA] == right
            assert cpu.memory[0x08AF] == 0xA5


def test_alu_group_vip_semantics() -> None:
    cpu = chip8_cpu({
        0x0200: [
            0x60, 0xFE,       # V0 = FE
            0x61, 0x03,       # V1 = 03
            0x80, 0x14,       # V0 = 01, VF = 1 (carry)
            0x8A, 0xF0,       # VA = VF
            0x62, 0x05,
            0x63, 0x07,
            0x82, 0x35,       # V2 = FE, VF = 0 (borrow)
            0x8B, 0xF0,       # VB = VF
            0x64, 0x02,
            0x65, 0x07,
            0x84, 0x57,       # V4 = 05, VF = 1 (no borrow)
            0x8C, 0xF0,       # VC = VF
            0x66, 0x00,
            0x67, 0x03,
            0x86, 0x76,       # VIP: V6 = V7 >> 1 = 01, VF = 1
            0x8D, 0xF0,       # VD = VF
            0x68, 0x00,
            0x69, 0x81,
            0x88, 0x9E,       # VIP: V8 = V9 << 1 = 02, VF = 1
            0x8E, 0xF0,       # VE = VF
            0x12, 0x28,
        ],
    })
    run_until(cpu, lambda s: s.memory[0x08AE] == 1 and s.memory[0x08A8] == 2)
    assert cpu.memory[0x08A0] == 0x01
    assert cpu.memory[0x08AA] == 1
    assert cpu.memory[0x08A2] == 0xFE
    assert cpu.memory[0x08AB] == 0
    assert cpu.memory[0x08A4] == 0x05
    assert cpu.memory[0x08AC] == 1
    assert cpu.memory[0x08A6] == 0x01
    assert cpu.memory[0x08AD] == 1
    assert cpu.memory[0x08A8] == 0x02
    assert cpu.memory[0x08AE] == 1


def test_timer_instructions() -> None:
    cpu = chip8_cpu({
        0x0200: [
            0x62, 0x05,       # V2 = 5
            0xF2, 0x15,       # delay = V2
            0x62, 0x00,       # V2 = 0
            0xF2, 0x07,       # V2 = delay
            0x63, 0x03,       # V3 = 3
            0xF3, 0x18,       # sound = V3
            0x12, 0x0C,
        ],
    })
    run_until(cpu, lambda s: s.memory[0x08A2] == 5 and s.memory[0x08B3] == 3)
    assert cpu.memory[0x08B2] == 5
    assert cpu.memory[0x08B3] == 3


def test_font_and_i_memory_operations() -> None:
    cpu = chip8_cpu({
        0x0200: [
            0x6A, 0x0A,       # VA = A
            0xFA, 0x29,       # I = font(A) = 0x032
            0x12, 0x04,
        ],
    })
    run_until(cpu, lambda s: s.r[10] == 0x1032)
    assert cpu.memory[0x1032:0x1037] == bytes([0xF0, 0x90, 0xF0, 0x90, 0x90])

    cpu = chip8_cpu({
        0x0200: [
            0x63, 0x7B,       # V3 = 123
            0xA3, 0x50,       # I = 0x350
            0xF3, 0x33,       # BCD(V3) -> I..I+2
            0x12, 0x06,
        ],
    })
    run_until(cpu, lambda s: s.memory[0x1350:0x1353] == bytes([1, 2, 3]))
    assert cpu.r[10] == 0x1350

    cpu = chip8_cpu({
        0x0200: [
            0x60, 0x11,
            0x61, 0x22,
            0x62, 0x33,
            0xA3, 0x60,
            0xF2, 0x55,       # store V0..V2, VIP behavior advances I
            0x60, 0x00,
            0x61, 0x00,
            0x62, 0x00,
            0xA3, 0x60,
            0xF2, 0x65,       # load V0..V2, VIP behavior advances I
            0x12, 0x14,
        ],
    })
    run_until(cpu, lambda s: s.memory[0x08A2] == 0x33 and s.r[10] == 0x1363)
    assert cpu.memory[0x1360:0x1363] == bytes([0x11, 0x22, 0x33])
    assert cpu.memory[0x08A0:0x08A3] == bytes([0x11, 0x22, 0x33])

    cpu = chip8_cpu({
        0x0200: [
            0xAF, 0xF0,       # I = 0xFF0
            0x60, 0x30,
            0xF0, 0x1E,       # I = 0x020 after 12-bit wrap
            0x12, 0x06,
        ],
    })
    run_until(cpu, lambda s: s.r[10] == 0x1020)

def test_program_counter_crosses_physical_page_contiguously() -> None:
    cpu = chip8_cpu({
        0x0200: [0x12, 0xFE], # jump to logical 0x2FE -> physical 0x12FE
        0x02FE: [0x60, 0x01],
        0x0300: [
            0x70, 0x01,       # V0 becomes 2 after ordinary 0x12FF->0x1300 crossing
            0x13, 0x02,
        ],
    })
    run_until(cpu, lambda s: s.memory[0x08A0] == 2)
    assert cpu.r[5] == 0x1302


def test_clear_screen() -> None:
    cpu = chip8_cpu({0x0200: [0x12, 0x00]})
    run_until(cpu, lambda s: s.video_on)
    cpu.memory[0x0900:0x0A00] = bytes([0xFF]) * 0x100
    cpu.memory[chip8_physical(0x0200):chip8_physical(0x0200) + 4] = bytes([0x00, 0xE0, 0x12, 0x00])
    run_until(cpu, lambda s: not any(s.memory[0x0900:0x0A00]))


def test_sprite_drawing() -> None:
    # Byte-aligned five-row glyph: draw from I without changing I.
    cpu = chip8_cpu({
        0x0200: [
            0xA3, 0x00,       # I = 0x300
            0x60, 0x00,       # V0 = X = 0
            0x61, 0x00,       # V1 = Y = 0
            0xD0, 0x15,       # draw five rows
            0x62, 0x01,
            0x12, 0x0A,
        ],
        0x0300: [0xF0, 0x90, 0xF0, 0x90, 0x90],
    })
    run_until(cpu, lambda s: s.memory[0x08A2] == 1)
    assert bytes(cpu.memory[0x0900:0x0929:8])[:5] == bytes([0xF0, 0x90, 0xF0, 0x90, 0x90])
    assert cpu.memory[0x08AF] == 0
    assert cpu.r[10] == 0x1300

    # An overlapping set pixel is erased by XOR and reports collision in VF.
    cpu = chip8_cpu({
        0x0200: [
            0xA3, 0x00,
            0x60, 0x00,
            0x61, 0x00,
            0xD0, 0x11,
            0x62, 0x01,
            0x12, 0x0A,
        ],
        0x0300: [0x80],
    })
    run_until(cpu, lambda s: s.video_on)
    cpu.memory[0x0900] = 0x80
    run_until(cpu, lambda s: s.memory[0x08A2] == 1)
    assert cpu.memory[0x0900] == 0
    assert cpu.memory[0x08AF] == 1

    # X=63 splits the sprite between byte columns 7 and 0; Y=31 wraps the
    # second sprite row to row zero.
    cpu = chip8_cpu({
        0x0200: [
            0xA3, 0x00,
            0x60, 0x3F,
            0x61, 0x1F,
            0xD0, 0x12,
            0x62, 0x01,
            0x12, 0x0A,
        ],
        0x0300: [0xC0, 0x80],
    })
    run_until(cpu, lambda s: s.memory[0x08A2] == 1)
    assert cpu.memory[0x09FF] == 0x01  # row 31, pixel 63
    assert cpu.memory[0x09F8] == 0x80  # row 31, wrapped pixel 0
    assert cpu.memory[0x0907] == 0x01  # wrapped row 0, pixel 63
    assert cpu.memory[0x08AF] == 0

    # N=0 is a no-op in the base 64x32 interpreter and clears VF.
    cpu = chip8_cpu({
        0x0200: [
            0x6F, 0x01,
            0x60, 0x00,
            0x61, 0x00,
            0xD0, 0x10,
            0x62, 0x01,
            0x12, 0x0C,
        ],
    })
    run_until(cpu, lambda s: s.memory[0x08A2] == 1)
    assert not any(cpu.memory[0x0900:0x0A00])
    assert cpu.memory[0x08AF] == 0


def test_alu_xor_dispatch() -> None:
    cpu = chip8_cpu({0x200: [
        0x68, 0xA5, 0x63, 0x3C, 0x6F, 0x07,
        0x88, 0x33,  # V8 ^= V3; Amabie uses this opcode at $361.
        0x62, 0x01, 0x12, 0x0A,
    ]})
    run_until(cpu, lambda c: c.memory[0x08A2] == 1)
    assert cpu.memory[0x08A8] == 0x99
    assert cpu.memory[0x08A3] == 0x3C
    assert cpu.memory[0x08AF] == 7


def test_offset_jump() -> None:
    symbols = define_symbols(SOURCE.read_text().splitlines())
    for target, offset, expected in ((0x234, 5, 0x239), (0x2FF, 1, 0x300),
                                     (0xFFF, 1, 0), (0xFF0, 0xFF, 0x0EF),
                                     (0, 0, 0), (0x800, 0x80, 0x880)):
        cpu = chip8_cpu({0x200: [0xB0 | (target >> 8), target & 255]})
        run_until(cpu, lambda c: c.r[c.p] == symbols['interpreter'])
        cpu.memory[0x8A0:0x8B0] = bytes([offset] + [0x55] * 15)
        cpu.r[10] = 0x1456
        run_until(cpu, lambda c: c.r[c.p] == symbols['op_jump_offset'])
        run_until(cpu, lambda c: c.r[c.p] == symbols['interpreter'])
        assert cpu.r[5] == 0x1000 + expected
        assert cpu.r[10] == 0x1456
        assert cpu.memory[0x8A0:0x8B0] == bytes([offset] + [0x55] * 15)


def test_random_instruction() -> None:
    symbols = define_symbols(SOURCE.read_text().splitlines())
    for register in range(16):
        for mask in (0, 1, 3, 0x37, 0x3F, 0x80, 0xFF):
            cpu = chip8_cpu({0x200: [0xC0 | register, mask]})
            run_until(cpu, lambda c: c.r[c.p] == symbols['interpreter'])
            cpu.memory[0x8A0:0x8B0] = bytes([0xA5] * 16)
            cpu.r[10] = 0x1234
            run_until(cpu, lambda c: c.r[c.p] == symbols['op_random'])
            run_until(cpu, lambda c: c.r[c.p] == symbols['interpreter'])
            expected = bytearray([0xA5] * 16)
            expected[register] = 0x70 & mask
            assert cpu.memory[0x8A0:0x8B0] == expected
            assert cpu.r[9] == 0xE270  # First state from the documented reset seed.
            assert cpu.r[10] == 0x1234
            assert cpu.r[5] == 0x1202

    # Exercise the native handler over the full period, including zero output.
    cpu = chip8_cpu({0x200: [0xC5, 0xFF]})
    run_until(cpu, lambda c: c.r[c.p] == symbols['op_random'])
    seen = set()
    counts = [0] * 256
    for _ in range(65535):
        cpu.r[cpu.p] = symbols['op_random']
        run_until(cpu, lambda c: c.r[c.p] == symbols['interpreter'])
        state = cpu.r[9]
        assert state and state not in seen
        seen.add(state)
        counts[cpu.memory[0x8A5]] += 1
    assert cpu.r[9] == 0xACE1
    assert counts == [255] + [256] * 255


def test_key_skips() -> None:
    symbols = define_symbols(SOURCE.read_text().splitlines())
    for key in range(16):
        for masked in (key, 0xB0 | key):
            for opcode in (0x9E, 0xA1):
                for pressed in (False, True):
                    cpu = chip8_cpu({0x200: [0x63, masked, 0xE3, opcode,
                                             0x64, 0x11, 0x65, 0x22, 0x12, 0x08]})
                    digit = key if key < 10 else key - 9
                    pad = cpu.keypad_a if key < 10 else cpu.keypad_b
                    if pressed:
                        pad.add(digit)
                    # A press on the other pad must not count.
                    (cpu.keypad_b if key < 10 else cpu.keypad_a).add(digit)
                    run_until(cpu, lambda c: c.r[c.p] == symbols['key_scan'])
                    run_until(cpu, lambda c: c.r[c.p] == symbols['interpreter'])
                    skipped = pressed == (opcode == 0x9E)
                    assert cpu.r[5] == (0x1206 if skipped else 0x1204)
                    run_until(cpu, lambda c: c.memory[0x08A5] == 0x22)
                    assert cpu.memory[0x08A4] == (0 if skipped else 0x11)
                    assert cpu.memory[0x08A3] == masked
                    assert cpu.key_selections == [digit]


def test_wait_key() -> None:
    symbols = define_symbols(SOURCE.read_text().splitlines())
    for key in range(16):
        for register in (0, 7, 15):
            for held in (False, True):
                cpu = chip8_cpu({0x200: [0x60 | register, 0xEE,
                                         0xF0 | register, 0x0A, 0x12, 0x04]})
                pad = cpu.keypad_a if key < 10 else cpu.keypad_b
                digit = key if key < 10 else key - 9
                if held:
                    pad.add(digit)
                run_until(cpu, lambda c: c.r[c.p] == symbols['key_scan'])
                if not held:
                    for _ in range(3000):
                        cpu.step()
                        assert cpu.ie == 1
                        assert cpu.r[5] == 0x1204
                        assert cpu.memory[0x08A0 + register] == 0xEE
                    assert set(cpu.key_selections) == set(range(10))
                    pad.add(digit)

                # FX0A must latch the selected key and wait for that same key
                # to be released before storing it in VX and returning.
                run_until(cpu, lambda c: c.r[c.p] == symbols['key_wait_release'])
                for _ in range(100):
                    cpu.step()
                    assert cpu.r[5] == 0x1204
                    assert cpu.memory[0x08A0 + register] == 0xEE
                pad.remove(digit)

                run_until(cpu, lambda c: c.r[c.p] == symbols['interpreter'])
                assert cpu.memory[0x08A0 + register] == key
                assert cpu.r[5] == 0x1204
                assert all(0 <= d < 10 for d in cpu.key_selections)
                assert cpu.r[2] == 0x08FF

    # Held simultaneous keys resolve in ascending virtual order. Once FX0A
    # chooses one key, other held keys do not satisfy its release wait.
    cpu = chip8_cpu({0x200: [0xF2, 0x0A, 0x12, 0x02]})
    cpu.keypad_a.update((9, 0))
    cpu.keypad_b.add(1)
    run_until(cpu, lambda c: c.r[c.p] == symbols['key_wait_release'])
    assert cpu.r[13] & 15 == 0
    cpu.keypad_a.remove(0)
    run_until(cpu, lambda c: c.r[c.p] == symbols['interpreter'])
    assert cpu.memory[0x08A2] == 0


def test_unsupported_key_variants() -> None:
    symbols = define_symbols(SOURCE.read_text().splitlines())
    for group, supported in ((0xE0, {0x9E, 0xA1}),
                             (0xF0, {0x0A, 0x07, 0x15, 0x18, 0x1E, 0x29, 0x33, 0x55, 0x65})):
        for low in set(range(256)) - supported:
            cpu = chip8_cpu({0x200: [group | 3, low]})
            run_until(cpu, lambda c: c.r[c.p] == symbols['unsupported'])
            assert not cpu.key_selections


if __name__ == "__main__":
    test_firmware_fits_native_rom()
    test_boot_and_basic_chip8_execution()
    test_call_and_return()
    test_register_skips()
    test_register_equality_ignores_low_nibble()
    test_alu_group_vip_semantics()
    test_timer_instructions()
    test_font_and_i_memory_operations()
    test_program_counter_crosses_physical_page_contiguously()
    test_clear_screen()
    test_sprite_drawing()
    test_offset_jump()
    test_random_instruction()
    test_key_skips()
    test_alu_xor_dispatch()
    test_wait_key()
    test_unsupported_key_variants()
    print("OpenStudio2 CHIP-8 execution checks passed")
