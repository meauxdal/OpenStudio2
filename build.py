#!/usr/bin/env python3
"""Assemble the OpenStudio2 firmware and emit reproducible ROM images."""

from __future__ import annotations

import argparse
import ast
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "openstudio2.asm"
BINARY = ROOT / "openstudio2.bin"
HEX = ROOT / "openstudio2.hex"
ROM_SIZE = 0x800
BRAM_SIZE = 0x1000


REGISTER_OPS = {
    "ldn": 0x00, "inc": 0x10, "dec": 0x20, "lda": 0x40,
    "str": 0x50, "glo": 0x80, "ghi": 0x90, "plo": 0xA0,
    "phi": 0xB0, "sep": 0xD0, "sex": 0xE0,
}
SHORT_BRANCHES = {
    "br": 0x30, "bq": 0x31, "bz": 0x32, "bdf": 0x33,
    "b1": 0x34, "b2": 0x35, "b3": 0x36, "b4": 0x37,
    "bnq": 0x39, "bnz": 0x3A, "bnf": 0x3B,
    "bn1": 0x3C, "bn2": 0x3D, "bn3": 0x3E, "bn4": 0x3F,
}
LONG_BRANCHES = {
    "lbr": 0xC0, "lbq": 0xC1, "lbz": 0xC2, "lbdf": 0xC3,
    "lbnq": 0xC9, "lbnz": 0xCA, "lbnf": 0xCB,
}
IMMEDIATE_OPS = {
    "adci": 0x7C, "sdbi": 0x7D, "smbi": 0x7F,
    "ldi": 0xF8, "ori": 0xF9, "ani": 0xFA, "xri": 0xFB,
    "adi": 0xFC, "sdi": 0xFD, "smi": 0xFF,
}
FIXED_OPS = {
    "idl": 0x00, "skp": 0x38, "irx": 0x60,
    "ret": 0x70, "dis": 0x71, "ldxa": 0x72, "stxd": 0x73,
    "adc": 0x74, "sdb": 0x75, "shrc": 0x76, "smb": 0x77,
    "sav": 0x78, "mark": 0x79, "req": 0x7A, "seq": 0x7B,
    "shlc": 0x7E, "nop": 0xC4,
    "lsnq": 0xC5, "lsnz": 0xC6, "lsnf": 0xC7, "lskp": 0xC8,
    "lsie": 0xCC, "lsq": 0xCD, "lsz": 0xCE, "lsdf": 0xCF,
    "ldx": 0xF0, "or": 0xF1, "and": 0xF2, "xor": 0xF3,
    "add": 0xF4, "sd": 0xF5, "shr": 0xF6, "sm": 0xF7,
    "shl": 0xFE,
}


class AssemblyError(Exception):
    pass


def clean_line(raw: str) -> str:
    return raw.split(";", 1)[0].strip()


def split_label(line: str) -> tuple[str | None, str]:
    match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", line)
    return (match.group(1), match.group(2).strip()) if match else (None, line)


def normalize_expr(text: str) -> str:
    text = re.sub(r"\$([0-9A-Fa-f]+)", r"0x\1", text)
    text = re.sub(r"%([01]+)", r"0b\1", text)
    return text.replace("/", "//")


