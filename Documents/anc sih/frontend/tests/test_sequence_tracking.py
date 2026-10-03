import pytest

class SequenceTracker:
    def __init__(self):
        self.received = 0
        self.lost = 0
        self.duplicates = 0
        self.out_of_order = 0
        self.last_seq = None

    def process_seq(self, seq: int):
        if self.last_seq is None:
            self.received += 1
            self.last_seq = seq
        elif seq == self.last_seq + 1:
            self.received += 1
            self.last_seq = seq
        elif seq == self.last_seq:
            self.duplicates += 1
        elif seq < self.last_seq:
            self.out_of_order += 1
        else:
            lost = seq - (self.last_seq + 1)
            self.lost += lost
            self.received += 1
            self.last_seq = seq

def test_normal_in_order_sequence():
    tracker = SequenceTracker()
    for seq in range(100):
        tracker.process_seq(seq)
    assert tracker.received == 100
    assert tracker.lost == 0
    assert tracker.duplicates == 0
    assert tracker.out_of_order == 0

def test_packet_loss_tracking():
    tracker = SequenceTracker()
    tracker.process_seq(0)
    tracker.process_seq(1)
    tracker.process_seq(5) # Skipped 2, 3, 4 -> 3 lost
    assert tracker.received == 3
    assert tracker.lost == 3

def test_duplicate_and_out_of_order():
    tracker = SequenceTracker()
    tracker.process_seq(10)
    tracker.process_seq(11)
    tracker.process_seq(11) # Duplicate
    tracker.process_seq(9)  # Out of order
    assert tracker.duplicates == 1
    assert tracker.out_of_order == 1
