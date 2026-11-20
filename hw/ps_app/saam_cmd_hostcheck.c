/* Host check of the command loop. Not a board test and not a BOOT.bin.
 * The MMIO stub delays FIR status the way fir_axi does: OUT_VALID stays 0 for
 * several reads after DATA_IN, then stays 1 until DATA_OUT is read. A driver
 * that samples status once returns no sample and the next write is refused.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#define SHA_BASE 0u
#define FIR_BASE 0x1000u

void saam_bind(uintptr_t sha, uintptr_t fir,
               uint32_t (*rd)(uintptr_t, uint32_t),
               void (*wr)(uintptr_t, uint32_t, uint32_t));
size_t saam_frame(uint8_t command, const uint8_t *payload, size_t len, uint8_t *out);
uint32_t saam_crc32(const uint8_t *data, size_t len);
int saam_dispatch(const uint8_t *frame, size_t frame_len, uint8_t *response,
                  size_t response_cap, size_t *response_len);
int saam_sha256(const uint32_t *words, size_t nwords, unsigned last_n, uint8_t out[32]);
int saam_fir_push(int16_t sample, int16_t *produced_sample, int *produced);
void saam_fir_clear(void);

static uint32_t sha_reg[16];
static int sha_force_done;
static uint8_t sha_msg[16];
static size_t sha_len;
static unsigned sha_last;
static int sha_final;

static int fir_ready = 1;
static int fir_hold;
static int fir_delay;
static int fir_index;
static int fir_blocked;
static int fir_pending_produce;
static int fir_pending_index;
static int16_t fir_pending_sample;
static uint32_t fir_hold_word;

static const int16_t k_in[6] = {1000, 0, 0, 0, 0, -1000};
static const int16_t k_out[2] = {-1, 4};
static const uint8_t k_abc[32] = {
    0xba, 0x78, 0x16, 0xbf, 0x8f, 0x01, 0xcf, 0xea, 0x41, 0x41, 0x40, 0xde, 0x5d, 0xae, 0x22, 0x23,
    0xb0, 0x03, 0x61, 0xa3, 0x96, 0x17, 0x7a, 0x9c, 0xb4, 0x10, 0xff, 0x61, 0xf2, 0x00, 0x15, 0xad};

static void sha_install(void) {
  unsigned d;
  const uint8_t abc[3] = {'a', 'b', 'c'};
  const uint8_t *dig = NULL;
  if (sha_len == 3 && memcmp(sha_msg, abc, 3) == 0) {
    dig = k_abc;
  }
  for (d = 0; d < 8; d++) {
    uint32_t word = 0;
    if (dig != NULL) {
      word = ((uint32_t)dig[4u * d] << 24) | ((uint32_t)dig[4u * d + 1u] << 16) |
             ((uint32_t)dig[4u * d + 2u] << 8) | (uint32_t)dig[4u * d + 3u];
    }
    sha_reg[(0x10u / 4u) + d] = word;
  }
  sha_reg[0x04u / 4u] |= 0x4u;
}

static void sha_note(uint32_t offset, uint32_t value) {
  if (offset == 0x00u && (value & 0x1u) != 0) {
    sha_len = 0;
    sha_last = 0;
    sha_final = 0;
    sha_reg[0x04u / 4u] = 0;
  }
  if (offset == 0x0Cu) {
    sha_last = value;
  }
  if (offset == 0x00u && (value & 0x2u) != 0) {
    sha_final = 1;
    if (sha_last == 0 && sha_len == 0) {
      sha_install();
    }
  }
  if (offset == 0x08u) {
    unsigned n = sha_final ? sha_last : 4u;
    unsigned i;
    if (n > 4u) {
      n = 4u;
    }
    for (i = 0; i < n && sha_len < sizeof sha_msg; i++) {
      sha_msg[sha_len++] = (uint8_t)(value >> (8u * (3u - i)));
    }
    if (sha_final) {
      sha_install();
    }
  }
}

static void fir_reset(void) {
  fir_ready = 1;
  fir_hold = 0;
  fir_delay = 0;
  fir_index = 0;
  fir_pending_produce = 0;
}

static void fir_write(uint32_t offset, uint32_t value) {
  int16_t sample;
  if (offset == 0x00u && (value & 0x1u) != 0) {
    fir_reset();
    return;
  }
  if (offset != 0x08u) {
    return;
  }
  if (!fir_ready || fir_hold || fir_delay > 0) {
    fir_blocked++;
    return;
  }
  sample = (int16_t)(value & 0xFFFFu);
  fir_pending_produce = (fir_index % 5) == 0;
  fir_pending_index = fir_index;
  fir_pending_sample = sample;
  fir_index++;
  fir_ready = 0;
  fir_delay = 4;
}

static uint32_t fir_read(uint32_t offset) {
  if (offset == 0x04u) {
    if (fir_delay > 0) {
      fir_delay--;
      if (fir_delay == 0) {
        if (fir_pending_produce) {
          int which = fir_pending_index / 5;
          int16_t outv = 0x7FFF;
          if (fir_pending_index < 6 && fir_pending_sample == k_in[fir_pending_index] && which < 2) {
            outv = k_out[which];
          }
          fir_hold = 1;
          fir_hold_word = (uint32_t)(uint16_t)outv;
          fir_ready = 0;
        } else {
          fir_ready = 1;
        }
      }
    }
    return (fir_ready ? 0x1u : 0u) | (fir_hold ? 0x2u : 0u);
  }
  if (offset == 0x0Cu) {
    uint32_t word = 0;
    if (fir_hold) {
      word = fir_hold_word;
      fir_hold = 0;
      fir_ready = 1;
    }
    return word;
  }
  if (offset == 0x10u) {
    return 0xCA0E824Cu;
  }
  return 0;
}

static uint32_t rd(uintptr_t base, uint32_t offset) {
  if (base == FIR_BASE) {
    return fir_read(offset);
  }
  if (offset == 0x04u && sha_force_done) {
    return sha_reg[offset / 4u] | 0x4u;
  }
  return sha_reg[offset / 4u];
}

static void wr(uintptr_t base, uint32_t offset, uint32_t value) {
  if (base == FIR_BASE) {
    fir_write(offset, value);
    return;
  }
  if (offset / 4u < 16u) {
    sha_reg[offset / 4u] = value;
  }
  if (!sha_force_done) {
    sha_note(offset, value);
  }
}

static int expect_digest(const uint8_t *got) {
  return memcmp(got, k_abc, 32) == 0;
}

int main(void) {
  uint8_t frame[64];
  uint8_t response[64];
  uint8_t samples[12];
  size_t n;
  size_t response_len = 0;
  uint32_t sum;
  int produced = 0;
  int16_t value = 0;
  unsigned i;
  saam_bind(SHA_BASE, FIR_BASE, rd, wr);
  sha_reg[0x30u / 4u] = 0x01020304u;
  n = saam_frame(0x01, NULL, 0, frame);
  if (saam_dispatch(frame, n, response, sizeof response, &response_len) != 0) {
    return 1;
  }
  if (response[6] != 0 || response[7] != 0x04 || response[14] != 0xCA) {
    return 2;
  }
  frame[n - 1] ^= 0xFFu;
  if (saam_dispatch(frame, n, response, sizeof response, &response_len) != -1) {
    return 3;
  }
  sum = saam_crc32((const uint8_t *)"abc", 3);
  if (sum != 0x352441C2u) {
    return 4;
  }

  sha_force_done = 1;
  sha_reg[0x04u / 4u] = 0x4u;
  sha_reg[0x10u / 4u] = 0xBA7816BFu;
  sha_reg[0x14u / 4u] = 0x8F01CFEAu;
  {
    uint8_t digest[32];
    if (saam_sha256(NULL, 0, 0, digest) != 0) {
      return 5;
    }
    if (digest[0] != 0xBAu || digest[1] != 0x78u || digest[2] != 0x16u || digest[3] != 0xBFu) {
      return 6;
    }
    if (digest[4] != 0x8Fu || digest[7] != 0xEAu) {
      return 7;
    }
    for (i = 8; i < 32; i++) {
      if (digest[i] != 0) {
        return 8;
      }
    }
  }

  sha_force_done = 0;
  memset(sha_reg, 0, sizeof sha_reg);
  n = saam_frame(0x10, (const uint8_t *)"abc", 3, frame);
  if (saam_dispatch(frame, n, response, sizeof response, &response_len) != 0) {
    return 9;
  }
  if (response_len != 43 || response[6] != 0 || !expect_digest(response + 7)) {
    return 10;
  }
  if (saam_dispatch(frame, n, response, 16, &response_len) != -1) {
    return 11;
  }

  saam_fir_clear();
  fir_blocked = 0;
  if (saam_fir_push(1000, &value, &produced) != 0 || produced != 1 || value != -1) {
    return 12;
  }
  for (i = 0; i < 4; i++) {
    if (saam_fir_push(0, &value, &produced) != 0 || produced != 0) {
      return 13;
    }
  }
  if (saam_fir_push(-1000, &value, &produced) != 0 || produced != 1 || value != 4) {
    return 14;
  }
  if (fir_blocked != 0) {
    return 15;
  }

  for (i = 0; i < 6; i++) {
    samples[2u * i] = (uint8_t)((uint16_t)k_in[i]);
    samples[2u * i + 1u] = (uint8_t)((uint16_t)k_in[i] >> 8);
  }
  n = saam_frame(0x20, samples, 12, frame);
  if (saam_dispatch(frame, n, response, sizeof response, &response_len) != 0) {
    return 16;
  }
  if (response_len != 15 || response[6] != 0 || response[7] != 0xFF || response[8] != 0xFF ||
      response[9] != 4 || response[10] != 0) {
    return 17;
  }
  if (fir_blocked != 0) {
    return 18;
  }
  n = saam_frame(0x20, (const uint8_t *)"x", 1, frame);
  if (saam_dispatch(frame, n, response, sizeof response, &response_len) != -1) {
    return 19;
  }
  n = saam_frame(0x7F, NULL, 0, frame);
  if (saam_dispatch(frame, n, response, sizeof response, &response_len) != -2) {
    return 20;
  }

  puts("SAAM_CMD_HOSTCHECK PASSED");
  return 0;
}
