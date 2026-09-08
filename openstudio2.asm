; SPDX-License-Identifier: MIT
;
; OpenStudio2 -- independently written CHIP-8 firmware for RCA Studio II.
;
; MiSTer-native CHIP-8 bring-up version. Native Studio II bytecode
; compatibility is intentionally not provided. OpenStudio2 assumes the core
; supplies a dedicated 4 KiB CHIP-8 RAM window:
;
;   CHIP-8 logical $0000-$0FFF -> CDP1802 physical $1000-$1FFF
;
; CHIP-8 programs therefore start at physical $1200. This intentionally drops
; the split-memory translation required by Marcel van Tongeren's real-hardware
; Studio II interpreter.

RAM_PAGE       = $08
VIDEO_PAGE     = $09
CHIP8_BASE      = $10        ; logical $000-$FFF appears at physical $1000-$1FFF
VREG_LOW       = $A0
I_HIGH_LOW     = $B0        ; reserved for later memory-backed I if required
DELAY_LOW      = $B2
SOUND_LOW      = $B3
SP_LOW         = $B4
DRAW_MASK_LOW  = $B5        ; temporary shifted sprite byte
DRAW_ROW_LOW   = $B6        ; temporary display-row byte offset
CHIP_STACK_LOW = $C0        ; 16 x 16-bit physical return PCs: $08C0-$08DF
NATIVE_STACK   = $FF

        .org $0000

reset:
        ldi 0
        phi rb
        plo rb

        ldi irq >> 8
        phi r1
        ldi irq & $FF
        plo r1

; R2 is the native CDP1802 interrupt/scratch stack.  CHIP-8's return stack is
; separate at $08C0-$08DF.
        ldi RAM_PAGE
        phi r2
        phi r6
        phi r7
        ldi NATIVE_STACK
        plo r2

        ldi interpreter_entry >> 8
        phi r4
        ldi interpreter_entry & $FF
        plo r4

; R5 is the physical program counter corresponding to CHIP-8 logical $0200.
        ldi $12
        phi r5
        ldi 0
        plo r5

; RA holds the physical pointer for CHIP-8 I ($1NNN).
        ldi 0
        phi ra
        plo ra

; Clear Studio II RAM and display RAM ($0800-$09FF).
        ldi RAM_PAGE
        phi rd
        ldi 0
        plo rd
clear_ram:
        ldi 0
        str rd
        inc rd
        ghi rd
        xri $0A
        bnz clear_ram

; Install the standard 4x5 CHIP-8 hexadecimal font at logical $000-$04F.
; This is ordinary writable CHIP-8 memory in the MiSTer-native $1000 window.
        ldi font_data >> 8
        phi rd
        ldi font_data & $FF
        plo rd
        ldi CHIP8_BASE
        phi rc
        ldi 0
        plo rc
        phi re
        ldi 80
        plo re
copy_font:
        lda rd
        str rc
        inc rc
        dec re
        glo re
        bnz copy_font

; Switch away from P=0 before enabling the CDP1861.  An immediate DMA request
; must not advance R0 while it is still the reset-program counter.
        sex r2
        sep r4

irq_return:
        ret

; CDP1861 interrupt service.  This retains the known-good display cadence from
; the earlier OpenStudio2 prototype, but the old Studio timers are replaced by
; CHIP-8 delay and sound timers at $08B2/$08B3.
irq:
        dec r2
        sav
        dec r2
        stxd
        nop
        shlc
        str r2
        inc r9

        ldi VIDEO_PAGE
        phi r0
        glo rb
        plo r0
        sex r2

video_rows:
        dec r0
        plo r0
        sex r2
        dec r0
        plo r0
        sex r2
        dec r0
        plo r0
        sex r2
        glo r0
        sex r2
        bn1 video_rows

wait_display_end:
        dec r0
        plo r0
        b1 wait_display_end

; Delay timer: decrement once per display interrupt while nonzero.
        ldi RAM_PAGE
        phi r8
        ldi DELAY_LOW
        plo r8
        ldn r8
        bz delay_done
        smi 1
        str r8
delay_done:

; Sound timer: decrement once per display interrupt.  Q is asserted while the
; post-decrement value remains nonzero.
        ldi SOUND_LOW
        plo r8
        ldn r8
        bz sound_off
        smi 1
        str r8
        bz sound_off
        seq
        br restore_irq
sound_off:
        req
restore_irq:
        lda r2
        shr
        lda r2
        br irq_return

interpreter_entry:
; INP 1 enables the CDP1861.  The input byte is discarded on the native stack.
        dec r2
        inp 1
        inc r2

