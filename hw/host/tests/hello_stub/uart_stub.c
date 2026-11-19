/*
 * uart_stub.c: the hardware under hw/ps_app/bringup/hello.c, for a build on the host (AUD-117).
 *
 * hello.c is compiled unchanged, with the stub headers of this directory, and linked with this file:
 * the UART is stdin (bytes received) and stdout (bytes sent), the register of the bring-up design is
 * a variable, and everything the application does to the hardware is written on stderr, one line
 * each:
 *
 *   BAUD <n>             XUartPs_SetBaudRate
 *   TXEMPTY              XUartPs_IsTransmitEmpty (always true here: the FIFO is empty)
 *   TXACTIVE <0|1>       XUartPs_IsTransmitActive (the last character is still in the shifter for
 *                        the first two calls, as on the UART, then it is out)
 *   OUT32 <addr> <hex>   Xil_Out32
 *   IN32 <addr>          Xil_In32
 *
 * An access outside the one register stops the program (exit 3). The program ends quietly (exit 0)
 * when stdin ends.
 *
 * This proves the logic of the console (parsing, limits, replies, order of the calls). It proves
 * nothing about the UART, the PL or the board: that is the board run of T1.9.
 */

#include <stdio.h>
#include <stdlib.h>

#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#endif

#include "xil_io.h"
#include "xparameters.h"
#include "xuartps.h"

#define REGISTER_ADDRESS 0x43C00000UL

static XUartPs_Config config;
static u32 reg_value;

XUartPs_Config *XUartPs_LookupConfig(u32 id_or_base)
{
    (void)id_or_base;
#ifdef _WIN32
    /* No translation of LF: the console speaks bytes. */
    (void)_setmode(_fileno(stdin), _O_BINARY);
    (void)_setmode(_fileno(stdout), _O_BINARY);
#endif
    /* A byte sent is on the pipe at once, as on a UART: the host side waits for it. */
    (void)setvbuf(stdout, NULL, _IONBF, 0);
    config.BaseAddress = XPAR_XUARTPS_0_BASEADDR;
    return &config;
}

s32 XUartPs_CfgInitialize(XUartPs *instance, XUartPs_Config *cfg, u32 base)
{
    (void)base;
    instance->Config = *cfg;
    return XST_SUCCESS;
}

void XUartPs_SetOperMode(XUartPs *instance, u8 mode)
{
    (void)instance;
    (void)mode;
}

s32 XUartPs_SetBaudRate(XUartPs *instance, u32 baud)
{
    (void)instance;
    fprintf(stderr, "BAUD %u\n", baud);
    return XST_SUCCESS;
}

void XUartPs_SendByte(u32 base, u8 data)
{
    (void)base;
    (void)putchar(data);
}

u8 XUartPs_RecvByte(u32 base)
{
    int c;

    (void)base;
    c = getchar();
    if (c == EOF) {
        (void)fflush(stdout);
        exit(0);
    }
    return (u8)c;
}

u32 XUartPs_IsTransmitEmpty(XUartPs *instance)
{
    (void)instance;
    fprintf(stderr, "TXEMPTY\n");
    return 1U;
}

u32 XUartPs_IsTransmitActive(u32 base)
{
    static unsigned int calls;
    u32 active;

    (void)base;
    active = (calls < 2U) ? 1U : 0U;
    calls++;
    fprintf(stderr, "TXACTIVE %u\n", active);
    return active;
}

void Xil_Out32(unsigned long address, u32 value)
{
    if (address != REGISTER_ADDRESS) {
        fprintf(stderr, "BADADDR %lx\n", address);
        exit(3);
    }
    reg_value = value;
    fprintf(stderr, "OUT32 %lx %08x\n", address, value);
}

u32 Xil_In32(unsigned long address)
{
    if (address != REGISTER_ADDRESS) {
        fprintf(stderr, "BADADDR %lx\n", address);
        exit(3);
    }
    fprintf(stderr, "IN32 %lx\n", address);
    return reg_value;
}
