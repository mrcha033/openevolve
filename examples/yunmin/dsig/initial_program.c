#include <stdio.h>
#include <stdlib.h>
#include <string.h>
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
    0x19,0x1a,0x1b,0x1c,0x1d,0x1e,0x1f,0x20
};

static unsigned char messages[NUM_MESSAGES][MESSAGE_LEN];
static unsigned char pk[crypto_sign_ed25519_PUBLICKEYBYTES];
static unsigned char sk[crypto_sign_ed25519_SECRETKEYBYTES];

void init_data(void) {
    if (sodium_init() < 0) { fprintf(stderr, "sodium_init failed\n"); exit(1); }
    crypto_sign_ed25519_keypair(pk, sk);
    for (int i = 0; i < NUM_MESSAGES; i++)
        randombytes_buf(messages[i], MESSAGE_LEN);
}

// EVOLVE-BLOCK-START
/* ── Sign one message. This is the hot function to optimize. ── */
int sign_message(const unsigned char *msg, unsigned long long msg_len,
                 unsigned char *sig_out, unsigned long long *sig_out_len,
                 const unsigned char *secret_key) {
    return crypto_sign_ed25519(sig_out, sig_out_len, msg, msg_len, secret_key);
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

    /* Print public key first */
    printf("PK:");
    for (int j = 0; j < crypto_sign_ed25519_PUBLICKEYBYTES; j++)
        printf("%02x", seed_pk[j]);
    printf("\n");

    for (int i = 0; i < VERIFY_COUNT; i++) {
        /* Deterministic message from index */
        memset(msg, 0, MESSAGE_LEN);
        memcpy(msg, &i, sizeof(i));
        for (int j = sizeof(i); j < MESSAGE_LEN; j++)
            msg[j] = (unsigned char)((i * 137 + j * 31) & 0xff);

        sign_message(msg, MESSAGE_LEN, sig, &sig_len, seed_sk);

        /* Print: MSG_HEX SIG_HEX */
        for (int j = 0; j < MESSAGE_LEN; j++) printf("%02x", msg[j]);
        printf(" ");
        /* sig = signature || message, first 64 bytes are the actual sig */
        for (int j = 0; j < crypto_sign_ed25519_BYTES; j++) printf("%02x", sig[j]);
        printf("\n");
    }
}

// EVOLVE-BLOCK-START
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

int main(int argc, char **argv) {
    init_data();
    if (argc > 1 && strcmp(argv[1], "--verify") == 0)
        run_verify();
    else
        run_bench();
    return 0;
}