/*
 * hello.c: bring-up console of the Zybo Z7-10 (T1.9, l10-board-bringup).
 *
 * A throw-away application that proves three things from the PS, over the board's USB-UART
 * (PS UART1, MIO48/49):
 *   - the board boots from the SD card and the application runs ("hello");
 *   - the PL register of axil_reg_bringup answers over M_AXI_GP0 (write, read back);
 *   - the UART keeps its throughput at 115 200 and at 921 600 baud (echo of a block).
 *
 * It is not the application of the project (hw/ps_app/, T4.12) and not the framed protocol of
 * IF-14: the commands are lines of text, one per request, sent by hw/host/tests/test_bringup.py.
 *
 *   H              -> "hello SAAM-BRINGUP 1"
 *   W <hex>        -> "OK"            write the 32-bit register (1 to 8 hex digits)
 *   R              -> "R <8 hex>"     read the register back
 *   B <baud>       -> "B <baud>"      then switch to it (115200 or 921600 only)
 *   E <n>          -> "GO", then echoes the next n raw bytes (n <= 65536), then "DONE"
 *   anything else  -> "ERR"
 * Replies end with CR LF. A line ends with LF; CR is ignored.
 *
 * Builds with both generations of the UART driver of Vitis: by device id, and with SDT (system
 * device tree, by base address).
 */

#include "xil_io.h"
#include "xil_types.h"
#include "xparameters.h"
#include "xuartps.h"

/* Base address of axil_reg_bringup in the PS address map; hw/vivado/build.tcl assigns the same. */
#define BRINGUP_REG_BASE 0x43C00000UL

#define LINE_MAX_LEN 32U
#define ECHO_MAX_BYTES 65536UL
#define BAUD_LOW 115200U
#define BAUD_HIGH 921600U

static XUartPs uart;
static u32 uart_base;

static void put_char(char c)
{
    XUartPs_SendByte(uart_base, (u8)c);
}

static void put_text(const char *text)
{
    while (*text != '\0') {
        put_char(*text);
        text++;
    }
}

static void put_hex32(u32 value)
{
    static const char digits[] = "0123456789abcdef";
    int shift;

    for (shift = 28; shift >= 0; shift -= 4) {
        put_char(digits[(value >> (unsigned)shift) & 0xFU]);
    }
}

static void put_decimal(u32 value)
{
    char text[11];
    int length = 0;

    do {
        text[length] = (char)('0' + (value % 10U));
        length++;
        value /= 10U;
    } while (value != 0U);
    while (length > 0) {
        length--;
        put_char(text[length]);
    }
}

static void reply_end(void)
{
    put_text("\r\n");
}

/* A line without its LF. A line longer than the buffer is dropped and reported as too long. */
static int read_line(char *line, u32 size)
{
    u32 length = 0U;
    int too_long = 0;

    for (;;) {
        char c = (char)XUartPs_RecvByte(uart_base);

        if (c == '\n') {
            line[length] = '\0';
            return too_long ? -1 : (int)length;
        }
        if (c == '\r') {
            continue;
        }
        if (length < size - 1U) {
            line[length] = c;
            length++;
        } else {
            too_long = 1;
        }
    }
}

static int parse_hex(const char *text, u32 *value)
{
    u32 result = 0U;
    u32 digits = 0U;

    while (*text == ' ') {
        text++;
    }
    for (; *text != '\0'; text++) {
        u32 digit;

        if (*text >= '0' && *text <= '9') {
            digit = (u32)(*text - '0');
        } else if (*text >= 'a' && *text <= 'f') {
            digit = (u32)(*text - 'a') + 10U;
        } else if (*text >= 'A' && *text <= 'F') {
            digit = (u32)(*text - 'A') + 10U;
        } else {
            return 0;
        }
        result = (result << 4U) | digit;
        digits++;
        if (digits > 8U) {
            return 0;
        }
    }
    *value = result;
    return digits > 0U;
}

static int parse_decimal(const char *text, u32 *value)
{
    u32 result = 0U;
    u32 digits = 0U;

    while (*text == ' ') {
        text++;
    }
    for (; *text != '\0'; text++) {
        if (*text < '0' || *text > '9') {
            return 0;
        }
        result = (result * 10U) + (u32)(*text - '0');
        digits++;
        if (digits > 7U) {
            return 0;
        }
    }
    *value = result;
    return digits > 0U;
}

static void command_baud(const char *argument)
{
    u32 baud;

    if (!parse_decimal(argument, &baud) || (baud != BAUD_LOW && baud != BAUD_HIGH)) {
        put_text("ERR");
        reply_end();
        return;
    }
    put_text("B ");
    put_decimal(baud);
    reply_end();
    /* The answer leaves at the old rate, then the rate changes. An empty FIFO is not enough: the
     * last character is still in the shifter, and XUartPs_SetBaudRate disables the UART and resets
     * its transmitter at once, which would cut that character. Wait for the transmit state machine
     * to stop as well (XUartPs_IsTransmitActive, the TACTIVE bit of the status register). */
    while (!XUartPs_IsTransmitEmpty(&uart) || XUartPs_IsTransmitActive(uart_base)) {
    }
    (void)XUartPs_SetBaudRate(&uart, baud);
}

static void command_echo(const char *argument)
{
    u32 count;
    u32 index;

    if (!parse_decimal(argument, &count) || count > ECHO_MAX_BYTES) {
        put_text("ERR");
        reply_end();
        return;
    }
    put_text("GO");
    reply_end();
    for (index = 0U; index < count; index++) {
        put_char((char)XUartPs_RecvByte(uart_base));
    }
    put_text("\r\nDONE");
    reply_end();
}

static void command(const char *line)
{
    u32 value;

    switch (line[0]) {
    case 'H':
        put_text("hello SAAM-BRINGUP 1");
        reply_end();
        break;
    case 'W':
        if (parse_hex(&line[1], &value)) {
            Xil_Out32(BRINGUP_REG_BASE, value);
            put_text("OK");
        } else {
            put_text("ERR");
        }
        reply_end();
        break;
    case 'R':
        put_text("R ");
        put_hex32(Xil_In32(BRINGUP_REG_BASE));
        reply_end();
        break;
    case 'B':
        command_baud(&line[1]);
        break;
    case 'E':
        command_echo(&line[1]);
        break;
    default:
        put_text("ERR");
        reply_end();
        break;
    }
}

static int uart_start(void)
{
    XUartPs_Config *config;

#ifdef SDT
    config = XUartPs_LookupConfig(XPAR_XUARTPS_0_BASEADDR);
#else
    config = XUartPs_LookupConfig(XPAR_XUARTPS_0_DEVICE_ID);
#endif
    if (config == NULL) {
        return -1;
    }
    if (XUartPs_CfgInitialize(&uart, config, config->BaseAddress) != XST_SUCCESS) {
        return -1;
    }
    uart_base = config->BaseAddress;
    XUartPs_SetOperMode(&uart, XUARTPS_OPER_MODE_NORMAL);
    return XUartPs_SetBaudRate(&uart, BAUD_LOW) == XST_SUCCESS ? 0 : -1;
}

int main(void)
{
    char line[LINE_MAX_LEN];

    if (uart_start() != 0) {
        for (;;) {
        }
    }
    reply_end();
    put_text("hello SAAM-BRINGUP 1");
    reply_end();

    for (;;) {
        int length = read_line(line, LINE_MAX_LEN);

        if (length < 0) {
            put_text("ERR");
            reply_end();
        } else if (length > 0) {
            command(line);
        }
    }
}
