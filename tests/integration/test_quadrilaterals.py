import os
import unittest
from tempfile import TemporaryDirectory
from deepdiff import DeepDiff 

from extractor import quadrilaterals
from .common import temp_dir_prefix, load_file


class TestQuadrilaterals(unittest.TestCase):

    def setUp(self):
        self.data_dir = os.path.join("tests", "integration", "data")
        self.work_dir = TemporaryDirectory(prefix=temp_dir_prefix)
        self.settings = {
            "min_iou": 0.9
        }
        self.frames_root = os.path.join(self.data_dir, "splitted")
        self.inference_root = os.path.join(self.data_dir, "segmented")
        self.tracks_root = os.path.join(self.data_dir, "tracking")
        self.output_dir = self.work_dir.name
        self.ir_or_rgb = "ir"

        # where to load files with desired output format from
        self.ground_truth_dir = os.path.join(self.data_dir, "quadrilaterals")

    def test_run(self):
        quadrilaterals.run(
            self.frames_root, 
            self.inference_root, 
            self.tracks_root,
            self.output_dir, 
            self.ir_or_rgb,
            **self.settings)

        # check if outputs equal ground truth
        file_name = "quadrilaterals.pkl"
        content, content_ground_truth = load_file(
            self.output_dir, 
            self.ground_truth_dir, 
            file_name)

        self.assertEqual(
            DeepDiff(
                content_ground_truth, 
                content,
                math_epsilon=1e-5
            ), {},
            "{} differs from ground truth".format(file_name)
        )

    def tearDown(self):
        self.work_dir.cleanup()