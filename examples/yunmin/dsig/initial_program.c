#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <time.h>
#include <sodium.h>

#define NUM_MESSAGES    1000
#define MESSAGE_LEN     128
#define BENCH_ITERS     50000
#define VERIFY_COUNT    50

/* ── Deterministic seed for verify mode reproducibility ── */
static const unsigned char FIXED_SEED[randombytes_SEEDBYTES] = {
    0x01,0x02,0x03,0x04,0x05,0x06,0x07,0x08,
    0x09,0x0a,0x0b,0x0c,0x0d,0x0e,0x0f,0x10,
    0x11,0x12,0x13,0x14,0x15,0x16,0x17,0x18,
    0x19,0x1a,0x1b,0x1c,0x1d,0x1f,0x1f,0x20
};

static unsigned char messages[NUM_MESSAGES][MESSAGE_LEN];
static unsigned char pk[crypto_sign_ed25519_PUBLICKEYBYTES];
static unsigned char sk[crypto_sign_ed25519_SECRETKEYBYTES];

/* ── Utility: s = a*b + c (mod L) ──
 * Schoolbook multiply + crypto_core_ed25519_scalar_reduce.
 * All inputs are 32-byte little-endian scalars. */
static void sc_muladd(unsigned char s[32], const unsigned char a[32],
                      const unsigned char b[32], const unsigned char c[32]) {
    uint32_t r[64];
    memset(r, 0, sizeof(r));
    for (int i = 0; i < 32; i++)
        for (int j = 0; j < 32; j++)
            r[i + j] += (uint32_t)a[i] * b[j];
    for (int i = 0; i < 32; i++)
        r[i] += c[i];
    for (int i = 0; i < 63; i++) {
        r[i + 1] += r[i] >> 8;
        r[i] &= 0xff;
    }
    r[63] &= 0xff;
    unsigned char product[64];
    for (int i = 0; i < 64; i++)
        product[i] = (unsigned char)r[i];
    crypto_core_ed25519_scalar_reduce(s, product);
}

void init_data(void) {
    if (sodium_init() < 0) { fprintf(stderr, "sodium_init failed\n"); exit(1); }
    crypto_sign_ed25519_keypair(pk, sk);
    for (int i = 0; i < NUM_MESSAGES; i++)
        randombytes_buf(messages[i], MESSAGE_LEN);
}

// EVOLVE-BLOCK-START
/*
 * Decomposed Ed25519 signing — each step is a separate function call
 * so the profiler can attribute CPU time to individual operations.
 *
 * Ed25519 signing steps:
 *   1. Expand secret key:  (a, prefix) = SHA-512(seed), clamp a
 *   2. Derive nonce:       r = SHA-512(prefix || msg) mod L
 *   3. Compute R:          R = r * B          ← EXPENSIVE (scalar mult on curve)
 *   4. Compute challenge:  h = SHA-512(R || pk || msg) mod L
 *   5. Compute S:          S = h*a + r mod L  ← cheap (scalar arithmetic)
 *   6. Output:             sig = R || S
 */
