"""
Central Unit Test Runner for Navis Navigation Subsystem.
========================================================
Runs all test suites across the navigation package and outputs formatted summary.

Usage:
  python run_tests.py
"""

import sys
import os
import unittest
import time


def run_all_tests():
    print("=" * 70)
    print("        NAVIS NAVIGATION & LOCALIZATION (P3) TEST SUITE        ")
    print("=" * 70)

    # Ensure root workspace is in sys.path
    root_dir = os.path.dirname(os.path.abspath(__file__))
    if root_dir not in sys.path:
        sys.path.insert(0, root_dir)

    start_time = time.time()

    # Discover and run all tests in navigation/tests
    loader = unittest.TestLoader()
    suite = loader.discover(start_dir=os.path.join(root_dir, "navigation", "tests"), pattern="test_*.py")

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    elapsed = time.time() - start_time

    print("\n" + "=" * 70)
    print(f"Total Tests Run: {result.testsRun}")
    print(f"Successes:      {result.testsRun - len(result.failures) - len(result.errors)}")
    print(f"Failures:       {len(result.failures)}")
    print(f"Errors:         {len(result.errors)}")
    print(f"Elapsed Time:   {elapsed:.3f} seconds")
    print("=" * 70)

    if result.wasSuccessful():
        print(">>> ALL TESTS PASSED SUCCESSFULLY! <<<")
        return 0
    else:
        print(">>> SOME TESTS FAILED! <<<")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
