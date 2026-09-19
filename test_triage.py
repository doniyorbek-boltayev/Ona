import unittest

from triage import assess


def a(**kw):
    base = {"mood": 4, "symptoms": ["none"], "movement": "normal", "anxiety": 2, "meds": "yes"}
    base.update(kw)
    return base


class TriageTest(unittest.TestCase):
    def test_healthy_day_is_green(self):
        self.assertEqual(assess(a(), 30), {"level": "green", "reasons": []})

    def test_bleeding_is_red(self):
        self.assertEqual(assess(a(symptoms=["bleeding"]), 12)["level"], "red")

    def test_no_movement_red_only_after_week_24(self):
        self.assertEqual(assess(a(movement="none"), 30)["reasons"], ["no_movement"])
        self.assertEqual(assess(a(movement="none"), 18)["level"], "green")

    def test_less_movement_is_yellow(self):
        self.assertEqual(assess(a(movement="less"), 30)["level"], "yellow")

    def test_bp_thresholds(self):
        self.assertEqual(assess(a(bp={"sys": 120, "dia": 80}), 30)["level"], "green")
        self.assertEqual(assess(a(bp={"sys": 142, "dia": 85}), 30)["reasons"], ["bp_high"])
        self.assertEqual(assess(a(bp={"sys": 150, "dia": 112}), 30)["reasons"], ["bp_severe"])

    def test_bp_typo_is_ignored(self):
        self.assertEqual(assess(a(bp={"sys": 1200, "dia": 80}), 30)["level"], "green")
        self.assertEqual(assess(a(bp={"sys": "", "dia": ""}), 30)["level"], "green")

    def test_preeclampsia_combination(self):
        r = assess(a(symptoms=["headache", "swelling"], headache_severity="severe"), 32)
        self.assertEqual(r["level"], "red")
        self.assertEqual(r["reasons"][0], "preeclampsia_signs")
        r = assess(a(symptoms=["vision"], bp={"sys": 145, "dia": 95}), 32)
        self.assertIn("preeclampsia_signs", r["reasons"])

    def test_single_warning_symptom_is_yellow(self):
        self.assertEqual(assess(a(symptoms=["swelling"]), 32)["level"], "yellow")
        self.assertEqual(assess(a(symptoms=["headache"], headache_severity="mild"), 32)["level"], "green")

    def test_contractions_depend_on_week(self):
        self.assertEqual(assess(a(symptoms=["contractions"]), 33)["level"], "red")
        self.assertEqual(assess(a(symptoms=["contractions"]), 39)["level"], "yellow")

    def test_fever_escalates_with_pain(self):
        self.assertEqual(assess(a(symptoms=["fever"]), 20)["level"], "yellow")
        self.assertEqual(assess(a(symptoms=["fever", "urination"]), 20)["level"], "red")

    def test_rapid_weight_gain(self):
        history = [a(weight=70.0), a(weight=69.8), a(weight=69.5)]
        self.assertEqual(assess(a(weight=72.1), 30, history)["reasons"], ["rapid_weight_gain"])
        self.assertEqual(assess(a(weight=70.4), 30, history)["level"], "green")

    def test_streaks_need_three_days(self):
        low = a(mood=2)
        self.assertEqual(assess(low, 30, [low])["level"], "green")
        self.assertEqual(assess(low, 30, [low, low])["reasons"], ["low_mood_streak"])
        self.assertEqual(assess(a(meds="no"), 30, [a(meds="no"), a(meds="no")])["reasons"], ["missed_meds_streak"])

    def test_red_reasons_sorted_first(self):
        r = assess(a(symptoms=["dizziness", "bleeding"]), 20)
        self.assertEqual(r["reasons"], ["bleeding", "dizziness"])


if __name__ == "__main__":
    unittest.main()
