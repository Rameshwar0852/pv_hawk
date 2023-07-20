import os
import unittest
from tempfile import TemporaryDirectory
from deepdiff import DeepDiff 

from extractor import tracking
from .common import temp_dir_prefix, load_file


class TestTracking(unittest.TestCase):

    def setUp(self):
        self.data_dir = os.path.join("tests", "integration", "data")
        self.work_dir = TemporaryDirectory(prefix=temp_dir_prefix)
        self.settings = {
            "motion_model": "homography",
            "orb_nfeatures": 5000,
            "orb_fast_thres": 12,
            "orb_scale_factor": 1.2,
            "orb_nlevels": 8,
            "match_distance_thres": 20.0,
            "max_distance": 60,
            "output_video_fps": 8.0,
            "deterministic_track_ids": True
        }
        self.frames_root = os.path.join(self.data_dir, "splitted")
        self.inference_root = os.path.join(self.data_dir, "segmented")
        self.output_dir = self.work_dir.name
        self.ir_or_rgb = "ir"

        # where to load files with desired output format from
        self.ground_truth_dir = os.path.join(self.data_dir, "tracking")

    def test_run(self):
        tracking.run(
            self.frames_root, 
            self.inference_root, 
            self.output_dir,
            self.ir_or_rgb,
            **self.settings)

        # check if outputs equal ground truth
        file_name = "tracks.csv"
        content, content_ground_truth = load_file(
            self.output_dir, 
            self.ground_truth_dir, 
            file_name)

        # Note: Test will fail when order of rows in tracks is permutated
        self.assertEqual(
            DeepDiff(
                content_ground_truth, 
                content
            ), {},
            "{} differs from ground truth".format(file_name)
        )        

    def tearDown(self):
        self.work_dir.cleanup()