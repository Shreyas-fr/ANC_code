#ifndef TIMESTAMPED_RING_BUFFER_H
#define TIMESTAMPED_RING_BUFFER_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
#include <pthread.h>

#define RING_BUFFER_CAPACITY (131072) /* 131,072 samples = 8.192 s @ 16 kHz */

typedef struct {
    float data[RING_BUFFER_CAPACITY];
    size_t capacity;
    
    /* Global continuous sample counters */
    uint64_t write_pos; /* Continuous samples written so far */
    uint64_t read_pos;  /* Continuous samples consumed so far */
    
    pthread_mutex_t lock;
    pthread_cond_t cond_read;
    pthread_cond_t cond_write;
    
    bool terminated;
    
    /* Performance metrics */
    uint64_t total_writes;
    uint64_t total_reads;
    double max_wait_time_ms;
    double total_wait_time_ms;
} TimestampedRingBuffer;

#ifdef __cplusplus
extern "C" {
#endif

void trb_init(TimestampedRingBuffer* rb);
void trb_destroy(TimestampedRingBuffer* rb);
void trb_reset(TimestampedRingBuffer* rb);
void trb_terminate(TimestampedRingBuffer* rb);

/* Write a contiguous block of samples starting at continuous index sample_idx */
bool trb_write(TimestampedRingBuffer* rb, uint64_t sample_idx, const float* src, size_t count);

/* Read a contiguous block of samples starting at continuous index sample_idx (blocking if not ready) */
bool trb_read(TimestampedRingBuffer* rb, uint64_t sample_idx, float* dst, size_t count);

/* Query available samples starting from sample_idx without blocking */
size_t trb_available_from(TimestampedRingBuffer* rb, uint64_t sample_idx);

#ifdef __cplusplus
}
#endif

#endif /* TIMESTAMPED_RING_BUFFER_H */