; ---------------------------------------------------------------------------
; CHIP-8 fetch/decode loop
; ---------------------------------------------------------------------------
;
; RF.0 = first opcode byte
; RE.0 = second opcode byte
; R5   = physical program counter
; RA   = physical CHIP-8 I pointer ($1NNN)
;
; Initial instruction subset:
;   00E0  00EE  1NNN  2NNN  3XNN  4XNN  5XY0
;   6XNN  7XNN  8XY0-8XY7  8XYE  9XY0  ANNN  DXYN
;   FX07  FX15  FX18  FX1E  FX29  FX33  FX55  FX65
;
; Unsupported instructions intentionally trap at `unsupported`.

interpreter:
        lda r5
        plo rf
        lda r5
        plo re

decode:
        glo rf
        ani $F0
        lbz op_0

        glo rf
        ani $F0
        xri $10
        lbz op_jump

        glo rf
        ani $F0
        xri $20
        lbz op_call

        glo rf
        ani $F0
        xri $30
        lbz op_skip_eq_imm

        glo rf
        ani $F0
        xri $40
        lbz op_skip_ne_imm

        glo rf
        ani $F0
        xri $50
        lbz op_skip_eq_reg

        glo rf
        ani $F0
        xri $60
        lbz op_load_imm

        glo rf
        ani $F0
        xri $70
        lbz op_add_imm

        glo rf
        ani $F0
        xri $80
        lbz op_alu

        glo rf
        ani $F0
        xri $90
        lbz op_skip_ne_reg

        glo rf
        ani $F0
        xri $A0
        lbz op_set_i

        glo rf
        ani $F0
        xri $D0
        lbz op_draw

        glo rf
        ani $F0
        xri $F0
        lbz op_f

        lbr unsupported

; 00E0 / 00EE ---------------------------------------------------------------
op_0:
        glo re
        xri $E0
        lbz op_clear
        glo re
        xri $EE
        lbz op_return
        lbr unsupported

op_clear:
        ldi VIDEO_PAGE
        phi rd
        ldi 0
        plo rd
clear_display:
        ldi 0
        str rd
        inc rd
        glo rd
        bnz clear_display
        lbr interpreter

; 00EE: pop a physical return PC from the CHIP-8 stack.
op_return:
        ldi RAM_PAGE
        phi r7
        ldi SP_LOW
        plo r7
        ldn r7
        lbz unsupported
        smi 1
        str r7
        shl
        adi CHIP_STACK_LOW
        plo rd
        ldi RAM_PAGE
        phi rd
        ldn rd
        phi r5
        inc rd
        ldn rd
        plo r5
        lbr interpreter

; 1NNN / 2NNN ---------------------------------------------------------------
op_jump:
        lbr set_pc_nnn

; Store the already-fetched physical return PC, then branch to NNN.
op_call:
        ldi RAM_PAGE
        phi r7
        ldi SP_LOW
        plo r7
        ldn r7
        smi $10
        lbdf unsupported
        ldn r7
        shl
        adi CHIP_STACK_LOW
        plo rd
        ldi RAM_PAGE
        phi rd
        ghi r5
        str rd
        inc rd
        glo r5
        str rd
        ldn r7
        adi 1
        str r7
        lbr set_pc_nnn

; Convert CHIP-8 NNN directly to the dedicated physical window $1NNN.
set_pc_nnn:
        glo rf
        ani $0F
        ori CHIP8_BASE
        phi r5
        glo re
        plo r5
        lbr interpreter

; 3XNN / 4XNN ---------------------------------------------------------------
op_skip_eq_imm:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        sex r6
        sd
        lbz skip_next
        lbr interpreter

op_skip_ne_imm:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        sex r6
        sd
        lbnz skip_next
        lbr interpreter

; 5XY0 / 9XY0 ---------------------------------------------------------------
op_skip_eq_reg:
        glo re
        ani $0F
        lbnz unsupported
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r7
        ldn r6
        sex r7
        xor
        lbz skip_next
        lbr interpreter

op_skip_ne_reg:
        glo re
        ani $0F
        lbnz unsupported
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r7
        ldn r6
        sex r7
        xor
        lbnz skip_next
        lbr interpreter

; Advance the physical PC by one CHIP-8 instruction. The dedicated CHIP-8
; window is contiguous, so no address-boundary translation is required.
skip_next:
        inc r5
        inc r5
        lbr interpreter

; 6XNN / 7XNN ---------------------------------------------------------------
op_load_imm:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        str r6
        lbr interpreter

op_add_imm:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        sex r6
        add
        str r6
        lbr interpreter


; 8XY0-8XY7 / 8XYE ----------------------------------------------------------
; These use original COSMAC VIP shift semantics: 8XY6 and 8XYE shift VY and
; store the result in VX. Logic operations leave VF unchanged.
op_alu:
        glo re
        ani $0F
        lbz op_alu_move
        glo re
        ani $0F
        xri $01
        lbz op_alu_or
        glo re
        ani $0F
        xri $02
        lbz op_alu_and
        glo re
        ani $0F
        xri $03
        glo re
        ani $0F
        xri $04
        lbz op_alu_add
        glo re
        ani $0F
        xri $05
        lbz op_alu_sub
        glo re
        ani $0F
        xri $06
        lbz op_alu_shr
        glo re
        ani $0F
        xri $07
        lbz op_alu_subn
        glo re
        ani $0F
        xri $0E
        lbz op_alu_shl
        lbr unsupported

