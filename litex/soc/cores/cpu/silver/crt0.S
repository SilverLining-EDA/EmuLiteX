	.global _start
_start:
	j reset_vector

reset_vector:
	la sp, _fstack
	la t0, trap_vector
	csrw mtvec, t0

	// initialize .data
	la t0, _fdata
	la t1, _edata
	la t2, _fdata_rom
1:	beq t0, t1, 2f
	ld t3, 0(t2)
	sd t3, 0(t0)
	addi t0, t0, 8
	addi t2, t2, 8
	j 1b
2:

	// initialize .bss
	la t0, _fbss
	la t1, _ebss
1:	beq t0, t1, 3f
	sd zero, 0(t0)
	addi t0, t0, 8
	j 1b
3:
	call litex_startup_init
	call main
1:	j 1b

trap_vector:
	addi sp, sp, -16*8
	sd ra,  0*8(sp)
	sd t0,  1*8(sp)
	sd t1,  2*8(sp)
	sd t2,  3*8(sp)
	sd a0,  4*8(sp)
	sd a1,  5*8(sp)
	sd a2,  6*8(sp)
	sd a3,  7*8(sp)
	sd a4,  8*8(sp)
	sd a5,  9*8(sp)
	sd a6, 10*8(sp)
	sd a7, 11*8(sp)
	sd t3, 12*8(sp)
	sd t4, 13*8(sp)
	sd t5, 14*8(sp)
	sd t6, 15*8(sp)
	call isr
	ld ra,  0*8(sp)
	ld t0,  1*8(sp)
	ld t1,  2*8(sp)
	ld t2,  3*8(sp)
	ld a0,  4*8(sp)
	ld a1,  5*8(sp)
	ld a2,  6*8(sp)
	ld a3,  7*8(sp)
	ld a4,  8*8(sp)
	ld a5,  9*8(sp)
	ld a6, 10*8(sp)
	ld a7, 11*8(sp)
	ld t3, 12*8(sp)
	ld t4, 13*8(sp)
	ld t5, 14*8(sp)
	ld t6, 15*8(sp)
	addi sp, sp, 16*8
	mret
