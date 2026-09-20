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


if __name__ == "__main__":
    test_pipeline_has_bounded_latency_and_expected_caps()
    print("ok  test_pipeline_has_bounded_latency_and_expected_caps")
