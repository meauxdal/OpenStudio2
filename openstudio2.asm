; SPDX-License-Identifier: MIT
;
; OpenStudio2 firmware -- independently written RCA Studio II firmware.

RAM_PAGE       = $08
VIDEO_PAGE     = $09
STACK_LOW      = $BF
VARIABLES_LOW  = $C0
TIMER_LOW      = $CD
TIMER_END      = $D0

        .org $0000

reset:
        ldi 0
        phi rb
        plo rb

        ldi irq >> 8
        phi r1
        ldi irq & $FF
        plo r1

        ldi RAM_PAGE
        phi r2
        phi r6
        phi r7
        phi r8
        ldi STACK_LOW
        plo r2

        ldi interpreter_entry >> 8
        phi r4
        ldi interpreter_entry & $FF
        plo r4

        ldi $04
        phi r5
        ldi 0
        plo r5

; Clear both physical RAM pages before video starts.
        ldi RAM_PAGE
        phi ra
        ldi 0
        plo ra
clear_ram:
        ldi 0
        str ra
        inc ra
        ghi ra
        xri $0A
        bnz clear_ram

; Preserve the documented initial sprite metadata used by Studio software.
        ldi $D2
        plo r8
        ldi $F8
        str r8
        inc r8
        inc r8
        ldi $15
        str r8
        inc r8
        ldi $11
        str r8
        inc r8
        inc r8
        inc r8
        ldi $04
        str r8
        inc r8
        str r8
        inc r8
        ldi $01
        str r8
        inc r8
        ldi $02
        str r8
        inc r8
        ldi $05
        str r8
        inc r8
        str r8

; Switch away from P=0 before enabling the CDP1861. An immediate DMA request
; must not advance R0 while it is still the reset-program counter.
        sex r2
        sep r4

irq_return:
        ret

; The interrupt path deliberately preserves D, DF, X and P. R0, R8, R9 and
; RB.0 retain their original Studio II ABI roles.
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
        ldi TIMER_END
        plo r8
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
; Four bursts leave R0 at the next row. Save that base in D; one SEX keeps the
; following DEC/PLO rewind ahead of the next DMA request.
        glo r0
        sex r2
        bn1 video_rows

wait_display_end:
        dec r0
        plo r0
        b1 wait_display_end

; Decrement the three frame timers from $08CD through $08CF.
        ldi TIMER_LOW
        plo r8
timer_loop:
        ldn r8
        bz timer_next
        smi 1
        str r8
timer_next:
        inc r8
        glo r8
        xri TIMER_END
        bnz timer_loop

        ldi TIMER_LOW
        plo r8
        ldn r8
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
; INP 1 enables the CDP1861. The input byte is discarded on the stack.
        dec r2
        inp 1
        inc r2

; Fetch and dispatch one Studio bytecode instruction. R6 and R7 address the
; memory-backed Vx and Vy registers at $08C0-$08CF. Native calls are handled
; before R3 becomes the bytecode handler PC.
interpreter:
        lda r5
        plo rf
        ani $F0
        bnz decode_operands
        glo rf
        ani $0F
        phi r3
        lda r5
        plo r3
        sep r3
        br interpreter

decode_operands:
        glo rf
        ani $0F
        ori VARIABLES_LOW
        plo r6
        ldn r5
        shr
        shr
        shr
        shr
        ori VARIABLES_LOW
        plo r7

        glo rf
        ani $F0
        shr
        shr
        shr
        adi dispatch_table & $FF
        plo rc
        ldi dispatch_table >> 8
        phi rc
        lda rc
        phi r3
        ldn rc
        plo r3
        sep r3
        br interpreter

op_jump:
        lda r5
        plo r5
        glo rf
        ani $0F
        phi r5
        sep r4

op_call:
        lda r5
        plo re
        ghi r5
        dec r2
        str r2
        glo r5
        dec r2
        str r2
        glo rf
        ani $0F
        phi r5
        glo re
        plo r5
        sep r4

op_jnz:
        ldn r6
        lbz skip_operand
take_short_branch:
        ldn r5
        plo r5
        sep r4

op_jz:
        ldn r6
        lbz take_short_branch
skip_operand:
        inc r5
        sep r4

op_skip_imm:
        lda r5
        sex r6
        xor
        lbz instruction_done
