import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from training import train_baseline
from training.features import extract_features
from training.prepare_dataset import load_dataset, split_indices


class DatasetPipelineTests(unittest.TestCase):
    def test_group_split_has_no_overlap(self):
        _, labels, groups = load_dataset()
        splits = split_indices(labels, groups)
        sets = [set(groups[index]) for index in splits.values()]
        self.assertFalse(sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
        self.assertTrue(all(set(labels[index]) == set(labels) for index in splits.values()))

    def test_feature_shape_rejects_invalid_window(self):
        with self.assertRaises(ValueError):
            extract_features(np.zeros((1, 127, 6)))

    def test_training_does_not_recreate_deleted_preprocessing_config(self):
        class FakeModel:
            def fit(self, _features, _labels):
                return self

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            models = root / "models"
            models.mkdir()
            np.savez(models / "split_indices.npz", train=np.array([0, 1]))
            x = np.zeros((2, 128, 10))
            labels = np.array(["a", "b"])
            with (patch.object(train_baseline, "ROOT", root),
                  patch.object(train_baseline, "load_dataset", return_value=(x, labels, None)),
                  patch.object(train_baseline, "extract_features", return_value=np.zeros((2, 48))),
                  patch.object(train_baseline, "RandomForestClassifier", return_value=FakeModel()),
                  patch.object(train_baseline.joblib, "dump")):
                train_baseline.train()
            self.assertFalse((models / "preprocessing_config.json").exists())
