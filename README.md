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
- Jump and call: `1nnn`, `2nnn`, `Bnnn` (V0 offset).
- Conditional skips: `3xkk`, `4xkk`, `5xy0`, `9xy0`.
- Key input: `Ex9E`, `ExA1`, `Fx0A`.
- Register load and addition: `6xkk`, `7xkk`.
- Masked pseudorandom byte: `Cxkk`.
- Arithmetic and logic: `8xy0` through `8xy7`, and `8xyE`.
- Index assignment: `Annn`.
- Sprite drawing: `Dxyn`, with XOR collision reporting and wrapped edges.
- Timers and index operations: `Fx07`, `Fx15`, `Fx18`, `Fx1E`.
- Font and memory operations: `Fx29`, `Fx33`, `Fx55`, `Fx65`.

The arithmetic implementation currently follows original COSMAC VIP behavior:
`8xy6` and `8xyE` shift `Vy` into `Vx`, logic operations leave `VF` unchanged,
and `Fx55`/`Fx65` advance `I` by `x + 1`. `Bnnn` adds `V0` to `nnn`,
wrapping the logical target to 12 bits.

`Cxkk` advances a 16-bit right-shifting Galois generator with feedback `$B400`
and stores its low byte AND `kk` in `Vx`. R9 holds its state, seeded to `$ACE1`
at reset. The sequence repeats after 65,535 calls; a zero mask still advances
it. Resets reproduce the sequence: this does not reproduce the VIP's random
sequence or derive entropy from hardware timing. VF is unchanged unless it
is the destination register.

Unsupported instructions enter a trap, including unrecognized E/F low bytes.
Extended instruction sets, including the `00FF` instruction used at entry by
Destroy the Line, remain unsupported. Initial MiSTer testing has demonstrated
some playable games, but broad game compatibility is not yet established.

CHIP-8 keys `0–9` map to keypad A `0–9` (EF3), and `A–F` map to keypad B
`1–6` (EF4). One shared scanner selects the physical digit through `OUT 2`;
it never selects the unconnected digits `10–15`. The skip opcodes use only
the low nibble of `Vx` and skip exactly one two-byte instruction.

`Fx0A` accepts an already-held key without waiting for release or a new edge.
It repeatedly scans virtual keys `0` through `F` in ascending order and stores
the first detected key in `Vx`. Stable simultaneous keys therefore select the
lowest virtual key. With no key, execution waits while interrupts, display DMA,
and timers continue. This is an explicit input policy, not a claim of original
COSMAC VIP wait-for-key equivalence.

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
drawing, collision reporting, and horizontal/vertical edge wrapping. Input
checks model `OUT 2` and EF3/EF4, cover all 16 keys, nibble masking, both skip
outcomes and exact skip distance, held/later presses, blocked waits, destination
registers including VF, and every unsupported E/F low byte. Offset-jump checks
cover V0 selection, page carries and 12-bit wrapping. Random checks cover all
destination registers, masks, register preservation and the full 65,535-state
period, including zero output. They use
small programs written for this project without original RCA or Marcel
interpreter bytes.

These checks do not validate CDP1861 interrupt/DMA timing, 60 Hz timer cadence,
audio timing, physical keypad behavior, real game compatibility, FPGA RAM inference, or
physical hardware behavior. No new Quartus or hardware validation is claimed
for this revision.

The input revision was also checked with the existing MiSTer Verilator harness
using `--ce4`: DXYN smoke frames 18–23 matched a fresh `77f7cb0` baseline run
pixel-for-pixel. A smoke variant waiting in `F70A` retained the same consecutive
frames while its delay timer advanced, then stored `F` in V7 after B6 was pressed
at frame 20. The IDL-synchronized ISR is unchanged. Final acceptance still
requires MiSTer hardware input and consecutive-frame checks.

After adding `Cxkk` and `Bnnn`, the same bounded 246-game diagnostic sweep
dropped from 149 observed traps to 19. The other 227 runs exhausted their
instruction budget without trapping; this is not a gameplay compatibility
score. Astro Dodge, Deep8 and Deflection also reached frame 600 in `--ce4`
simulation without remaining in the firmware trap. Six consecutive DXYN smoke
frames matched the pre-change baseline pixel-for-pixel. These new instructions
still need MiSTer hardware testing; Destroy the Line still requires unsupported
instructions beginning with `00FF`.

## License

OpenStudio2 is available under the [MIT License](LICENSE). Preserve its
copyright and permission notice when redistributing the firmware.
