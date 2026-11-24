/* Host stand-in for the UART driver (xuartps.h): only what hello.c calls. uart_stub.c implements it
 * on stdin and stdout and writes what the application does to the hardware on stderr. */
#ifndef HELLO_STUB_XUARTPS_H
#define HELLO_STUB_XUARTPS_H

#include "xil_types.h"

#define XUARTPS_OPER_MODE_NORMAL 0

typedef struct {
    u32 BaseAddress;
} XUartPs_Config;

typedef struct {
    XUartPs_Config Config;
} XUartPs;

XUartPs_Config *XUartPs_LookupConfig(u32 id_or_base);
s32 XUartPs_CfgInitialize(XUartPs *instance, XUartPs_Config *config, u32 base);
void XUartPs_SetOperMode(XUartPs *instance, u8 mode);
s32 XUartPs_SetBaudRate(XUartPs *instance, u32 baud);
void XUartPs_SendByte(u32 base, u8 data);
u8 XUartPs_RecvByte(u32 base);
u32 XUartPs_IsTransmitEmpty(XUartPs *instance);
u32 XUartPs_IsTransmitActive(u32 base);

#endif
