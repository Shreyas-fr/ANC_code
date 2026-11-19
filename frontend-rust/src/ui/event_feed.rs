//! Real-Time Event Audit Feed for Operator Console.

use std::collections::VecDeque;
use std::time::SystemTime;

#[derive(Clone, Debug)]
pub enum EventSeverity {
    Info,
    Warn,
    Error,
}

#[derive(Clone, Debug)]
pub struct AuditEvent {
    pub timestamp: String,
    pub source: String,
    pub message: String,
    pub severity: EventSeverity,
}

pub struct EventFeed {
    events: VecDeque<AuditEvent>,
    max_events: usize,
}

impl EventFeed {
    pub fn new(max_events: usize) -> Self {
        Self {
            events: VecDeque::with_capacity(max_events),
            max_events,
        }
    }

    pub fn log(&mut self, source: &str, message: &str, severity: EventSeverity) {
        let now = SystemTime::now();
        let datetime: chrono::DateTime<chrono::Local> = now.into();
        let timestamp = datetime.format("%H:%M:%S").to_string();

        if self.events.len() >= self.max_events {
            self.events.pop_back();
        }

        self.events.push_front(AuditEvent {
            timestamp,
            source: source.to_string(),
            message: message.to_string(),
            severity,
        });
    }

    pub fn events(&self) -> &VecDeque<AuditEvent> {
        &self.events
    }
}
