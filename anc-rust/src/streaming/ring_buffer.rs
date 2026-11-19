//! Lock-free Single-Producer Single-Consumer (SPSC) Ring Buffer.
//!
//! Provides zero-allocation, wait-free real-time audio sample streaming
//! between hardware I/O interrupts and background inference threads.

use rtrb::{Consumer, Producer, RingBuffer};

/// Ring buffer producer for pushing audio samples.
pub struct AudioProducer {
    producer: Producer<f32>,
}

impl AudioProducer {
    /// Pushes samples into the ring buffer without blocking.
    /// Returns the number of samples successfully written.
    pub fn push_slice(&mut self, samples: &[f32]) -> usize {
        let mut written = 0;
        for &s in samples {
            if self.producer.push(s).is_ok() {
                written += 1;
            } else {
                break; // Buffer full
            }
        }
        written
    }

    /// Returns available write capacity.
    pub fn slots(&self) -> usize {
        self.producer.slots()
    }
}

/// Ring buffer consumer for reading audio samples.
pub struct AudioConsumer {
    consumer: Consumer<f32>,
}

impl AudioConsumer {
    /// Pops up to `out.len()` samples from the ring buffer into `out`.
    /// Returns the number of samples actually read.
    pub fn pop_slice(&mut self, out: &mut [f32]) -> usize {
        let mut read = 0;
        for s in out.iter_mut() {
            if let Ok(val) = self.consumer.pop() {
                *s = val;
                read += 1;
            } else {
                break; // Buffer empty
            }
        }
        read
    }

    /// Returns number of unread samples currently in the buffer.
    pub fn slots(&self) -> usize {
        self.consumer.slots()
    }
}

/// Creates a new lock-free audio ring buffer with specified sample capacity.
pub fn create_audio_ring_buffer(capacity: usize) -> (AudioProducer, AudioConsumer) {
    let (producer, consumer) = RingBuffer::new(capacity);
    (AudioProducer { producer }, AudioConsumer { consumer })
}
