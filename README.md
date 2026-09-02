# OpenStudio2 firmware

OpenStudio2 is a reimplementation of the RCA Studio II firmware 
under the MIT License.

The implementation does not use or copy RCA firmware code.

Python 3 is required. The checked-in binary and hexadecimal files
are generated from `openstudio2.asm`:

```text
python build.py
python build.py --check
python test_firmware.py
```

`openstudio2.bin` is the canonical 2 KiB ROM image. `openstudio2.hex` is a
4 KiB, one-byte-per-line hexadecimal image suitable for FPGA block-RAM
initialization; its upper 2 KiB are filled with `FF`.

The prototype supplies reset, RAM initialization, CDP1861 video, frame timers,
beeper control, native `0nnn` machine calls, and these Studio II bytecode
instructions:

- Control: `1nnn`, `2nnn`, `3xaa`, `4xaa`, `5xkk`, `70aa`, and `C0`.
- Variables and arithmetic: `6xkk`, `7xkk` for `x=1-F`, and
  `8xy1/2/3/4/5/6/7/E`.
- Memory and index: `9xy0/1/2/4/8`, `Annn`, `Bnkk`, and
  `FxA6/A9/AC/AF/B3/B6/F2`.
- Input and random values: `Cxkk` for `x=1-F` and `Dkaa`.
- Graphics: `E0`, `E1`, `E2`, `E4`, and `E8aa`.

Graphics use the eight 16-byte pattern buffers selected by V9. `E0` clears a
buffer, `E1` moves it using its stored direction, `E2` moves it using VC,
`E4` XOR-loads its configured number of rows from the index address, and
`E8aa` XOR-draws it with a collision branch. Directions are 2 up, 4 left,
6 right, and 8 down; other direction values skip the following two-byte
instruction.

Undefined encodings deliberately enter a trap. The focused checks use small
cartridge programs written for this project to exercise dispatch, subroutine
flow, keypad input, graphics loading and clearing, all four movement
directions, XOR drawing, and collision branches. No original cartridge or RCA
firmware bytes are test inputs.

The behavior was implemented from the published language and memory-map
descriptions in RCA's September 1977
[Programming Manual for STUDIO III](https://bitsavers.org/components/rca/cosmac/Programming_Manual_for_STUDIO_III_Sep77.pdf).

Compatibility with original cartridges is not established in this prototype.

## Validation

The firmware has passed its focused Python checks, all 32 reset-release phases
of the MiSTer core's Verilator rewind/cadence regression, and 120-frame soaks at
phases 0 and 28. The clean simulated frame hash was `BB31B0B5`. Hardware testing
produced a clean OPEN splash, stable repeated resets, and no malformed or black
starts.

For MiSTer firmware-only testing, copy `openstudio2.bin` to
`/media/fat/games/Studio-II/boot0.rom`. No RBF rebuild is required.

## License

OpenStudio2 is available under the [MIT License](LICENSE).
