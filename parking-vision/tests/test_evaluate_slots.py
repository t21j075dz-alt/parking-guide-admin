"""目視ラベルによる空き誤判定評価のテスト。"""
import unittest
from evaluate_slots import evaluate


class EvaluateSlotsTest(unittest.TestCase):
    def test_false_available_is_counted_and_unknown_reduces_coverage(self):
        pred = [
            {"動画の時刻(秒)":"0", "駐車枠ID":"space_001", "判定コード":"occupied"},
            {"動画の時刻(秒)":"4", "駐車枠ID":"space_001", "判定コード":"available"},
            {"動画の時刻(秒)":"6", "駐車枠ID":"space_001", "判定コード":"unknown"},
        ]
        truth = [
            {"動画の時刻(秒)":"1", "駐車枠ID":"space_001", "正解コード":"occupied"},
            {"動画の時刻(秒)":"5", "駐車枠ID":"space_001", "正解コード":"occupied"},
            {"動画の時刻(秒)":"8", "駐車枠ID":"space_001", "正解コード":"occupied"},
        ]
        result, detail = evaluate(pred, truth)
        self.assertEqual(result["false_available_count"], 1)
        self.assertEqual(result["evaluated"], 3)
        self.assertEqual(result["coverage_excluding_unknown"], round(2/3,4))
        self.assertEqual([row["予測コード"] for row in detail],
                         ["occupied","available","unknown"])

    def test_truth_unknown_not_scored(self):
        result,_ = evaluate(
            [{"動画の時刻(秒)":"0", "駐車枠ID":"space_001", "判定コード":"available"}],
            [{"動画の時刻(秒)":"0", "駐車枠ID":"space_001", "正解コード":"unknown"}])
        self.assertEqual(result["evaluated"], 0)
        self.assertIsNone(result["exact_accuracy_including_unknown"])

    def test_invalid_truth_raises(self):
        with self.assertRaises(ValueError):
            evaluate([], [{"駐車枠ID":"space_001","正解コード":"free"}])


if __name__ == "__main__":
    unittest.main()