int sign_message(const unsigned char *msg, unsigned long long msg_len,
                 unsigned char *sig_out, unsigned long long *sig_out_len,
                 const unsigned char *secret_key) {

    /* Step 1: Expand secret key → (a, prefix) */
    unsigned char az[64];
    crypto_hash_sha512(az, secret_key, 32);
    az[0]  &= 248;
    az[31] &= 127;
    az[31] |= 64;
    /* az[0..31] = clamped scalar a,  az[32..63] = nonce prefix */

    /* Step 2: Derive nonce r = SHA-512(prefix || msg) mod L */
    unsigned char nonce_hash[64];
    crypto_hash_sha512_state hs;
    crypto_hash_sha512_init(&hs);
    crypto_hash_sha512_update(&hs, az + 32, 32);
    crypto_hash_sha512_update(&hs, msg, msg_len);
    crypto_hash_sha512_final(&hs, nonce_hash);

    unsigned char r_scalar[32];
    crypto_core_ed25519_scalar_reduce(r_scalar, nonce_hash);

    /* Step 3: R = r * B — scalar multiplication on Ed25519 base point */
    unsigned char R[32];
    crypto_scalarmult_ed25519_base_noclamp(R, r_scalar);

    /* Step 4: h = SHA-512(R || pk || msg) mod L */
    unsigned char hram_hash[64];
    crypto_hash_sha512_init(&hs);
    crypto_hash_sha512_update(&hs, R, 32);
    crypto_hash_sha512_update(&hs, secret_key + 32, 32);  /* pk = sk[32..63] */
    crypto_hash_sha512_update(&hs, msg, msg_len);
    crypto_hash_sha512_final(&hs, hram_hash);

    unsigned char hram[32];
    crypto_core_ed25519_scalar_reduce(hram, hram_hash);

    /* Step 5: S = h*a + r mod L */
    unsigned char S[32];
    sc_muladd(S, hram, az, r_scalar);

    /* Step 6: Assemble signature = R || S, then append message */
    memcpy(sig_out, R, 32);
    memcpy(sig_out + 32, S, 32);
    memcpy(sig_out + 64, msg, (size_t)msg_len);
    *sig_out_len = 64ULL + msg_len;

    sodium_memzero(az, sizeof(az));
    sodium_memzero(r_scalar, sizeof(r_scalar));

    return 0;
}

/* ── Bench mode: throughput measurement ── */
void run_bench(void) {
    unsigned char sig[crypto_sign_ed25519_BYTES + MESSAGE_LEN];
    unsigned long long sig_len;
    struct timespec t0, t1;

    /* Warm up */
    for (int i = 0; i < 1000; i++)
        sign_message(messages[i % NUM_MESSAGES], MESSAGE_LEN, sig, &sig_len, sk);

    clock_gettime(CLOCK_MONOTONIC, &t0);
    for (int i = 0; i < BENCH_ITERS; i++)
        sign_message(messages[i % NUM_MESSAGES], MESSAGE_LEN, sig, &sig_len, sk);
    clock_gettime(CLOCK_MONOTONIC, &t1);

    double secs = (t1.tv_sec - t0.tv_sec) + (t1.tv_nsec - t0.tv_nsec) / 1e9;
    printf("%.2f\n", (double)BENCH_ITERS / secs);
}
// EVOLVE-BLOCK-END

/* ── Verify mode: deterministic messages + print signatures ── */
void run_verify(void) {
    unsigned char seed_sk[crypto_sign_ed25519_SECRETKEYBYTES];
    unsigned char seed_pk[crypto_sign_ed25519_PUBLICKEYBYTES];
    crypto_sign_ed25519_seed_keypair(seed_pk, seed_sk, FIXED_SEED);

    unsigned char msg[MESSAGE_LEN];
    unsigned char sig[crypto_sign_ed25519_BYTES + MESSAGE_LEN];
    unsigned long long sig_len;

    printf("PK:");
    for (int j = 0; j < crypto_sign_ed25519_PUBLICKEYBYTES; j++)
        printf("%02x", seed_pk[j]);
    printf("\n");

    for (int i = 0; i < VERIFY_COUNT; i++) {
        memset(msg, 0, MESSAGE_LEN);
        memcpy(msg, &i, sizeof(i));
        for (int j = sizeof(i); j < MESSAGE_LEN; j++)
            msg[j] = (unsigned char)((i * 137 + j * 31) & 0xff);

        sign_message(msg, MESSAGE_LEN, sig, &sig_len, seed_sk);

        for (int j = 0; j < MESSAGE_LEN; j++) printf("%02x", msg[j]);
        printf(" ");
        for (int j = 0; j < crypto_sign_ed25519_BYTES; j++) printf("%02x", sig[j]);
        printf("\n");
    }
}

int main(int argc, char **argv) {
    init_data();
    if (argc > 1 && strcmp(argv[1], "--verify") == 0)
        run_verify();
    else
        run_bench();
    return 0;
}
