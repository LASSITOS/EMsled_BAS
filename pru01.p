//
// PRU01.p is responsible for reading the ADC data, and putting it on a 
// shared bus that PRU00.p can read.  PRU00.p then copies this data to the 
// Beaglebone main memory so that the ARM processor can read it.



//
// This source code is available under the "Simplified BSD license".
//
// Copyright (c) 2013, J. Kleiner
// All rights reserved.
//
// Redistribution and use in source and binary forms, with or without 
// modification, are permitted provided that the following conditions are met:
//
// 1. Redistributions of source code must retain the above copyright notice, 
//    this list of conditions and the following disclaimer.
//
// 2. Redistributions in binary form must reproduce the above copyright 
//    notice, this list of conditions and the following disclaimer in the 
//    documentation and/or other materials provided with the distribution.
//
// 3. Neither the name of the original author nor the names of its contributors 
//    may be used to endorse or promote products derived from this software 
//    without specific prior written permission.
//
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS 
// "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT 
// LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
// A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT 
// HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, 
// SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED 
// TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, 
// OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY 
// OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT 
// (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE 
// OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
//
//

.setcallreg r29.w0

.origin 0
.entrypoint MAIN1

#include "pru.hp"
#include "pructl.h"

//-----------------------------------------------------------------------------
MAIN1:
    // Enable OCP master port
    LBCO      r0, CONST_PRUCFG, 4, 4
    CLR       r0, r0, 4  // Clear SYSCFG[STANDBY_INIT] to enable OCP master port
    SBCO      r0, CONST_PRUCFG, 4, 4

//   
//   SRAM
//           +-- rHeadPtr       +--- rHeadPtrPtr
//           |                  |  + -- rSpinPtr
//           |                  |  |
//           |                  |  |
//           V                  V  V
//   +-------------------------+-----------------------+  
//   |                         |                       |
//   +-------------------------+-----------------------+  
//    <---- rHeadMask -------->
//

#define rHeadPtr     r3
    MOV       rHeadPtr,     (0x2000)

#define rHeadMask    r4
    MOV       rHeadMask,    0x2fff

#define rHeadPtrPtr  r5
    MOV       rHeadPtrPtr,  (0x2000 + PRU0_OFFSET_SRAM_HEAD)  // 0x3000

#define rSpinPtr     r6
    MOV       rSpinPtr,     (0x2000 + PRU0_OFFSET_SPIN_COUNT)   // 0x3008

#define rStopPtr     r8
    MOV       rStopPtr,     (0x2000 + PRU0_OFFSET_RES1)

#define rBits     r7
    MOV rBits, 24

#define rSamp0       r9
    MOV        rSamp0, 0x00
#define rSamp1       r10
    MOV        rSamp0, 0x01
#define rSamp2       r11
    MOV        rSamp0, 0x01
#define rSampMask    r12
    MOV        rSampMask, 0xffffff
#define channels     r14 

MOV r13, 0x00000000
MOV rSamp0, 0x00000000

loop_label:

	MOV channels, 4 
	// Need to wait at this point until it is ready to take a sample
	MOV r15,3 
	MOV r30.b0, 0x02
	CLKH:	
		SUB r15, r15, 1
		QBNE CLKH, r15, 1
	MOV r30.b0, 0x00
	CLKL:
		SUB r15, r15, 1
		QBNE CLKL, r15, 0
	QBBS loop_label, r31.t5 // data is ready!

	CHANNEL_LOOP:
					
		MOV rSamp0, 0x00000000
		MOV rBits, 24 // going to write/read 24 bits (3 bytes) 96 for 4 samples
	
	SPICLK_BIT:                     // loop for each of the 24 bits
		MOV r15, 3
		MOV r30.b0, 0x03 // 0x03

		CLKH2:	
			SUB r15, r15, 1
			QBNE CLKH2, r15, 1
		MOV r30.b0, 0x00
		CLKL2:
			SUB r15, r15, 1
			QBNE CLKL2, r15, 0
		QBBC SPICLK_BIT, r31.t5 // data is ready!

		// This is the 24 bit SPI loop 
		SUB rBits, rBits, 1        // count down through the bits
		LSL rSamp0, rSamp0, 1
		QBBC DATAINLOW, r31.t6
			OR rSamp0, rSamp0, 0x00000001
			QBA NEXT
		DATAINLOW:
			OR rSamp0, rSamp0, 0x00000000
			QBA NEXT
			
		NEXT:
		QBNE SPICLK_BIT, rBits, 0
		

    LSL rSamp0, rSamp0, 8   //Make the 24 data a 32 bit signed integer

		// Store sample at head and advance head
		ST32      rSamp0, rHeadPtr               // 2
		MOV r30.b0, 0x00
		ADD       rHeadPtr, rHeadPtr, 4          // 1
		AND       rHeadPtr, rHeadPtr, rHeadMask  // 1
		
	 	SUB channels, channels, 1
	    // Update sram with new head
    ST32      rHeadPtr, rHeadPtrPtr          // 2

	QBNE CHANNEL_LOOP, channels, 0


    // Goto top of main loop
  LD32  r15, rStopPtr
  QBEQ  loop_label, r15, 0x0                     // 1
HALT
