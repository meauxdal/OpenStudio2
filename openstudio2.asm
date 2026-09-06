; SPDX-License-Identifier: MIT
;
; OpenStudio2 -- independently written CHIP-8 firmware for RCA Studio II.
;
; Initial CHIP-8 bring-up version.  Native Studio II bytecode compatibility is
; intentionally not provided.  CHIP-8 program bytes are expected to be loaded
; by the MiSTer core using this mapping:
;
;   CHIP-8 $0200-$06FF -> Studio II $0300-$07FF
;   CHIP-8 $0700-$0AFF -> Studio II $0C00-$0FFF
;
; The firmware itself must remain below $0300.

RAM_PAGE       = $08
VIDEO_PAGE     = $09
VREG_LOW       = $A0
I_HIGH_LOW     = $B0        ; reserved for later memory-backed I if required
DELAY_LOW      = $B2
SOUND_LOW      = $B3
SP_LOW         = $B4
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
        ldi $03
        phi r5
        ldi 0
        plo r5

; RA holds the logical 12-bit CHIP-8 I register.
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
; RA   = logical CHIP-8 I
;
; Initial instruction subset:
;   00E0  00EE  1NNN  2NNN  3XNN  4XNN  5XY0
;   6XNN  7XNN  9XY0  ANNN
;
; Unsupported instructions intentionally trap at `unsupported`.

interpreter:
        lda r5
        plo rf

; Sequential CHIP-8 address $06FF->$0700 is physical $07FF->$0C00.
        ghi r5
        xri $08
        bnz fetch_second
        glo r5
        bnz fetch_second
        ldi $0C
        phi r5
fetch_second:
        lda r5
        plo re

        ghi r5
        xri $08
        bnz decode
        glo r5
        bnz decode
        ldi $0C
        phi r5

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
        xri $90
        lbz op_skip_ne_reg

        glo rf
        ani $F0
        xri $A0
        lbz op_set_i

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

; Convert NNN in RF.0/RE.0 from the CHIP-8 logical view into the physical
; Studio II program layout.  Targets below $0700 use +$0100; targets at/above
; $0700 use +$0500.  This initial build assumes executable targets are within
; the loaded CHIP-8 program range $0200-$0AFF.
set_pc_nnn:
        glo rf
        ani $0F
        smi 7
        bdf set_pc_upper
        glo rf
        ani $0F
        adi 1
        phi r5
        glo re
        plo r5
        lbr interpreter
set_pc_upper:
        glo rf
        ani $0F
        adi 5
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

; Advance the physical PC by one CHIP-8 instruction, respecting the split
; program mapping even if the skipped instruction straddles the boundary.
skip_next:
        inc r5
        ghi r5
        xri $08
        bnz skip_second_byte
        glo r5
        bnz skip_second_byte
        ldi $0C
        phi r5
skip_second_byte:
        inc r5
        ghi r5
        xri $08
        bnz skip_done
        glo r5
        bnz skip_done
        ldi $0C
        phi r5
skip_done:
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

; ANNN ----------------------------------------------------------------------
op_set_i:
        glo rf
        ani $0F
        phi ra
        glo re
        plo ra
        lbr interpreter

unsupported:
        br unsupported

        .end
