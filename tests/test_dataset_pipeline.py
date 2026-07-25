import unittest

import numpy as np

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