; Point R6 at VX and R7 at VY. Their high bytes remain fixed at RAM_PAGE.
alu_xy_move:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r7
        ldn r7
        str r6
        lbr interpreter

op_alu_move:
        lbr alu_xy_move

op_alu_or:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r7
        ldn r6
        sex r7
        or
        str r6
        lbr interpreter

op_alu_and:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r7
        ldn r6
        sex r7
        and
        str r6
        lbr interpreter

op_alu_xor:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r7
        ldn r6
        sex r7
        xor
        str r6
        lbr interpreter

op_alu_add:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r7
        ldn r6
        sex r7
        add
        str r6
        ldi VREG_LOW + $0F
        plo r7
        ldi 0
        adci 0
        str r7
        lbr interpreter

op_alu_sub:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r7
        ldn r7
        sex r6
        sd
        str r6
        ldi VREG_LOW + $0F
        plo r7
        ldi 0
        adci 0
        str r7
        lbr interpreter

op_alu_subn:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r7
        ldn r6
        sex r7
        sd
        str r6
        ldi VREG_LOW + $0F
        plo r7
        ldi 0
        adci 0
        str r7
        lbr interpreter

op_alu_shr:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r7
        ldn r7
        shr
        str r6
        ldi VREG_LOW + $0F
        plo r7
        ldi 0
        adci 0
        str r7
        lbr interpreter

op_alu_shl:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r7
        ldn r7
        shl
        str r6
        ldi VREG_LOW + $0F
        plo r7
        ldi 0
        adci 0
        str r7
        lbr interpreter

; ANNN ----------------------------------------------------------------------
op_set_i:
        glo rf
        ani $0F
        ori CHIP8_BASE
        phi ra
        glo re
        plo ra
        lbr interpreter

; DXYN ----------------------------------------------------------------------
; XOR N sprite bytes at I onto the 64x32 display and set VF on collision.
; Coordinates and pixels wrap at both edges, matching the interpreter's
; existing original-VIP compatibility policy. I itself is not modified.
;
; R3.1 = X bit shift, R3.0 = X byte column
; RF.1 = current Y row, RF.0 = rows remaining
; RC   = walking sprite pointer, RE.0 = current sprite byte
; RD   = current display byte, R6/R7 = work-RAM pointers and shift counter
op_draw:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        ldn r6
        ani $3F
        plo r3
        ani $07
        phi r3
        glo r3
        shr
        shr
        shr
        plo r3

        glo re
        ani $0F
        plo rf
        glo re
        shr
        shr
        shr
        shr
        ori VREG_LOW
        plo r6
        ldn r6
        ani $1F
        phi rf

        ldi VREG_LOW + $0F
        plo r6
        ldi 0
        str r6

        ghi ra
        phi rc
        glo ra
        plo rc

        glo rf
        lbz draw_done

draw_row:
        lda rc
        plo re

; Convert (Y, X-byte) to the linear display offset Y*8 + X-byte.
        ldi DRAW_ROW_LOW
        plo r7
        ghi rf
        shl
        shl
        shl
        str r7
        glo r3
        sex r7
        add
        plo rd
        ldi VIDEO_PAGE
        phi rd

; Left display byte: sprite >> (X & 7).
        ldi DRAW_MASK_LOW
        plo r7
        ghi r3
        plo r6
        lbz draw_left_unshifted
        glo re
draw_left_shift:
        shr
        str r7
        dec r6
        glo r6
        lbz draw_left_ready
        ldn r7
        lbr draw_left_shift
draw_left_unshifted:
        glo re
        str r7
draw_left_ready:
        ldn rd
        sex r7
        and
        lbz draw_left_no_collision
        ldi VREG_LOW + $0F
        plo r6
        ldi 1
        str r6
draw_left_no_collision:
        ldn rd
        sex r7
        xor
        str rd

; A byte-aligned sprite has no right-hand fragment.
        ghi r3
        lbz draw_next_row

; Right display byte: sprite << (8 - (X & 7)).
        sdi 8
        plo r6
        glo re
draw_right_shift:
        shl
        str r7
        dec r6
        glo r6
        lbz draw_right_ready
        ldn r7
        lbr draw_right_shift
draw_right_ready:

; Advance one byte, wrapping byte column 7 back to column 0 of the same row.
        inc rd
        glo rd
        ani $07
        lbnz draw_right_address_ready
        glo rd
        smi 8
        plo rd