skip_instruction:
        inc r5
        inc r5
instruction_done:
        sep r4

op_load_imm:
        lda r5
        str r6
        sep r4

op_add_imm:
        glo rf
        ani $0F
        lbz op_loop
        lda r5
        sex r6
        add
        str r6
        sep r4
op_loop:
        ldn r6
        smi 1
        lbz skip_operand
        str r6
        lbr take_short_branch

op_alu:
        lda r5
        ani $0F
        smi 1
        lbz alu_or
        smi 1
        lbz alu_and
        smi 1
        lbz alu_xor
        smi 1
        lbz alu_add
        smi 1
        lbz alu_sub
        smi 1
        lbz alu_shr
        smi 1
        lbz alu_reverse_sub
        smi 7
        lbz alu_shl
        lbr unsupported
alu_or:
        ldn r7
        sex r6
        or
        str r6
        lbr clear_carry
alu_and:
        ldn r7
        sex r6
        and
        str r6
        lbr clear_carry
alu_xor:
        ldn r7
        sex r6
        xor
        str r6
        lbr clear_carry
alu_add:
        ldn r7
        sex r6
        add
        str r6
        lbr save_carry
alu_sub:
        ldn r7
        sex r6
        sd
        str r6
        lbr save_carry
alu_reverse_sub:
        ldn r7
        sex r6
        sm
        str r6
        lbr save_carry
alu_shr:
        ldn r7
        shr
        str r6
        lbr save_carry
alu_shl:
        ldn r7
        shl
        str r6
        lbr save_carry
clear_carry:
        ldi 0
        lbr write_carry
save_carry:
        ldi 0
        shlc
write_carry:
        phi re
        ldi RAM_PAGE
        phi rd
        ldi $CB
        plo rd
        ghi re
        str rd
        sep r4

op_memory:
        lda r5
        ani $0F
        lbz memory_compare
        smi 1
        lbz memory_copy
        smi 1
        lbz memory_read
        smi 2
        lbz memory_write
        smi 4
        lbz memory_bcd
        lbr unsupported
memory_compare:
        ldn r6
        sex r7
        xor
        lbz instruction_done
        lbr skip_instruction
memory_copy:
        ldn r6
        str r7
        sep r4
memory_pointer:
        ldi RAM_PAGE
        phi rd
        ldn r7
        plo rd
        sep rc
memory_read:
        ldi memory_read_back & $FF
        plo rc
        ldi memory_read_back >> 8
        phi rc
        lbr memory_pointer
memory_read_back:
        ldn rd
        str r6
        sep r4
memory_write:
        ldi RAM_PAGE
        phi rd
        ldn r7
        plo rd
        ldn r6
        str rd
        sep r4
memory_bcd:
        ldn r6
        phi rf
        ldi RAM_PAGE
        phi rd
        ldn r7
        plo rd
        ldi bcd_powers >> 8
        phi re
        ldi bcd_powers & $FF
        plo re
bcd_digit:
        ldi 0
        str rd
bcd_subtract:
        ghi rf
        sex re
        sm
        lbnf bcd_next
        phi rf
        ldn rd
        adi 1
        str rd
        lbr bcd_subtract
bcd_next:
        inc rd
        inc re
        glo re
        xri (bcd_powers + 3) & $FF
        lbnz bcd_digit
        glo rd
        smi 1
        str r7
        sep r4
bcd_powers:
        .byte 100,10,1

op_index:
        lda r5
        plo ra
        glo rf
        ani $0F
        phi ra
        sep r4

op_store_indexed:
        lda r5
        str ra
        glo rf
        ani $0F
        phi re
        dec r2
        sex r2
        ghi re
        str r2
        glo ra
        add
        plo ra
        inc r2
        sep r4

op_return_random:
        glo rf
        ani $0F
        lbnz op_random
        lda r2
        plo r5
        lda r2
        phi r5
        sep r4
op_random:
        lda r5
        str r6
        inc r9
        glo r9
        shr
        lbnf random_ready
        xri $B8
random_ready:
        plo r9
        glo r9
        sex r6
        and
        str r6
        sep r4

op_key:
        ldi RAM_PAGE
        phi rd
        glo rf
        ani $0F
        plo re
        xri $0F
        bnz key_number_ready
        ldi $CB
        plo rd
        ldn rd
        plo re
