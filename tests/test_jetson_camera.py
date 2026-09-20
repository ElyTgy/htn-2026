"""Pure pipeline construction test; it does not require a Jetson or OpenCV."""
import importlib.util
from pathlib import Path

source_path = Path(__file__).resolve().parent.parent / "pi" / "sources" / "jetson_csi_source.py"
spec = importlib.util.spec_from_file_location("jetson_csi_source", source_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
gstreamer_pipeline = module.gstreamer_pipeline


def test_pipeline_has_bounded_latency_and_expected_caps():
    pipeline = gstreamer_pipeline(1, 1280, 720, 30)
    assert "nvarguscamerasrc sensor-id=1" in pipeline
    assert "width=(int)1280,height=(int)720" in pipeline
    assert "framerate=(fraction)30/1" in pipeline
    assert "memory:NVMM" in pipeline
    assert "appsink drop=true max-buffers=1 sync=false" in pipeline


def test_oak_source_is_registered_and_launcher_uses_live_mediapipe_path():
    root = Path(__file__).resolve().parent.parent
    sources = (root / "pi/sources/__init__.py").read_text()
    launcher = (root / "scripts/jetson_start.sh").read_text()
    assert 'name == "oak"' in sources
    assert 'oak) set -- --backend mediapipe --source oak --width 512 --height 384 ;;' in launcher


def test_oak_capture_is_60_fps_and_latest_frame_only():
    root = Path(__file__).resolve().parent.parent
    source = (root / "pi/sources/oak_source.py").read_text()
    assert "FPS = 60" in source
    assert "WIDTH = 512" in source
    assert "HEIGHT = 384" in source
    assert "resizeMode=dai.ImgResizeMode.LETTERBOX" in source
    assert "setPreviewKeepAspectRatio(True)" in source
    assert "bgr[::-1, ::-1, ::-1].copy()" in source
    assert "self._latest = rgb" in source
    assert "self._sequence += 1" in source
    assert "self._latest is not None and self._sequence != self._read_sequence" in source
    assert "inference-width" not in (root / "pi/main.py").read_text()
    assert "send_hz" not in (root / "pi/config.py").read_text()
    assert "asyncio.sleep(1 / 60)" in (root / "pi/server.py").read_text()


def test_jetson_mediapipe_requires_gpu_without_a_cpu_fallback():
    root = Path(__file__).resolve().parent.parent
    backend = (root / "pi/backends/mediapipe_backend.py").read_text()
    assert 'b"jetson" in JETSON_MODEL_PATH.read_bytes().lower()' in backend
    assert "mp_python.BaseOptions.Delegate.GPU" in backend
    assert "except" not in backend.split("self._landmarker =", 1)[1].split("self.source.start()", 1)[0]


def test_scripted_transcription_is_not_shippable():
    root = Path(__file__).resolve().parent.parent
    assert not (root / "web/stt/mock.js").exists()
    assert "./stt/mock.js" not in (root / "web/app.js").read_text()


def test_global_caption_bar_is_not_shippable():
    root = Path(__file__).resolve().parent.parent
    assert 'id="bar"' not in (root / "web/index.html").read_text()
    assert "faceId ?? 'bar'" not in (root / "web/app.js").read_text()


def test_glasses_controls_expose_boxes_menu_and_display_mode():
    root = Path(__file__).resolve().parent.parent
    html = (root / "web/index.html").read_text()
    app = (root / "web/app.js").read_text()
    assert 'id="control-dock"' in html
    assert '>B</button>' in html
    assert 'id="menu-btn"' in html
    assert 'id="video-toggle"' in html
    assert 'id="settings-hotspot"' not in html
    assert "store.set('camera-feed'" in app


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok ", name)
