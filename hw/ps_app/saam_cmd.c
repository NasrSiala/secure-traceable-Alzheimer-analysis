/* saam_cmd.c — bare-metal command loop for IF-14 / IF-15 / IF-16 (T4.12, 2/2).
 *
 * The UART bytes and the AXI registers are function pointers so a host test can
 * compile this file without Vitis. On the PS they are the Xilinx UART and the
 * two slaves at the addresses build.tcl assigns. This file was not linked into
 * a BOOT.bin: there is no bitstream and no board in this run.
 *
 * Frame: 0xA5 | cmd | len LE | payload | CRC-32 LE (IEEE), same as hw/host.
 * Commands: 0x01 INFO, 0x10 SHA256, 0x20 FIR. Response payload starts with 0.
 */

#include <stdint.h>
#include <stddef.h>

#define CMD_INFO 0x01u
#define CMD_SHA256 0x10u
#define CMD_FIR 0x20u
#define SYNC 0xA5u

#define SHA_CTRL 0x00u
#define SHA_STATUS 0x04u
#define SHA_DATA 0x08u
#define SHA_LAST 0x0Cu
#define SHA_DIGEST 0x10u
#define SHA_VERSION 0x30u
#define FIR_CTRL 0x00u
#define FIR_STATUS 0x04u
#define FIR_DATA_IN 0x08u
#define FIR_DATA_OUT 0x0Cu
#define FIR_COEF 0x10u

static uint32_t (*mmio_read)(uintptr_t base, uint32_t offset);
static void (*mmio_write)(uintptr_t base, uint32_t offset, uint32_t value);
static uintptr_t sha_base;
static uintptr_t fir_base;

static uint32_t crc_table[256];
static int crc_ready;

static void crc_init(void) {
  uint32_t i, bit, c;
  for (i = 0; i < 256; i++) {
    c = i;
    for (bit = 0; bit < 8; bit++) {
      c = (c & 1u) ? (0xEDB88320u ^ (c >> 1)) : (c >> 1);
    }
    crc_table[i] = c;
  }
  crc_ready = 1;
}

static uint32_t crc32_ieee(const uint8_t *data, size_t len) {
  uint32_t crc = 0xFFFFFFFFu;
  size_t i;
  if (!crc_ready) {
    crc_init();
  }
  for (i = 0; i < len; i++) {
    crc = crc_table[(crc ^ data[i]) & 0xFFu] ^ (crc >> 8);
  }
  return crc ^ 0xFFFFFFFFu;
}

static uint32_t rd_le(const uint8_t *p) {
  return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24);
}

static void wr_le(uint8_t *p, uint32_t value) {
  p[0] = (uint8_t)value;
  p[1] = (uint8_t)(value >> 8);
  p[2] = (uint8_t)(value >> 16);
  p[3] = (uint8_t)(value >> 24);
}

/* DIGEST0 is the first four hash bytes, with the first byte in bits 31..24. */
static void wr_be(uint8_t *p, uint32_t value) {
  p[0] = (uint8_t)(value >> 24);
  p[1] = (uint8_t)(value >> 16);
  p[2] = (uint8_t)(value >> 8);
  p[3] = (uint8_t)value;
}

void saam_bind(uintptr_t sha, uintptr_t fir,
               uint32_t (*rd)(uintptr_t, uint32_t),
               void (*wr)(uintptr_t, uint32_t, uint32_t)) {
  sha_base = sha;
  fir_base = fir;
  mmio_read = rd;
  mmio_write = wr;
}

/* Hash one message already split into big-endian words. last_n is 1..4, or 0
 * for the empty message (nwords must be 0). Returns 0. */
int saam_sha256(const uint32_t *words, size_t nwords, unsigned last_n, uint8_t out[32]) {
  size_t i;
  unsigned d;
  mmio_write(sha_base, SHA_CTRL, 0x1u);
  if (nwords == 0) {
    mmio_write(sha_base, SHA_LAST, 0);
    mmio_write(sha_base, SHA_CTRL, 0x2u);
  } else {
    for (i = 0; i + 1 < nwords; i++) {
      mmio_write(sha_base, SHA_DATA, words[i]);
    }
    mmio_write(sha_base, SHA_LAST, last_n);
    mmio_write(sha_base, SHA_CTRL, 0x2u);
    if (last_n != 0) {
      mmio_write(sha_base, SHA_DATA, words[nwords - 1]);
    }
  }
  while ((mmio_read(sha_base, SHA_STATUS) & 0x4u) == 0) {
  }
  for (d = 0; d < 8; d++) {
    wr_be(out + 4u * d, mmio_read(sha_base, SHA_DIGEST + 4u * d));
  }
  return 0;
}

size_t saam_frame(uint8_t command, const uint8_t *payload, size_t len, uint8_t *out) {
  size_t i;
  uint32_t sum;
  out[0] = SYNC;
  out[1] = command;
  wr_le(out + 2, (uint32_t)len);
  for (i = 0; i < len; i++) {
    out[6 + i] = payload[i];
  }
  sum = crc32_ieee(out, 6 + len);
  wr_le(out + 6 + len, sum);
  return 10 + len;
}

uint32_t saam_crc32(const uint8_t *data, size_t len) { return crc32_ieee(data, len); }

uint32_t saam_version(void) { return mmio_read(sha_base, SHA_VERSION); }
uint32_t saam_coef_id(void) { return mmio_read(fir_base, FIR_COEF); }

static uint32_t word_be(const uint8_t *data, unsigned nbytes) {
  uint32_t word = 0;
  unsigned i;
  for (i = 0; i < nbytes; i++) {
    word |= (uint32_t)data[i] << (8u * (3u - i));
  }
  return word;
}