key_number_ready:
        dec r2
        glo re
        str r2
        out 2
        ldi $CA
        plo rd
        ldn rd
        bz key_player_two
        b3 key_pressed
key_not_pressed:
        inc r5
        sep r4
key_player_two:
        bn4 key_not_pressed
key_pressed:
        ldi $CB
        plo rd
        glo re
        str rd
        lbr take_short_branch

op_graphics:
        br graphics_decode

op_extended:
        lda r5
        smi $A6
        lbz ext_read
        smi 3
        lbz ext_write
        smi 3
        lbz ext_read_inc
        smi 3
        lbz ext_write_inc
        smi 4
        lbz ext_index_low
        smi 3
        lbz ext_index_or
        smi $3C
        lbz ext_clear_page
        br unsupported
ext_read:
        ldn ra
        str r6
        sep r4
ext_write:
        ldn r6
        str ra
        sep r4
ext_read_inc:
        lda ra
        str r6
        sep r4
ext_write_inc:
        ldn r6
        str ra
        inc ra
        sep r4
ext_index_low:
        ldn r6
        plo ra
        sep r4
ext_index_or:
        ldn r6
        ani $0F
        str r6
        sex r6
        glo ra
        or
        plo ra
        sep r4
ext_clear_page:
        ldi 0
        str ra
        glo ra
        dec ra
        lbnz ext_clear_page
        sep r4

unsupported:
        br unsupported

; Opcode E uses eight independently shifted 16-byte pattern buffers. The
; selected buffer is V9, with its display parameters in $08D0-$08F7.
graphics_decode:
        glo rf
        ani $0F
        phi rf

        ldi RAM_PAGE
        phi r6
        phi r7
        phi rd
        phi re
        ldi $C9
        plo r7
        ldn r7
        ani 7
        plo r7
        shl
        shl
        shl
        shl
        plo r6
        glo r7
        adi $D0
        plo r7
        glo r7
        adi 8
        plo rd
        glo r7
        adi $10
        plo re

        ghi rf
        bz graphics_clear
        smi 1
        bz graphics_move_stored
        smi 1
        bz graphics_move_variable
        smi 2
        bz graphics_load
        smi 4
        lbz graphics_draw
        br unsupported

graphics_clear:
        ldi $10
        plo re
graphics_clear_byte:
        ldi 0
        str r6
        inc r6
        dec re
        glo re
        bnz graphics_clear_byte
        sep r4

graphics_load:
        ldn rd
        ani $0F
        plo re
        bz graphics_done
graphics_load_row:
        lda ra
        sex r6
        xor
        str r6
        inc r6
        inc r6
        dec re
        glo re
        bnz graphics_load_row
graphics_done:
        sep r4

graphics_move_stored:
        ldn re
        br graphics_move
graphics_move_variable:
        ldi RAM_PAGE
        phi rc
        ldi $CC
        plo rc
        ldn rc
graphics_move:
        phi rc
        smi 2
        lbz graphics_move_up
        smi 2
        lbz graphics_move_left
        smi 2
        lbz graphics_move_right
        smi 2
        lbz graphics_move_down
        lbr skip_instruction

graphics_move_up:
        ldn r7
        smi 8
        str r7
        br graphics_count_vertical
graphics_move_down:
        ldn r7
        adi 8
        str r7
graphics_count_vertical:
        glo r7
        adi $18
        plo re
        ldn re
        smi 1
        str re
        sep r4

graphics_move_right:
        ldi 0
        phi rc
        ldn rd
        ani $0F
        plo re
        bz graphics_count_horizontal
graphics_shift_right_row:
        ldn r6
        shr
        str r6
        inc r6
        ldn r6
        shrc
        str r6
        inc r6
        ldn rd
        ani $80
        bnz graphics_right_edge_y
        dec r6
        ldn r6
        ani $80
        inc r6
        bz graphics_right_no_cross
        br graphics_right_cross
graphics_right_edge_y:
        bnf graphics_right_no_cross
graphics_right_cross:
        ldi 1
        phi rc
graphics_right_no_cross:
        dec re
        glo re
        bnz graphics_shift_right_row
        ghi rc
        bz graphics_count_horizontal
        ldn rd
        xri $80
        str rd
        ldn r7
        adi 1
        str r7
        br graphics_count_horizontal

