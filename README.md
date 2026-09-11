# OpenStudio2 firmware

OpenStudio2 is an independently written, MIT-licensed CHIP-8 interpreter/firmware for the RCA Studio II MiSTer core.

Unlike the historical Studio II CHIP-8 interpreter, OpenStudio2 is designed specifically for the FPGA core rather than original hardware. It uses a core-provided contiguous 4 KiB CHIP-8 memory window, avoiding the split-memory layout required by the original real-hardware interpreter.

OpenStudio2 runs classic CHIP-8 software using the Studio II's CDP1802/CDP1861 environment. It is not intended to replace normal Studio II firmware or provide native Studio II cartridge compatibility.

## Current implementation

The current interpreter provides:

- CDP1861 display setup and clearing
- 16-level CHIP-8 return stack
- delay and sound timers
- Q-line beeper control
- standard 4x5 hexadecimal font
- keypad input
- sprite drawing and collision detection
- pseudorandom number generation
- direct access to the core's 4 KiB CHIP-8 RAM

Implemented CHIP-8 instructions:

- `00E0`, `00EE`
- `1nnn`, `2nnn`, `Bnnn`
- `3xkk`, `4xkk`, `5xy0`, `9xy0`
- `6xkk`, `7xkk`
- `8xy0` through `8xy7`, `8xyE`
- `Annn`
- `Cxkk`
- `Dxyn`
- `Ex9E`, `ExA1`
- `Fx07`, `Fx0A`, `Fx15`, `Fx18`, `Fx1E`
- `Fx29`, `Fx33`, `Fx55`, `Fx65`

Arithmetic behavior currently follows original COSMAC VIP conventions where applicable. `8xy6` and `8xyE` shift `Vy` into `Vx`, logic operations leave `VF` unchanged, and `Fx55`/`Fx65` advance `I` by `x + 1`. `Bnnn` uses `V0` as its offset and wraps the target to 12 bits.

`Cxkk` uses a deterministic 16-bit Galois generator with feedback `$B400`, seeded to `$ACE1` at reset. This is suitable for CHIP-8 execution but is not intended to reproduce the COSMAC VIP random sequence.

Unsupported instructions enter a trap. Extended CHIP-8 instruction sets are not currently supported; for example, software beginning with `00FF` will not run.

## Input

CHIP-8 keys `0-9` map to Studio II keypad A `0-9`, and CHIP-8 keys `A-F` map to keypad B `1-6`.

`Ex9E` and `ExA1` use the low nibble of `Vx`.

`Fx0A` accepts an already-held key and scans virtual keys `0-F` in ascending order. If more than one key is held, the lowest-numbered key is selected. With no key pressed, execution waits while display DMA, interrupts, and timers continue.

## Memory model

OpenStudio2 uses a dedicated contiguous CHIP-8 RAM window supplied by the MiSTer core:

| Purpose | CDP1802 physical address | CHIP-8 logical address |
|---|---:|---:|
| OpenStudio2 firmware ROM | `$0000-$07FF` | n/a |
| Interpreter work RAM | `$0800-$08FF` | n/a |
| CDP1861 display RAM | `$0900-$09FF` | n/a |
| Dedicated CHIP-8 RAM | `$1000-$1FFF` | `$000-$FFF` |
| CHIP-8 font | `$1000-$104F` | `$000-$04F` |
| CHIP-8 program start | `$1200` | `$200` |

A CHIP-8 address `NNN` therefore corresponds internally to CDP1802 physical address `$1NNN`.

Program fetches, jumps, calls, `I`, fonts, and data accesses all use this contiguous mapping. CHIP-8 software has the normal 4 KiB logical address space without the split program layout used by the historical Studio II interpreter.

V0-VF occupy `$08A0-$08AF`, the delay and sound timers `$08B2-$08B3`, the stack pointer `$08B4`, and the 16-entry return stack `$08C0-$08DF`.

OpenStudio2 has its own loader and RAM path in the MiSTer core. The historical interpreter retains its existing memory layout separately.

## Build

Python 3 is required.

```text
python build.py
python build.py --check
python test_firmware.py
```

`openstudio2.bin` is the canonical 2 KiB ROM image, padded with `FF`.

`openstudio2.hex` is a 4 KiB one-byte-per-line hexadecimal image suitable for FPGA block-RAM initialization. Its unused upper 2 KiB are also filled with `FF`.

## Testing

`openstudio2-dxyn-smoke.ch8` is a small visual test program for sprite drawing and edge wrapping. It draws `0` at the upper left and `F` beginning at `(63,31)`, wrapping across the right and bottom edges.

The Python test suite covers the implemented instruction groups, stack behavior, timers, font and memory operations, sprite drawing, collision detection, edge wrapping, keypad handling, offset jumps, random-number behavior, unsupported instructions, and contiguous program fetches across physical page boundaries.

MiSTer Verilator tests also cover the dedicated OpenStudio2 RAM and loader path, address-boundary behavior, and separation from the native Studio II and historical CHIP-8 mappings.

A bounded 246-program diagnostic sweep currently reaches the instruction limit without trapping in 227 cases and traps in 19. This is a diagnostic result rather than a gameplay compatibility score.

Current tests do not establish full game compatibility or validate all physical-hardware details, including exact CDP1861 timing, timer cadence, audio timing, or physical keypad behavior.

## License

OpenStudio2 is available under the [MIT License](LICENSE). Preserve the copyright and permission notice when redistributing the firmware.
