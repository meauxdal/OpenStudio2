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


def chip8_physical(address: int) -> int:
    if 0x0200 <= address <= 0x06FF:
        return address + 0x0100
    if 0x0700 <= address <= 0x0AFF:
        return address + 0x0500
    raise AssertionError(f"CHIP-8 address outside initial program map: ${address:04X}")


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


def test_firmware_stays_below_chip8_program_area() -> None:
    image = firmware()
    assert image[0x0300:] == bytes([0xFF]) * (len(image) - 0x0300)


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
    run_until(cpu, lambda s: s.memory[0x08A1] == 0x22 and s.r[10] == 0x0456)
    assert cpu.video_on
    assert cpu.memory[0x08A0] == 3
    assert cpu.memory[0x08A1] == 0x22
    assert cpu.r[10] == 0x0456


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


def test_program_counter_crosses_split_mapping() -> None:
    cpu = chip8_cpu({
        0x0200: [0x16, 0xFE], # jump to logical 0x6FE
        0x06FE: [0x60, 0x01], # fetch ends at physical 0x800 -> remap to 0xC00
        0x0700: [
            0x70, 0x01,       # V0 becomes 2 after the discontinuity
            0x17, 0x02,
        ],
    })
    run_until(cpu, lambda s: s.memory[0x08A0] == 2)
    assert cpu.r[5] == 0x0C02


def test_clear_screen() -> None:
    cpu = chip8_cpu({0x0200: [0x12, 0x00]})
    run_until(cpu, lambda s: s.video_on)
    cpu.memory[0x0900:0x0A00] = bytes([0xFF]) * 0x100
    cpu.memory[0x0300:0x0304] = bytes([0x00, 0xE0, 0x12, 0x00])
    run_until(cpu, lambda s: not any(s.memory[0x0900:0x0A00]))


if __name__ == "__main__":
    test_firmware_stays_below_chip8_program_area()
    test_boot_and_basic_chip8_execution()
    test_call_and_return()
    test_register_skips()
    test_program_counter_crosses_split_mapping()
    test_clear_screen()
    print("OpenStudio2 initial CHIP-8 execution checks passed")
