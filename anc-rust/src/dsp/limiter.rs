//! Soft-knee peak limiter to prevent digital clipping without introducing harsh harmonics.

/// Soft-knee smooth limiter.
#[derive(Debug, Clone)]
pub struct SoftLimiter {
    knee: f32,
}

impl Default for SoftLimiter {
    fn default() -> Self {
        Self { knee: 0.85 }
    }
}

impl SoftLimiter {
    pub fn new(knee: f32) -> Self {
        assert!(knee > 0.0 && knee < 1.0, "knee must be between 0.0 and 1.0");
        Self { knee }
    }

    /// Limits samples in-place.
    ///
    /// Values with magnitude <= knee pass through linearly (100% transparent).
    /// Values with magnitude > knee smoothly saturate towards 1.0 using tanh.
    pub fn process(&self, samples: &mut [f32]) -> usize {
        let mut limited_count = 0;
        let knee = self.knee;
        let headroom = 1.0 - knee;

        for s in samples.iter_mut() {
            let abs_val = s.abs();
            if abs_val > knee {
                limited_count += 1;
                let sign = s.signum();
                let excess = (abs_val - knee) / headroom;
                *s = sign * (knee + headroom * excess.tanh());
            }
        }
        limited_count
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_limiter_behavior() {
        let limiter = SoftLimiter::new(0.8);
        let mut buf = vec![0.5, 0.8, 1.2, -2.0];
        let count = limiter.process(&mut buf);

        assert_eq!(count, 2);
        assert_eq!(buf[0], 0.5); // Untouched
        assert_eq!(buf[1], 0.8); // On knee
        assert!(buf[2] > 0.8 && buf[2] < 1.0); // Smoothly compressed
        assert!(buf[3] < -0.8 && buf[3] > -1.0); // Smoothly compressed
    }
}
