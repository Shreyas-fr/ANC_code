#include "gap_safe_ring_buffer.h"
#include <stdlib.h>
#include <string.h>
#include <errno.h>

int trb_init(gap_safe_ring_buffer_t *rb, uint32_t capacity) {
    if (!rb || capacity == 0) return -1;
    // Capacity must be power of 2
    if ((capacity & (capacity - 1)) != 0) return -1;

    rb->capacity = capacity;
    rb->mask = capacity - 1;
    rb->data = (float *)calloc(capacity, sizeof(float));
    rb->sample_indices = (int64_t *)malloc(capacity * sizeof(int64_t));
    if (!rb->data || !rb->sample_indices) {
        free(rb->data);
        free(rb->sample_indices);
        return -1;
    }

    // Initialize all slot indices to -1 (indicating unwritten)
    for (uint32_t i = 0; i < capacity; ++i) {
        rb->sample_indices[i] = -1;
    }

    rb->write_pos = 0;
    rb->min_valid_pos = 0;
    rb->shutdown = false;

    pthread_mutex_init(&rb->mutex, NULL);
    pthread_cond_init(&rb->data_cond, NULL);

    return 0;
}

void trb_destroy(gap_safe_ring_buffer_t *rb) {
    if (!rb) return;
    trb_shutdown(rb);
    pthread_mutex_destroy(&rb->mutex);
    pthread_cond_destroy(&rb->data_cond);
    free(rb->data);
    free(rb->sample_indices);
    rb->data = NULL;
    rb->sample_indices = NULL;
}

void trb_shutdown(gap_safe_ring_buffer_t *rb) {
    if (!rb) return;
    pthread_mutex_lock(&rb->mutex);
    rb->shutdown = true;
    pthread_cond_broadcast(&rb->data_cond);
    pthread_mutex_unlock(&rb->mutex);
}

trb_status_t trb_write(gap_safe_ring_buffer_t *rb, int64_t sample_idx, const float *data, uint32_t count) {
    if (!rb || !data || count == 0) return TRB_ERROR_INVALID_ARGS;

    pthread_mutex_lock(&rb->mutex);
    if (rb->shutdown) {
        pthread_mutex_unlock(&rb->mutex);
        return TRB_ERROR_SHUTDOWN;
    }

    // Write samples and tag each slot with its exact absolute sample index
    for (uint32_t i = 0; i < count; ++i) {
        int64_t idx = sample_idx + i;
        uint32_t slot = (uint32_t)(idx & rb->mask);
        rb->data[slot] = data[i];
        rb->sample_indices[slot] = idx;
    }

    int64_t end_idx = sample_idx + count;
    if (end_idx > rb->write_pos) {
        rb->write_pos = end_idx;
    }

    // Overrun floor: buffer cannot retain samples older than write_pos - capacity
    int64_t new_floor = rb->write_pos - (int64_t)rb->capacity;
    if (new_floor > rb->min_valid_pos) {
        rb->min_valid_pos = new_floor;
    }

    pthread_cond_broadcast(&rb->data_cond);
    pthread_mutex_unlock(&rb->mutex);

    return TRB_SUCCESS;
}

trb_status_t trb_read(gap_safe_ring_buffer_t *rb, int64_t sample_idx, float *data, uint32_t count) {
    if (!rb || !data || count == 0) return TRB_ERROR_INVALID_ARGS;

    pthread_mutex_lock(&rb->mutex);

    // Wait until write_pos has advanced past the requested range
    while (!rb->shutdown && rb->write_pos < sample_idx + count) {
        pthread_cond_wait(&rb->data_cond, &rb->mutex);
    }

    if (rb->shutdown) {
        pthread_mutex_unlock(&rb->mutex);
        return TRB_ERROR_SHUTDOWN;
    }

    // Check if the requested range has already been overrun
    if (sample_idx < rb->min_valid_pos) {
        pthread_mutex_unlock(&rb->mutex);
        return TRB_ERROR_OVERRUN;
    }

    // Per-sample validity and gap verification
    for (uint32_t i = 0; i < count; ++i) {
        int64_t target = sample_idx + i;
        uint32_t slot = (uint32_t)(target & rb->mask);
        int64_t recorded = rb->sample_indices[slot];

        if (recorded < target) {
            // Slot holds stale data or was never written -> GAP detected!
            pthread_mutex_unlock(&rb->mutex);
            return TRB_ERROR_GAP;
        }
        if (recorded > target) {
            // Slot was already overwritten by a later write -> OVERRUN!
            pthread_mutex_unlock(&rb->mutex);
            return TRB_ERROR_OVERRUN;
        }

        data[i] = rb->data[slot];
    }

    pthread_mutex_unlock(&rb->mutex);
    return TRB_SUCCESS;
}

trb_status_t trb_read_timeout(gap_safe_ring_buffer_t *rb, int64_t sample_idx, float *data, uint32_t count, uint32_t timeout_ms) {
    if (!rb || !data || count == 0) return TRB_ERROR_INVALID_ARGS;

    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    ts.tv_sec += timeout_ms / 1000;
    ts.tv_nsec += (timeout_ms % 1000) * 1000000L;
    if (ts.tv_nsec >= 1000000000L) {
        ts.tv_sec += 1;
        ts.tv_nsec -= 1000000000L;
    }

    pthread_mutex_lock(&rb->mutex);

    while (!rb->shutdown && rb->write_pos < sample_idx + count) {
        int rc = pthread_cond_timedwait(&rb->data_cond, &rb->mutex, &ts);
        if (rc == ETIMEDOUT) {
            pthread_mutex_unlock(&rb->mutex);
            return TRB_ERROR_TIMEOUT;
        }
    }

    if (rb->shutdown) {
        pthread_mutex_unlock(&rb->mutex);
        return TRB_ERROR_SHUTDOWN;
    }

    if (sample_idx < rb->min_valid_pos) {
        pthread_mutex_unlock(&rb->mutex);
        return TRB_ERROR_OVERRUN;
    }

    for (uint32_t i = 0; i < count; ++i) {
        int64_t target = sample_idx + i;
        uint32_t slot = (uint32_t)(target & rb->mask);
        int64_t recorded = rb->sample_indices[slot];

        if (recorded < target) {
            pthread_mutex_unlock(&rb->mutex);
            return TRB_ERROR_GAP;
        }
        if (recorded > target) {
            pthread_mutex_unlock(&rb->mutex);
            return TRB_ERROR_OVERRUN;
        }

        data[i] = rb->data[slot];
    }

    pthread_mutex_unlock(&rb->mutex);
    return TRB_SUCCESS;
}