graphics_move_left:
        ldi 0
        phi rc
        ldn rd
        ani $0F
        plo re
        bz graphics_count_horizontal
graphics_shift_left_row:
        ldn r6
        shl
        str r6
        inc r6
        ldn r6
        shlc
        str r6
        inc r6
        ldn rd
        ani $80
        bnz graphics_left_edge_x
        bnf graphics_left_no_cross
        br graphics_left_cross
graphics_left_edge_x:
        dec r6
        ldn r6
        ani 1
        inc r6
        bz graphics_left_no_cross
graphics_left_cross:
        ldi 1
        phi rc
graphics_left_no_cross:
        dec re
        glo re
        bnz graphics_shift_left_row
        ghi rc
        bz graphics_count_horizontal
        ldn rd
        xri $80
        str rd
        ldn r7
        smi 1
        str r7
graphics_count_horizontal:
        glo r7
        adi $20
        plo re
        ldn re
        smi 1
        str re
        sep r4

graphics_draw:
        ldn rd
        ani $0F
        plo re
        ldi 0
        phi re
        ldi VIDEO_PAGE
        phi rf
        ldn r7
        plo rf
; The dispatcher leaves RC on page 3, where the draw helper also resides.
        ldi graphics_xor_byte & $FF
        plo rc
        sex rf
        glo re
        bz graphics_draw_done
        ldn rd
        ani $80
        bnz graphics_draw_reversed
graphics_draw_row:
        sep rc
        inc r6
        dec rf
        sep rc
        inc r6
        glo rf
        adi 9
        plo rf
        dec re
        glo re
        bnz graphics_draw_row
        br graphics_draw_done

graphics_draw_reversed:
        inc r6
graphics_draw_reversed_row:
        sep rc
        dec r6
        dec rf
        sep rc
        inc r6
        inc r6
        glo rf
        adi 9
        plo rf
        dec re
        glo re
        bnz graphics_draw_reversed_row
graphics_draw_done:
        ghi re
        lbnz take_short_branch
        inc r5
        sep r4

graphics_xor_byte:
        ldn r6
        and
        bz graphics_xor_clear
        ldi 1
        phi re
graphics_xor_clear:
        ldn r6
        xor
        str rf
        sep r3
        br graphics_xor_byte

        .org $03E0
dispatch_table:
        .byte unsupported >> 8, unsupported & $FF
        .byte op_jump >> 8, op_jump & $FF
        .byte op_call >> 8, op_call & $FF
        .byte op_jnz >> 8, op_jnz & $FF
        .byte op_jz >> 8, op_jz & $FF
        .byte op_skip_imm >> 8, op_skip_imm & $FF
        .byte op_load_imm >> 8, op_load_imm & $FF
        .byte op_add_imm >> 8, op_add_imm & $FF
        .byte op_alu >> 8, op_alu & $FF
        .byte op_memory >> 8, op_memory & $FF
        .byte op_index >> 8, op_index & $FF
        .byte op_store_indexed >> 8, op_store_indexed & $FF
        .byte op_return_random >> 8, op_return_random & $FF
        .byte op_key >> 8, op_key & $FF
        .byte op_graphics >> 8, op_graphics & $FF
        .byte op_extended >> 8, op_extended & $FF

        .org $0400

; With no cartridge loaded, enter an original machine-code splash program.
        .byte splash >> 8, splash & $FF

        .org $0410
splash:
        ldi VIDEO_PAGE
        phi rd
        ldi $62
        plo rd
        ldi splash_data >> 8
        phi rf
        ldi splash_data & $FF
        plo rf
        ldi 7
        plo re
splash_row:
        ldi 4
        plo rc
splash_column:
        lda rf
        str rd
        inc rd
        glo rc
        smi 1
        plo rc
        bnz splash_column
        glo rd
        adi 4
        plo rd
        glo re
        smi 1
        plo re
        bnz splash_row
splash_idle:
        br splash_idle

splash_data:
        .byte $7C,$7C,$7C,$66
        .byte $66,$66,$66,$66
        .byte $66,$66,$60,$76
        .byte $66,$7C,$78,$7E
        .byte $66,$60,$60,$6E
        .byte $66,$60,$60,$66
        .byte $7C,$60,$7E,$66

        .end