draw_right_address_ready:
        ldi VIDEO_PAGE
        phi rd

        ldn rd
        sex r7
        and
        lbz draw_right_no_collision
        ldi VREG_LOW + $0F
        plo r6
        ldi 1
        str r6
draw_right_no_collision:
        ldn rd
        sex r7
        xor
        str rd

draw_next_row:
        ghi rf
        adi 1
        ani $1F
        phi rf
        glo rf
        smi 1
        plo rf
        lbnz draw_row
draw_done:
        lbr interpreter


; FX07 / FX15 / FX18 ---------------------------------------------------------
op_f:
        glo re
        xri $07
        lbz op_get_delay
        glo re
        xri $15
        lbz op_set_delay
        glo re
        xri $18
        lbz op_set_sound
        glo re
        xri $1E
        lbz op_add_i
        glo re
        xri $29
        lbz op_font
        glo re
        xri $33
        lbz op_bcd
        glo re
        xri $55
        lbz op_store_regs
        glo re
        xri $65
        lbz op_load_regs
        lbr unsupported

op_get_delay:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        ldi DELAY_LOW
        plo r7
        ldn r7
        str r6
        lbr interpreter

op_set_delay:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        ldi DELAY_LOW
        plo r7
        ldn r6
        str r7
        lbr interpreter

op_set_sound:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        ldi SOUND_LOW
        plo r7
        ldn r6
        str r7
        lbr interpreter

; FX1E: I += VX, retaining the physical $1NNN representation and wrapping the
; logical result to 12 bits.
op_add_i:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        glo ra
        sex r6
        add
        plo ra
        ghi ra
        adci 0
        ani $0F
        ori CHIP8_BASE
        phi ra
        lbr interpreter

; FX29: point I at the 5-byte font sprite for the low nibble of VX.
op_font:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        ldn r6
        ani $0F
        plo rc
        ldi 0
        plo re
        glo rc
        lbz font_offset_done
font_offset_loop:
        glo re
        adi 5
        plo re
        dec rc
        glo rc
        lbnz font_offset_loop
font_offset_done:
        glo re
        plo ra
        ldi CHIP8_BASE
        phi ra
        lbr interpreter

; FX33: store decimal hundreds, tens, and ones at I..I+2 without changing I.
op_bcd:
        glo rf
        ani $0F
        ori VREG_LOW
        plo r6
        ghi ra
        phi rd
        glo ra
        plo rd
        ldi 0
        phi rc
        plo rc
        ldn r6
bcd_hundreds:
        smi 100
        lbnf bcd_hundreds_done
        inc rc
        lbr bcd_hundreds
bcd_hundreds_done:
        adi 100
        plo re
        glo rc
        str rd
        inc rd
        ldi 0
        plo rc
        glo re
bcd_tens:
        smi 10
        lbnf bcd_tens_done
        inc rc
        lbr bcd_tens
bcd_tens_done:
        adi 10
        plo re
        glo rc
        str rd
        inc rd
        glo re
        str rd
        lbr interpreter

; FX55 / FX65 use original VIP behavior: transfer V0..VX and advance I by
; X+1. The dedicated RAM window means there is no Studio-specific remapping.
op_store_regs:
        glo rf
        ani $0F
        adi 1
        plo re
        ldi 0
        phi re
        ldi VREG_LOW
        plo r6
store_regs_loop:
        lda r6
        str ra
        inc ra
        dec re
        glo re
        lbnz store_regs_loop
        lbr interpreter

op_load_regs:
        glo rf
        ani $0F
        adi 1
        plo re
        ldi 0
        phi re
        ldi VREG_LOW
        plo r6
load_regs_loop:
        ldn ra
        str r6
        inc ra
        inc r6
        dec re
        glo re
        lbnz load_regs_loop
        lbr interpreter

unsupported:
        lbr unsupported


; Standard CHIP-8 4x5 hexadecimal font, copied to logical $000-$04F at reset.
font_data:
        .byte $F0,$90,$90,$90,$F0
        .byte $20,$60,$20,$20,$70
        .byte $F0,$10,$F0,$80,$F0
        .byte $F0,$10,$F0,$10,$F0
        .byte $90,$90,$F0,$10,$10
        .byte $F0,$80,$F0,$10,$F0
        .byte $F0,$80,$F0,$90,$F0
        .byte $F0,$10,$20,$40,$40
        .byte $F0,$90,$F0,$90,$F0
        .byte $F0,$90,$F0,$10,$F0
        .byte $F0,$90,$F0,$90,$90
        .byte $E0,$90,$E0,$90,$E0
        .byte $F0,$80,$80,$80,$F0
        .byte $E0,$90,$90,$90,$E0
        .byte $F0,$80,$F0,$80,$F0
        .byte $F0,$80,$F0,$80,$80

        .end
