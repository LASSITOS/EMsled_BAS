// This routine is the assembly code for bit-banging an SPI port to talk to the AWG

.setcallreg r16.w0
.origin 0
.entrypoint START

#define PRU0_ARM_INTERRUPT 19

#define data r2
#define bits r9
#define delay r10
#define rSamp0       r13

/*
 * These values are from the "AM335x PRU-ICSS Reference Guide" (google it!)
 * Reading http://www.embedded-things.com/bbb/understanding-bbb-pru-shared-memory-access/ is enlightening
 */
#define CONST_PRUCFG         C4
#define CONST_PRUSHAREDRAM   C28
#define PRU0_CTRL            0x22000
#define PRU1_CTRL            0x24000
#define CTPPR0               0x28
#define OWN_RAM              0x000
#define OTHER_RAM            0x020
#define SHARED_RAM           0x100

START:    
    // We are on PRU1, so bit 6 of R30 controls P8_39
    SET r30.t6                          // Set P8_39 to High, Chip Select ON
    MOV rSamp0, 0x0000                  // Initialises the currently read sample to 0
    MOV r10, 0xFF000000                 // bit mask for getting the operation mode, comes from if(rx==0) at the beginning of Send data in the python code
    
    // Again, read http://www.embedded-things.com/bbb/understanding-bbb-pru-shared-memory-access/ 
    LBCO    r0, CONST_PRUCFG, 4, 4      // Enable OCP master port
    CLR     r0, r0, 4
    SBCO    r0, CONST_PRUCFG, 4, 4
    MOV     r0, SHARED_RAM + OTHER_RAM  // Set C28 to point to shared RAM
    MOV     r1, PRU1_CTRL + CTPPR0
    SBBO    r0, r1, 0, 4
    
    MOV  r0, 0                          // r0 will contain address 0 (beginning of the PRU shared memory)
    LBBO data, r0, 0, 4                 // Read the data at address 0 written by pypruss.pru_write_memory(1, 0, data)

    MOV bits, 0x00000000
    AND r1, data, r10                   // Applies the bit mask to get the mode (read or write)
    QBEQ WRITE, r1, 0                   // if r1 == 0 go to write mode 
    QBA READ                            // else go to label read
    
WRITE:
    MOV bits, 32                        // Initialises r9/bits to 32, the number of bits we want to write
    QBA SEND                            // Jumps to label SEND
    
READ:
    MOV bits, 16                        // Initialises r9/bits to 16, the number of bits we want to write (just a 16bit read command)

SEND:                                   // This routine is common to read and write mode and sends the instructions to the device

    loop_start:
        // prepare data out
        mov r13, data
        /**
         * Note on r13 here. After those 2 instructions, it will be copied to r30.b1
         * In r30.b1, the LSB is connected to P8_27 which his the SDIO port of the AWG, this is how we transfer commands & data bit by bit
         * The bit just on the left is P8_29, whic is the SCLK of the AWG, we flip it on and off by calling SCLK_CONTROL for each bit we send
        **/
        lsr r13, r13, 31                // r13 now conains the leftmost bit of the data variable, which is the bit we're going to transfer now
        MOV r30.b1, r13                 // send one bit (on P8_27)
        
        CALL SCLK_CONTROL
        
        SUB bits, bits, 1               // decrement the number of bits remaining to be sent
        lsl data, data, 1               // shift the data one bit on the right, ready for next loop
        QBNE loop_start, bits, 0        // Unless we have sent all the bits we wanted to send, loop back to the loop_start label

     QBNE READ2, r1, 0                  // If we're in read mode, read the result of the command
     QBA FINISH                         // Else we're done...
     
READ2:
    MOV bits, 16                        // Initialises r9/bits to 16, the number of bits we want to read
    MOV rSamp0, 0x00000000              // Intitalises our WORD
    SPICLK_BIT:                         // loop for each of the 24 bits
        LSL rSamp0, rSamp0, 1           // shift the data one bit to the left, making space for the next bit
        QBBC NEXT, r31.t10              // If we have HIGH on P8_28, the current bit is a 1
        OR rSamp0, rSamp0, 0x00000001
        NEXT:
        CALL SCLK_CONTROL
        SUB bits, bits, 1               // decrement the number of bits remaining to be received
        QBNE SPICLK_BIT, bits, 0        // If there are still bits to be read, keep going

FINISH:
    SET r30.t6                          // Set P8_39 to High, Chip Select OFF
    SBCO rSamp0, CONST_PRUSHAREDRAM, 0, 4    // Place sequence in local PRU 0 ram    
    MOV R31.b0, PRU0_ARM_INTERRUPT+16   // Send notification to Host for program completion
    HALT

/**
 * The BUSY_WAIT function uses and overwrites r10/delay as a working register
 * It expects the return address to be stored in r17.w0
 */
BUSY_WAIT:
    MOV delay, 34000
    delay_loop:                         // loop until delay == 0
        SUB delay, delay, 1
        QBNE delay_loop, delay, 0
    JMP r17.w0
    
/**
 * The SCLK_CONTROL function overwrites the second LSB of r30.b1 but leaves the other bits untouched, driving P8_29 HIGH and LOW
    It uses BUSY_WAIT twice, and thefore also overwrites r17.w0
 * It expects to be called with the CALL instruction (and therefore overwrites r16.w0)
 */
SCLK_CONTROL:
    OR r30.b1, r30.b1, 0x02             // Set P8_29 High
    JAL r17.w0, BUSY_WAIT               // Wait
    AND r30.b1, r30.b1, 0xFD            // Set it low again
    JAL r17.w0, BUSY_WAIT               // Wait some more
    RET
