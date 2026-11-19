#ifndef GAP_SAFE_RING_BUFFER_H
#define GAP_SAFE_RING_BUFFER_H

#include <stdint.h>
#include <stdbool.h>
#include <pthread.h>
#include <time.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    TRB_SUCCESS = 0,
    TRB_ERROR_GAP = 1,          /* Unwritten gap detected inside requested range */
    TRB_ERROR_OVERRUN = 2,      /* Samples have been overwritten by newer writes */
    TRB_ERROR_SHUTDOWN = 3,     /* Ring buffer was shut down */
    TRB_ERROR_TIMEOUT = 4,      /* Blocking wait timed out */
    TRB_ERROR_INVALID_ARGS = 5  /* Invalid arguments passed */
} trb_status_t;

typedef struct {
    float *data;                /* Sample data array */
    int64_t *sample_indices;    /* Monotonic sample index per slot (-1 = unwritten) */
    uint32_t capacity;          /* Must be power of 2 */
    uint32_t mask;              /* capacity - 1 */
    int64_t write_pos;          /* Highest sample index written + 1 */
    int64_t min_valid_pos;      /* Earliest sample index not yet overwritten */
    pthread_mutex_t mutex;
    pthread_cond_t data_cond;
    bool shutdown;
} gap_safe_ring_buffer_t;

/* Lifecycle */
int trb_init(gap_safe_ring_buffer_t *rb, uint32_t capacity);
void trb_destroy(gap_safe_ring_buffer_t *rb);
void trb_shutdown(gap_safe_ring_buffer_t *rb);

/* Thread-safe Operations */
/* Writes 'count' samples starting at 'sample_idx'. Supports out-of-order writes. */
trb_status_t trb_write(gap_safe_ring_buffer_t *rb, int64_t sample_idx, const float *data, uint32_t count);

/* Blocking read: waits until samples [sample_idx, sample_idx + count) are ready.
 * Validates that every sample in the range was explicitly written in the current generation.
 * Returns TRB_SUCCESS only if all samples are valid and contiguous.
 * Returns TRB_ERROR_GAP, TRB_ERROR_OVERRUN, or TRB_ERROR_SHUTDOWN on failure. */
trb_status_t trb_read(gap_safe_ring_buffer_t *rb, int64_t sample_idx, float *data, uint32_t count);

/* Timed blocking read with millisecond timeout */
trb_status_t trb_read_timeout(gap_safe_ring_buffer_t *rb, int64_t sample_idx, float *data, uint32_t count, uint32_t timeout_ms);

#ifdef __cplusplus
}
#endif

#endif /* GAP_SAFE_RING_BUFFER_H */

