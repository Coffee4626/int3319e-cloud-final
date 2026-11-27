import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from app.domain import TrainingRequest
from app.tasks.factory import default_factory
from app.tasks.tabular import AutoTabularTask, ClassificationTask, RegressionTask


class TaskTests(unittest.TestCase):
    def test_factory_supports_extensions_and_rejects_unknown_or_duplicate_names(self):
        factory = default_factory()
        self.assertIsInstance(factory.create("classification"), ClassificationTask)
        factory.register("custom", RegressionTask)
        self.assertIsInstance(factory.create("custom"), RegressionTask)
        for name in ("custom", ""):
            with self.assertRaises(ValueError):
                factory.register(name, RegressionTask)
        for name in ("app.tasks.evil", None, [], {}):
            with self.assertRaises(ValueError):
                factory.create(name)

    def test_classification_handles_binary_and_multiclass_even_with_numeric_labels(self):
        task = ClassificationTask()
        self.assertEqual(task.problem_type([0, 1, 0]), "binary")
        self.assertEqual(task.problem_type(list(range(25))), "multiclass")
        with self.assertRaises(ValueError):
            task.validate_training(TrainingRequest("x,y\n1,a\n2,a", "y"))

    def test_regression_accepts_numbers_and_rejects_nonfinite_targets(self):
        task = RegressionTask()
        task.validate_training(TrainingRequest("x,y\n1,-2.5\n2,3e2", "y"))
        for value in ("cat", "NaN", "inf", "-inf", ""):
            with self.subTest(value=value), self.assertRaises(ValueError):
                task.validate_training(TrainingRequest(f"x,y\n1,{value}\n2,4", "y"))

    def test_malformed_csv_is_rejected(self):
        for csv in ("x,y\n1,2,3\n4,5", "x,y\n1\n2,3", "x,x,y\n1,2,3\n4,5,6", "y\n1\n2"):
            with self.subTest(csv=csv), self.assertRaises(ValueError):
                AutoTabularTask().validate_training(TrainingRequest(csv, "y"))

    def test_training_selects_correct_autogluon_problem_type(self):
        for task, labels, expected in (
            (AutoTabularTask(), [1, 2], None),
            (ClassificationTask(), [0, 1], "binary"),
            (ClassificationTask(), [1, 2, 3], "multiclass"),
            (RegressionTask(), [0, 1], "regression"),
        ):
            with self.subTest(task=type(task).__name__, expected=expected):
                fake = MagicMock()
                fake.TabularDataset.return_value = {"y": labels}
                fake.TabularPredictor.return_value.leaderboard.return_value.to_json.return_value = '[]'
                with patch.dict(sys.modules, {"autogluon": MagicMock(), "autogluon.tabular": fake}):
                    task.train(Path("data.csv"), Path("model"), {"target": "y", "time_limit": 30})
                self.assertEqual(fake.TabularPredictor.call_args.kwargs["problem_type"], expected)
                self.assertEqual(fake.TabularPredictor.return_value.fit.call_args.kwargs["time_limit"], 30)

    def test_prediction_checks_each_row_for_missing_features(self):
        model = MagicMock()
        model.feature_metadata_in.get_features.return_value = ["x", "z"]
        model.predict.return_value.to_json.return_value = "[1.5, 3.0]"
        with patch.dict(sys.modules, {"pandas": MagicMock()}):
            with self.assertRaisesRegex(ValueError, "Missing features: z"):
                RegressionTask().predict(model, [{"x": 1, "z": 2}, {"x": 3}])
            result = RegressionTask().predict(model, [{"x": 1, "z": 2}, {"x": 3, "z": 4}])
        self.assertEqual(result, {"predictions": [1.5, 3.0]})

    def test_prediction_input_validation(self):
        for rows in (None, [], [1], [{}] * 101):
            with self.subTest(rows=rows), self.assertRaises(ValueError):
                ClassificationTask().validate_prediction({"rows": rows})


if __name__ == "__main__":
    unittest.main()
