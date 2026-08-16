"""Tests for continuous-tracking mode (proportional velocity controller)."""
import time
import xml.etree.ElementTree as ET
import app as bridge


def make_engine(**over):
    cfg = {"ip": "10.0.10.231", "user": "admin", "driver": "onvif",
           "profile_token": "MainStream", "tracking_mode": "continuous",
           "track_watchdog": 0.3}
    cfg.update(over)
    eng = bridge.MotionEngine("t", cfg, "secret")
    eng._posts = []
    eng._onvif_post = lambda a, b: eng._posts.append((a, b))
    return eng


def test_axis_velocity():
    eng = make_engine()  # gain 0.6, deadband 0.06, min 0.1, max 0.4
    assert eng._axis_velocity(0.02) == 0.0          # inside deadband
    assert eng._axis_velocity(0.10) == 0.1          # below min -> min floor
    assert eng._axis_velocity(0.60) == 0.36         # proportional (0.6*0.6)
    assert eng._axis_velocity(0.90) == 0.4          # clamped to max (sustained-safe)
    assert eng._axis_velocity(-0.60) == -0.36       # sign preserved
    print("PASS  proportional axis velocity (deadband / min / gain / max-cap / sign)")


def test_relative_sets_target_not_queue():
    eng = make_engine()
    eng.on_relative_move(0.5, -0.3, 0.0)
    assert eng.target == (0.5, -0.3, 0.0)
    assert eng.work_queue.qsize() == 0  # continuous mode does NOT use the pulse queue
    print("PASS  on_relative_move updates target (no pulse queue)")


def test_controller_drives_then_watchdog_stops():
    eng = make_engine(track_watchdog=0.3)
    eng.start()
    eng.on_relative_move(0.6, -0.4, 0.0)      # target off-centre: pan right, tilt down
    time.sleep(0.2)
    moves = [b for a, b in eng._posts if a.endswith("/ContinuousMove")]
    assert moves, "controller sent no ContinuousMove"
    for b in moves:
        ET.fromstring(b)
    assert '<PanTilt x="0.36" y="-0.24"' in moves[-1], moves[-1]
    # stop feeding -> after the watchdog the camera must be told to Stop
    time.sleep(0.5)
    assert any(a.endswith("/Stop") for a, b in eng._posts), "watchdog did not Stop"
    print("PASS  controller drives proportional velocity; watchdog Stops on target loss")


def test_manual_override_and_stop():
    eng = make_engine()
    eng.on_continuous_move(-0.5, 0.0, 0.0)    # manual pan-left
    assert eng.manual_active is True
    assert any('<PanTilt x="-0.5" y="0.0"' in b for a, b in eng._posts), eng._posts
    eng.on_stop()
    assert eng.manual_active is False
    assert eng.current_vel == (0.0, 0.0, 0.0)
    assert any(a.endswith("/Stop") for a, b in eng._posts)
    print("PASS  manual ContinuousMove passthrough + Stop clears state")


def test_pulse_mode_still_default():
    eng = bridge.MotionEngine("t", {"ip": "1.2.3.4", "user": "admin"}, "p")
    assert eng.tracking_mode == "pulse"
    eng.on_relative_move(0.2, 0.0, 0.0)       # pulse mode routes to the queue
    assert eng.work_queue.qsize() == 1
    print("PASS  pulse mode remains the default; on_relative_move -> queue")


if __name__ == "__main__":
    test_axis_velocity()
    test_relative_sets_target_not_queue()
    test_controller_drives_then_watchdog_stops()
    test_manual_override_and_stop()
    test_pulse_mode_still_default()
    print("\nALL CONTINUOUS TESTS PASSED")
