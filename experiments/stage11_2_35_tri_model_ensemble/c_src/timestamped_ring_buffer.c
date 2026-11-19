#include "timestamped_ring_buffer.h"
#include <string.h>
#include <stdio.h>
#include <time.h>

static double trb_get_time_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (double)ts.tv_sec * 1000.0 + (double)ts.tv_nsec / 1000000.0;
}

void trb_init(TimestampedRingBuffer* rb) {
    if (!rb) return;
    memset(rb->data, 0, sizeof(rb->data));
    rb->capacity = RING_BUFFER_CAPACITY;
    rb->write_pos = 0;
    rb->read_pos = 0;
    rb->terminated = false;
    rb->total_writes = 0;
    rb->total_reads = 0;
    rb->max_wait_time_ms = 0.0;
    rb->total_wait_time_ms = 0.0;

    pthread_mutex_init(&rb->lock, NULL);
    pthread_cond_init(&rb->cond_read, NULL);
    pthread_cond_init(&rb->cond_write, NULL);
}

void trb_destroy(TimestampedRingBuffer* rb) {
    if (!rb) return;
    pthread_mutex_lock(&rb->lock);
    rb->terminated = true;
    pthread_cond_broadcast(&rb->cond_read);
    pthread_cond_broadcast(&rb->cond_write);
    pthread_mutex_unlock(&rb->lock);

    pthread_cond_destroy(&rb->cond_read);
    pthread_cond_destroy(&rb->cond_write);
    pthread_mutex_destroy(&rb->lock);
}

void trb_reset(TimestampedRingBuffer* rb) {
    if (!rb) return;
    pthread_mutex_lock(&rb->lock);
    memset(rb->data, 0, sizeof(rb->data));
    rb->write_pos = 0;
    rb->read_pos = 0;
    rb->terminated = false;
    pthread_cond_broadcast(&rb->cond_write);
    pthread_mutex_unlock(&rb->lock);
}

void trb_terminate(TimestampedRingBuffer* rb) {
    if (!rb) return;
    pthread_mutex_lock(&rb->lock);
    rb->terminated = true;
    pthread_cond_broadcast(&rb->cond_read);
    pthread_cond_broadcast(&rb->cond_write);
    pthread_mutex_unlock(&rb->lock);
}

bool trb_write(TimestampedRingBuffer* rb, uint64_t sample_idx, const float* src, size_t count) {
    if (!rb || !src || count == 0) return false;

    pthread_mutex_lock(&rb->lock);
    while (!rb->terminated && (sample_idx + count - rb->read_pos > rb->capacity)) {
        pthread_cond_wait(&rb->cond_write, &rb->lock);
    }
    if (rb->terminated) {
        pthread_mutex_unlock(&rb->lock);
        return false;
    }

    for (size_t i = 0; i < count; ++i) {
        size_t idx = (size_t)((sample_idx + i) % rb->capacity);
        rb->data[idx] = src[i];
    }

    if (sample_idx + count > rb->write_pos) {
        rb->write_pos = sample_idx + count;
    }
    rb->total_writes++;

    pthread_cond_broadcast(&rb->cond_read);
    pthread_mutex_unlock(&rb->lock);
    return true;
}

bool trb_read(TimestampedRingBuffer* rb, uint64_t sample_idx, float* dst, size_t count) {
    if (!rb || !dst || count == 0) return false;

    double t0 = trb_get_time_ms();
    pthread_mutex_lock(&rb->lock);
    while (!rb->terminated && (rb->write_pos < sample_idx + count)) {
        pthread_cond_wait(&rb->cond_read, &rb->lock);
    }

    double wait_time = trb_get_time_ms() - t0;
    if (wait_time > rb->max_wait_time_ms) {
        rb->max_wait_time_ms = wait_time;
    }
    rb->total_wait_time_ms += wait_time;

    if (rb->write_pos < sample_idx + count) {
        /* Terminated before enough samples became available */
        pthread_mutex_unlock(&rb->lock);
        return false;
    }

    for (size_t i = 0; i < count; ++i) {
        size_t idx = (size_t)((sample_idx + i) % rb->capacity);
        dst[i] = rb->data[idx];
    }

    if (sample_idx + count > rb->read_pos) {
        rb->read_pos = sample_idx + count;
    }
    rb->total_reads++;

    pthread_cond_broadcast(&rb->cond_write);
    pthread_mutex_unlock(&rb->lock);
    return true;
}

size_t trb_available_from(TimestampedRingBuffer* rb, uint64_t sample_idx) {
    if (!rb) return 0;
    pthread_mutex_lock(&rb->lock);
    size_t avail = 0;
    if (rb->write_pos > sample_idx) {
        avail = (size_t)(rb->write_pos - sample_idx);
    }
    pthread_mutex_unlock(&rb->lock);
    return avail;
}

