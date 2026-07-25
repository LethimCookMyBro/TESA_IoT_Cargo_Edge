import json
import unittest
from pathlib import Path

import numpy as np

from cargo.controller import MissionController
from cargo.inference import _features
from cargo.sources import DatasetReplaySource
from training.features import extract_features
from training.prepare_dataset import load_dataset


class CargoIntegrationTests(unittest.TestCase):
    def test_real_dataset_window_reaches_model_and_decision(self):
        root = Path(__file__).resolve().parents[1]
        labels = {int(key): value for key, value in json.loads((root / "models" / "label_mapping.json").read_text()).items()}
        source = DatasetReplaySource(root / "dataset", labels)
        controller = MissionController(root)
        controller.start()
        window, point = source.window(0)
        state = controller.process_dataset_window(window, point.ground_truth or "unknown", "A1")
        self.assertIn(state["decision"]["action"], {"MOVE", "SLOW_DOWN", "SAFE_STOP", "HOLD_UNCERTAIN"})

    def test_inference_and_training_extract_identical_features(self):
        root = Path(__file__).resolve().parents[1]
        labels = {int(key): value for key, value in json.loads((root / "models" / "label_mapping.json").read_text()).items()}
        window, _ = DatasetReplaySource(root / "dataset", labels).window(0)
        x, _, _ = load_dataset()
        np.testing.assert_array_equal(_features(window), extract_features(x[:1, :, 4:10]))
