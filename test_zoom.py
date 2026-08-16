"""Tests for zoom passthrough (onvif driver + capability advertisement)."""
import time
import xml.etree.ElementTree as ET
import requests
import app as bridge


def make_engine(**over):
    cfg = {"ip": "10.0.10.231", "user": "admin", "driver": "onvif", "port": 9995,
           "profile_token": "MainStream", "onvif_zoom_velocity": 0.6}
    cfg.update(over)
    return bridge.MotionEngine("t", cfg, "secret")


def test_zoom_soap():
    eng = make_engine()
    posts = []
    eng._onvif_post = lambda action, body: posts.append((action, body))
    eng._send_cmd("zoom_in")
    eng._send_cmd("zoom_out")
    eng._send_cmd("stop")
    for _, body in posts:
        ET.fromstring(body)  # well-formed
    assert posts[0][0].endswith("/ContinuousMove") and '<Zoom x="0.6"' in posts[0][1], posts[0]
    assert '<Zoom x="-0.6"' in posts[1][1], posts[1]
    assert posts[2][0].endswith("/Stop") and "<Zoom>true</Zoom>" in posts[2][1]
    # zoom must NOT emit a PanTilt velocity
    assert "PanTilt" not in posts[0][1]
    print("PASS  zoom_in/out -> ONVIF ContinuousMove Zoom; stop -> Stop")


def test_pan_still_works():
    # regression: pan/tilt path unaffected by the zoom additions
    eng = make_engine()
    posts = []
    eng._onvif_post = lambda a, b: posts.append((a, b))
    eng._send_cmd("left")
    assert 'x="-0.5"' in posts[0][1] and "PanTilt" in posts[0][1] and "Zoom" not in posts[0][1]
    print("PASS  pan/tilt unchanged (no zoom leakage)")


def test_flask_advertises_zoom_and_dispatches():
    eng = make_engine(port=9995)
    posts = []
    eng._onvif_post = lambda a, b: posts.append((a, b))
    eng.start()
    srv = bridge.ProxyServerThread(eng, 9995)
    srv.start()
    time.sleep(0.6)
    base = "http://127.0.0.1:9995/onvif/ptz_service"

    def soap(inner, ns=""):
        return (f'<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope" {ns}>'
                f'<s:Body>{inner}</s:Body></s:Envelope>')

    prof = requests.post(base, data=soap('<GetProfiles xmlns="http://www.onvif.org/ver10/media/wsdl"/>'),
                         headers={"Content-Type": "application/soap+xml"}, timeout=3).text
    assert "TranslationSpaceFov" in prof, "pan/tilt FOV must still be advertised"
    assert "DefaultContinuousZoomVelocitySpace" in prof, "profile must advertise zoom"

    opts = requests.post(base, data=soap('<GetConfigurationOptions xmlns="http://www.onvif.org/ver20/ptz/wsdl"/>'),
                         headers={"Content-Type": "application/soap+xml"}, timeout=3).text
    assert "ContinuousZoomVelocitySpace" in opts, "options must advertise zoom velocity space"
    # responses must still parse as XML
    ET.fromstring(prof); ET.fromstring(opts)

    # A zoom-only ContinuousMove (what Frigate's zoom button sends) must forward a zoom command
    cm = ('<ContinuousMove xmlns="http://www.onvif.org/ver20/ptz/wsdl"><ProfileToken>x</ProfileToken>'
          '<Velocity><tt:Zoom x="0.5"/></Velocity></ContinuousMove>')
    r = requests.post(base, data=soap(cm, 'xmlns:tt="http://www.onvif.org/ver10/schema"'),
                      headers={"Content-Type": "application/soap+xml"}, timeout=3).text
    assert "ContinuousMoveResponse" in r
    time.sleep(0.5)
    assert any(a.endswith("/ContinuousMove") and 'Zoom x="0.6"' in b for a, b in posts), \
        f"zoom-only move not forwarded: {[b for _, b in posts]}"
    print("PASS  Flask advertises zoom + forwards a zoom-only ContinuousMove")


if __name__ == "__main__":
    test_zoom_soap()
    test_pan_still_works()
    test_flask_advertises_zoom_and_dispatches()
    print("\nALL ZOOM TESTS PASSED")
