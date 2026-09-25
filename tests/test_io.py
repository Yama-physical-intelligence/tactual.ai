import json
from pathlib import Path

import pytest

from fingering.actions import Click
from fingering.config import load_settings
from fingering.record import Recorder, read, replay
from tests.test_gestures import make_hand


def test_load_settings_overrides(tmp_path):
    cfg = tmp_path / "s.json"
    cfg.write_text(json.dumps({"natural_scroll": False, "extend_thresholds": [1.1, 1.1, 1.1, 1.1],
                               "profile_path": "~/p.json"}))
    s = load_settings(cfg)
    assert s.natural_scroll is False
    assert s.extend_thresholds == (1.1, 1.1, 1.1, 1.1)
    assert s.profile_path == Path("~/p.json").expanduser()


def test_load_settings_rejects_unknown_keys(tmp_path):
    cfg = tmp_path / "s.json"
    cfg.write_text(json.dumps({"scrol_gain": 2}))
    with pytest.raises(ValueError, match="scrol_gain"):
        load_settings(cfg)


def test_record_roundtrip_and_replay(tmp_path):
    path = tmp_path / "session.jsonl"
    rec = Recorder(path)
    frames = [make_hand()] * 5 + [make_hand(pinch="index")] * 3 + [make_hand()] * 2
    for i, hand in enumerate(frames):
        rec.write(i / 30, [hand])
    rec.write(10 / 30, [])
    rec.close()

    loaded = list(read(path))
    assert len(loaded) == 11 and loaded[-1][1] == []
    assert loaded[0][1][0].landmarks == pytest.approx(frames[0].landmarks, abs=1e-5)

    cfg = tmp_path / "s.json"  # isolate from any real profile/calibration in the repo
    cfg.write_text(json.dumps({"profile_path": str(tmp_path / "none.json"),
                               "calibration_path": str(tmp_path / "none2.json")}))
    actions = [a for _, a in replay(path, cfg)]
    assert Click("left", 1) in actions