static void sha_read_digest(uint8_t out[32]) {
  unsigned d;
  for (d = 0; d < 8; d++) {
    wr_be(out + 4u * d, mmio_read(sha_base, SHA_DIGEST + 4u * d));
  }
}

/* Hash the raw message. A multiple of 4 bytes uses last_n 4, never 0: 0 is the
 * empty message and would start a second, empty beat. */
static int sha_bytes(const uint8_t *msg, size_t len, uint8_t out[32]) {
  size_t nwords;
  size_t i;
  unsigned last_n;
  mmio_write(sha_base, SHA_CTRL, 0x1u);
  if (len == 0) {
    mmio_write(sha_base, SHA_LAST, 0);
    mmio_write(sha_base, SHA_CTRL, 0x2u);
  } else {
    last_n = (unsigned)(len % 4u);
    if (last_n == 0u) {
      last_n = 4u;
    }
    nwords = (len + 3u) / 4u;
    for (i = 0; i + 1u < nwords; i++) {
      mmio_write(sha_base, SHA_DATA, word_be(msg + 4u * i, 4u));
    }
    mmio_write(sha_base, SHA_LAST, last_n);
    mmio_write(sha_base, SHA_CTRL, 0x2u);
    mmio_write(sha_base, SHA_DATA, word_be(msg + 4u * (nwords - 1u), last_n));
  }
  while ((mmio_read(sha_base, SHA_STATUS) & 0x4u) == 0) {
  }
  sha_read_digest(out);
  return 0;
}

static void wr_le16(uint8_t *p, int16_t value) {
  uint16_t bits = (uint16_t)value;
  p[0] = (uint8_t)bits;
  p[1] = (uint8_t)(bits >> 8);
}

static int16_t rd_le16(const uint8_t *p) {
  return (int16_t)((uint16_t)p[0] | ((uint16_t)p[1] << 8));
}

/* Push one int16. The slave accepts the write only while IN_READY is 1, then
 * spends 111 MAC cycles and a rounding cycle before a producing sample raises
 * OUT_VALID. OUT_VALID stays 1, and IN_READY stays 0, until DATA_OUT is read.
 * One status read immediately after the write sees neither bit and the next
 * write waits forever, so this polls until one of them is set. */
int saam_fir_push(int16_t sample, int16_t *produced_sample, int *produced) {
  uint32_t status;
  uint32_t word;
  *produced = 0;
  mmio_write(fir_base, FIR_DATA_IN, (uint32_t)(uint16_t)sample);
  for (;;) {
    status = mmio_read(fir_base, FIR_STATUS);
    if ((status & 0x2u) != 0) {
      word = mmio_read(fir_base, FIR_DATA_OUT);
      *produced_sample = (int16_t)(word & 0xFFFFu);
      *produced = 1;
      return 0;
    }
    if ((status & 0x1u) != 0) {
      return 0;
    }
  }
}

void saam_fir_clear(void) { mmio_write(fir_base, FIR_CTRL, 0x1u); }

/* Returns 0 and writes a response frame, or -1 when the frame is not usable
 * (short, bad sync, bad CRC, odd FIR payload, or response_cap too small).
 * -2 is a command this loop does not implement. The caller retries on -1;
 * this function does not count retries. */
int saam_dispatch(const uint8_t *frame, size_t frame_len, uint8_t *response,
                  size_t response_cap, size_t *response_len) {
  uint32_t length;
  uint32_t found;
  uint32_t expect;
  if (frame_len < 10 || frame[0] != SYNC) {
    return -1;
  }
  length = rd_le(frame + 2);
  if (frame_len != (size_t)length + 10u) {
    return -1;
  }
  found = rd_le(frame + 6 + length);
  expect = crc32_ieee(frame, 6 + length);
  if (found != expect) {
    return -1;
  }
  if (frame[1] == CMD_INFO && length == 0) {
    uint8_t body[9];
    if (response_cap < 19u) {
      return -1;
    }
    body[0] = 0;
    wr_le(body + 1, saam_version());
    wr_le(body + 5, saam_coef_id());
    *response_len = saam_frame(CMD_INFO, body, 9, response);
    return 0;
  }
  if (frame[1] == CMD_SHA256) {
    uint8_t body[33];
    if (response_cap < 43u) {
      return -1;
    }
    body[0] = 0;
    sha_bytes(length == 0 ? NULL : frame + 6, length, body + 1);
    *response_len = saam_frame(CMD_SHA256, body, 33, response);
    return 0;
  }
  if (frame[1] == CMD_FIR) {
    size_t count;
    size_t i;
    size_t nout;
    size_t filled = 0;
    if ((length & 1u) != 0u) {
      return -1;
    }
    count = (size_t)length / 2u;
    nout = count == 0u ? 0u : (count - 1u) / 5u + 1u;
    if (response_cap < 11u + 2u * nout) {
      return -1;
    }
    response[0] = SYNC;
    response[1] = CMD_FIR;
    response[6] = 0;
    saam_fir_clear();
    for (i = 0; i < count; i++) {
      int produced = 0;
      int16_t value = 0;
      saam_fir_push(rd_le16(frame + 6u + 2u * i), &value, &produced);
      if (produced) {
        if (filled >= 2u * nout) {
          return -1;
        }
        wr_le16(response + 7u + filled, value);
        filled += 2u;
      }
    }
    wr_le(response + 2, (uint32_t)(1u + filled));
    wr_le(response + 7u + filled, crc32_ieee(response, 7u + filled));
    *response_len = 11u + filled;
    return 0;
  }
  return -2;
}
