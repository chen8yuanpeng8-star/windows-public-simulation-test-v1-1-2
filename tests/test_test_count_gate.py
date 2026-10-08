import unittest

from simtest.test_gate import GateResult, evaluate_python_counts, evaluate_powershell_counts


class TestCountGateTests(unittest.TestCase):
    def test_zero_python_tests_is_failure(self):
        result = evaluate_python_counts(run=0, failures=0, errors=0, skipped=0, minimum=17)
        self.assertFalse(result.full_pass)
        self.assertIn("below minimum", result.reasons[0])

    def test_skipped_python_test_blocks_full_pass(self):
        result = evaluate_python_counts(run=17, failures=0, errors=0, skipped=1, minimum=17)
        self.assertFalse(result.full_pass)
        self.assertEqual(result.passed, 16)
        self.assertEqual(result.skipped, 1)

    def test_complete_python_suite_passes_with_exact_counts(self):
        result = evaluate_python_counts(run=17, failures=0, errors=0, skipped=0, minimum=17)
        self.assertEqual(result, GateResult(True, 17, 0, 0, ()))

    def test_zero_powershell_assertions_is_failure(self):
        result = evaluate_powershell_counts(passed=0, failed=0, minimum=5)
        self.assertFalse(result.full_pass)
        self.assertIn("below minimum", result.reasons[0])

    def test_powershell_failure_and_minimum_are_independent(self):
        result = evaluate_powershell_counts(passed=5, failed=1, minimum=5)
        self.assertFalse(result.full_pass)
        self.assertEqual(result.passed, 5)
        self.assertEqual(result.failed, 1)


if __name__ == "__main__":
    unittest.main()
