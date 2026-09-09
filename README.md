# OpenStudio2 firmware

OpenStudio2 is independently written, MIT-licensed CDP1802 firmware for the
RCA Studio II MiSTer core. The implementation does not use or copy RCA firmware
code or Marcel van Tongeren's Studio II CHIP-8 interpreter.

OpenStudio2 is a clean-room CHIP-8 environment rather than a replacement for
native Studio II firmware. Retail Studio II cartridges should continue to use
normal Studio II firmware; Marcel's interpreter remains useful as an optional
historical compatibility path.

## Current implementation

The current source is a partial CHIP-8 interpreter with reset and RAM
initialization, CDP1861 video setup, display clearing, a 16-level CHIP-8 return
stack, delay/sound timers, Q beeper control, a standard 4x5 hexadecimal font,
and direct access to the MiSTer-native 4 KiB CHIP-8 RAM window.

Implemented CHIP-8 instructions:

- Display and return: `00E0`, `00EE`.
- Jump and call: `1nnn`, `2nnn`.
- Conditional skips: `3xkk`, `4xkk`, `5xy0`, `9xy0`.
- Register load and addition: `6xkk`, `7xkk`.
- Arithmetic and logic: `8xy0` through `8xy7`, and `8xyE`.
- Index assignment: `Annn`.
- Sprite drawing: `Dxyn`, with XOR collision reporting and wrapped edges.
- Timers and index operations: `Fx07`, `Fx15`, `Fx18`, `Fx1E`.
- Font and memory operations: `Fx29`, `Fx33`, `Fx55`, `Fx65`.

The arithmetic implementation currently follows original COSMAC VIP behavior:
`8xy6` and `8xyE` shift `Vy` into `Vx`, logic operations leave `VF` unchanged,
and `Fx55`/`Fx65` advance `I` by `x + 1`.

Unsupported instructions enter a trap. Random values, offset jumps, key
handling, and wait-for-key remain unimplemented. Loading and playing real
CHIP-8 games on the FPGA has not yet been established.

## MiSTer-native memory model

Marcel van Tongeren's real-hardware Studio II interpreter has to split CHIP-8
program storage around the Studio II memory map and provides only 159 bytes of
free writable RAM. OpenStudio2 does not preserve those restrictions.

The MiSTer integration gives OpenStudio2 a dedicated contiguous 4 KiB
CHIP-8 RAM window:

| Purpose | CDP1802 physical address | CHIP-8 logical address |
|---|---:|---:|
| OpenStudio2 firmware ROM | `$0000-$07FF` | n/a |
| Interpreter work RAM | `$0800-$08FF` | n/a |
| CDP1861 display RAM | `$0900-$09FF` | n/a |
| Dedicated CHIP-8 RAM | `$1000-$1FFF` | `$000-$FFF` |
| CHIP-8 font | `$1000-$104F` | `$000-$04F` |
| CHIP-8 program start | `$1200` | `$200` |

A logical CHIP-8 address `NNN` is therefore represented internally as physical
`$1NNN`. Sequential program fetches, jumps, calls, `I`, fonts, and data access
all use the same contiguous mapping. There is no `$06FF->$0700` discontinuity,
no `$B00-$B9F` RAM alias, and no reduced program-size limit beyond CHIP-8's
normal 4 KiB address space.

V0-VF occupy `$08A0-$08AF`, delay and sound timers occupy `$08B2-$08B3`, the
stack pointer is at `$08B4`, and the 16-entry return stack occupies
`$08C0-$08DF`. Display RAM remains `$0900-$09FF`.

This mapping is implemented by the firmware and MiSTer RTL. OpenStudio2 has its
own dedicated RAM and loader path, while Marcel's historical interpreter keeps
its original split program mapping unchanged. Directed Verilator regressions
cover both interpreter sizes, both loader paths, the `$1FFF` boundary, oversize
rejection, native/Marcel/OS2 decode isolation, and CPU reads and writes through
the dedicated RAM.

## Build and validation

Python 3 is required. The checked-in binary and hexadecimal files are generated
from `openstudio2.asm`:

```text
python build.py
python build.py --check
python test_firmware.py
```

`openstudio2.bin` is the canonical 2 KiB ROM image, with unused bytes filled
with `FF`. `openstudio2.hex` is a 4 KiB, one-byte-per-line hexadecimal image
suitable for FPGA block-RAM initialization; its upper 2 KiB are also `FF`.

`openstudio2-dxyn-smoke.ch8` is a tiny visual hardware check. Load
`openstudio2.bin` as the CHIP-8 interpreter, then load the smoke test as the
CHIP-8 program. It draws `0` at the top left and `F` from `(63,31)`, wrapping
the latter across the right and bottom edges. Its matching `.hex` file records
the complete 24-byte test program in readable form.

The focused Python execution checks cover firmware bounds, boot/basic
execution, call/return, register skips, VIP-style arithmetic, timer
instructions, font/BCD/register memory operations, contiguous program fetch
across a physical page boundary, screen clearing, aligned and unaligned sprite
drawing, collision reporting, and horizontal/vertical edge wrapping. They use
small programs written for this project without original RCA or Marcel
interpreter bytes.

These checks do not validate CDP1861 interrupt/DMA timing, 60 Hz timer cadence,
audio timing, keypad behavior, real game compatibility, FPGA RAM inference, or
physical hardware behavior. No new Quartus or hardware validation is claimed
for this revision.

## License

OpenStudio2 is available under the [MIT License](LICENSE). Preserve its
copyright and permission notice when redistributing the firmware.
