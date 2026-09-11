# OpenStudio2

OpenStudio2 is a CHIP-8 interpreter/firmware for the MiSTer FPGA RCA Studio II core. It is not intended to run on original Studio II hardware.

## Implementation

- CDP1861 display setup and clearing
- 16-level CHIP-8 return stack
- delay and sound timers
- Q-line beeper control
- standard 4x5 hexadecimal font
- keypad input
- sprite drawing and collision detection
- pseudorandom number generation
- direct access to the core's 4 KiB CHIP-8 RAM

Implemented instructions:

- `00E0`, `00EE`
- `1nnn`, `2nnn`, `Bnnn`
- `3xkk`, `4xkk`, `5xyn`, `9xy0`
- `6xkk`, `7xkk`
- `8xy0` through `8xy7`, `8xyE`
- `Annn`
- `Cxkk`
- `Dxyn`
- `Ex9E`, `ExA1`
- `Fx07`, `Fx0A`, `Fx15`, `Fx18`, `Fx1E` 
- `Fx29`, `Fx33`, `Fx55`, `Fx65`

Implementation details:

- `5xyn` ignores the low nibble, matching the original VIP (including Dot-Dash's `57AD`)
- `8xy6` and `8xyE` shift `Vy` into `Vx`
- logic operations leave `VF` unchanged
- `Fx55`/`Fx65` advance `I` by `x + 1`
- `Bnnn` uses `V0` as its offset and wraps the target to 12 bits

Extended CHIP-8 instruction sets are not supported. Unsupported instructions enter a trap.

## Input

CHIP-8 keys `0-9` map to Studio II keypad A `0-9`, and CHIP-8 keys `A-F` map to keypad B `1-6`.

## Memory model

| Purpose | CDP1802 physical address | CHIP-8 logical address |
|---|---:|---:|
| OpenStudio2 ROM | `$0000-$07FF` | n/a |
| OpenStudio2 work RAM | `$0800-$08FF` | n/a |
| CDP1861 display RAM | `$0900-$09FF` | n/a |
| CHIP-8 RAM | `$1000-$1FFF` | `$000-$FFF` |
| CHIP-8 font | `$1000-$104F` | `$000-$04F` |
| CHIP-8 program start | `$1200` | `$200` |

## Build / Test

Python 3 is required.

```text
python build.py
python build.py --check
python test_firmware.py
```

## License

OpenStudio2 is available under the [MIT License](LICENSE).