def eval_expr(text: str, symbols: dict[str, int]) -> int:
    operators = {
        ast.Add: lambda a, b: a + b, ast.Sub: lambda a, b: a - b,
        ast.Mult: lambda a, b: a * b, ast.FloorDiv: lambda a, b: a // b,
        ast.BitAnd: lambda a, b: a & b, ast.BitOr: lambda a, b: a | b,
        ast.BitXor: lambda a, b: a ^ b, ast.LShift: lambda a, b: a << b,
        ast.RShift: lambda a, b: a >> b,
    }

    def visit(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return visit(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.Name) and node.id.lower() in symbols:
            return symbols[node.id.lower()]
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return operators[type(node.op)](visit(node.left), visit(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub, ast.Invert)):
            value = visit(node.operand)
            return value if isinstance(node.op, ast.UAdd) else -value if isinstance(node.op, ast.USub) else ~value
        raise AssemblyError(f"unsupported expression: {text}")

    try:
        return visit(ast.parse(normalize_expr(text), mode="eval"))
    except (SyntaxError, ZeroDivisionError) as exc:
        raise AssemblyError(f"invalid expression: {text}") from exc


def instruction_size(line: str) -> int:
    mnemonic = line.split(None, 1)[0].lower()
    if mnemonic in REGISTER_OPS or mnemonic in FIXED_OPS or mnemonic in {"out", "inp"}:
        return 1
    if mnemonic in SHORT_BRANCHES or mnemonic in IMMEDIATE_OPS:
        return 2
    if mnemonic in LONG_BRANCHES:
        return 3
    raise AssemblyError(f"unknown instruction: {line}")


def define_symbols(lines: list[str]) -> dict[str, int]:
    symbols = {f"r{index:x}": index for index in range(16)}
    pc = 0
    for number, raw in enumerate(lines, 1):
        line = clean_line(raw)
        if not line:
            continue
        constant = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", line)
        if constant:
            symbols[constant.group(1).lower()] = eval_expr(constant.group(2), symbols)
            continue
        label, line = split_label(line)
        if label:
            key = label.lower()
            if key in symbols:
                raise AssemblyError(f"line {number}: duplicate symbol {label}")
            symbols[key] = pc
        if not line:
            continue
        if line.lower().startswith(".org "):
            pc = eval_expr(line[5:], symbols)
        elif line.lower().startswith(".byte "):
            pc += len(line[6:].split(","))
        elif line.lower().startswith(".fill "):
            pc += eval_expr(line[6:].split(",", 1)[0], symbols)
        elif line.lower() == ".end":
            break
        else:
            pc += instruction_size(line)
    return symbols


def assemble(lines: list[str]) -> bytes:
    symbols = define_symbols(lines)
    image = bytearray([0xFF] * ROM_SIZE)
    used = bytearray(ROM_SIZE)
    pc = 0

    def emit(value: int, number: int) -> None:
        nonlocal pc
        if not 0 <= value <= 0xFF:
            raise AssemblyError(f"line {number}: byte value out of range: {value}")
        if not 0 <= pc < ROM_SIZE:
            raise AssemblyError(f"line {number}: address outside 2 KiB ROM: ${pc:04X}")
        if used[pc]:
            raise AssemblyError(f"line {number}: address written twice: ${pc:04X}")
        image[pc] = value
        used[pc] = 1
        pc += 1

    for number, raw in enumerate(lines, 1):
        line = clean_line(raw)
        if not line or re.match(r"^[A-Za-z_][A-Za-z0-9_]*\s*=", line):
            continue
        _, line = split_label(line)
        if not line:
            continue
        lower = line.lower()
        if lower.startswith(".org "):
            pc = eval_expr(line[5:], symbols)
            continue
        if lower.startswith(".byte "):
            for item in line[6:].split(","):
                emit(eval_expr(item.strip(), symbols), number)
            continue
        if lower.startswith(".fill "):
            parts = [part.strip() for part in line[6:].split(",", 1)]
            count = eval_expr(parts[0], symbols)
            value = eval_expr(parts[1], symbols) if len(parts) == 2 else 0xFF
            for _ in range(count):
                emit(value, number)
            continue
        if lower == ".end":
            break

        parts = line.split(None, 1)
        mnemonic = parts[0].lower()
        operand = parts[1].strip() if len(parts) == 2 else ""
        if mnemonic in REGISTER_OPS:
            register = eval_expr(operand, symbols)
            if not 0 <= register <= 15:
                raise AssemblyError(f"line {number}: invalid register: {operand}")
            emit(REGISTER_OPS[mnemonic] | register, number)
        elif mnemonic in FIXED_OPS:
            if operand:
                raise AssemblyError(f"line {number}: unexpected operand: {operand}")
            emit(FIXED_OPS[mnemonic], number)
        elif mnemonic in SHORT_BRANCHES:
            target = eval_expr(operand, symbols)
            if (pc + 2) >> 8 != target >> 8:
                raise AssemblyError(f"line {number}: short branch crosses page: {operand}")
            emit(SHORT_BRANCHES[mnemonic], number)
            emit(target & 0xFF, number)
        elif mnemonic in LONG_BRANCHES:
            target = eval_expr(operand, symbols)
            emit(LONG_BRANCHES[mnemonic], number)
            emit((target >> 8) & 0xFF, number)
            emit(target & 0xFF, number)
        elif mnemonic in IMMEDIATE_OPS:
            emit(IMMEDIATE_OPS[mnemonic], number)
            emit(eval_expr(operand, symbols), number)
        elif mnemonic == "out":
            port = eval_expr(operand, symbols)
            if not 1 <= port <= 7:
                raise AssemblyError(f"line {number}: invalid output port: {port}")
            emit(0x60 | port, number)
        elif mnemonic == "inp":
            port = eval_expr(operand, symbols)
            if not 1 <= port <= 7:
                raise AssemblyError(f"line {number}: invalid input port: {port}")
            emit(0x68 | port, number)
        else:
            raise AssemblyError(f"line {number}: unknown instruction: {mnemonic}")
    return bytes(image)


def hex_image(binary: bytes) -> str:
    return "".join(f"{value:02X}\n" for value in binary + bytes([0xFF]) * (BRAM_SIZE - len(binary)))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="verify checked-in generated files")
    args = parser.parse_args()
    binary = assemble(SOURCE.read_text(encoding="utf-8").splitlines())
    rendered_hex = hex_image(binary)
    if args.check:
        if not BINARY.exists() or BINARY.read_bytes() != binary:
            raise SystemExit("openstudio2.bin is stale; run python build.py")
        if not HEX.exists() or HEX.read_text(encoding="ascii") != rendered_hex:
            raise SystemExit("openstudio2.hex is stale; run python build.py")
        print(f"OpenStudio2 firmware verified: {len(binary)} bytes")
        return 0
    BINARY.write_bytes(binary)
    HEX.write_text(rendered_hex, encoding="ascii", newline="\n")
    print(f"Wrote {BINARY.name} ({len(binary)} bytes) and {HEX.name} ({BRAM_SIZE} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
