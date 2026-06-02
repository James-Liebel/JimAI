"""Client-presence window backing the generation dead-man's switch."""

from __future__ import annotations

import time

from agent_space.instance_lifecycle import InstanceLifecycleManager


def test_no_baseline_yet_does_not_arm_switch():
    # Before any client has ever been seen this run, the dead-man's switch must
    # stay disarmed so a chat issued during boot isn't falsely aborted.
    mgr = InstanceLifecycleManager()
    mgr._instances.clear()
    mgr._last_client_seen = 0.0
    assert mgr.has_recent_clients() is True


def test_recent_heartbeat_counts_as_present():
    mgr = InstanceLifecycleManager(client_presence_window_seconds=75)
    mgr._last_client_seen = time.time()
    assert mgr.has_recent_clients() is True


def test_stale_client_falls_outside_window():
    mgr = InstanceLifecycleManager(client_presence_window_seconds=75)
    mgr._last_client_seen = time.time() - 200  # long past the window
    assert mgr.has_recent_clients() is False
