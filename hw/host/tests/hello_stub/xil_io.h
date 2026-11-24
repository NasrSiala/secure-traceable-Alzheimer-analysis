/* Host stand-in for xil_io.h: the register of the bring-up design, served by uart_stub.c. */
#ifndef HELLO_STUB_XIL_IO_H
#define HELLO_STUB_XIL_IO_H

#include "xil_types.h"

void Xil_Out32(unsigned long address, u32 value);
u32 Xil_In32(unsigned long address);

#endif
