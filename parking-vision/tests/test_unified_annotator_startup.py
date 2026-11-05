"""Regression guard for Tkinter's root/variable initialization order.

Headless CI cannot open a GUI window; this verifies the exact startup cause of
the Windows Python 3.13 crash without requiring a display server.
"""
import inspect
import unittest

from unified_annotator import UnifiedAnnotator


class UnifiedAnnotatorStartupTests(unittest.TestCase):
    def test_root_is_created_before_all_tkinter_variables(self):
        source = inspect.getsource(UnifiedAnnotator.__init__)
        root = source.index("self.root = tk.Tk()")
        self.assertEqual(source.count("self.root = tk.Tk()"), 1)
        for declaration in (
            "self.mode = tk.StringVar(",
            "self.class_id = tk.IntVar(",
            "self.progress = tk.StringVar(",
            "self.hint = tk.StringVar(",
        ):
            with self.subTest(declaration=declaration):
                self.assertLess(root, source.index(declaration))
        self.assertIn("tk.StringVar(master=self.root", source)
        self.assertIn("tk.IntVar(master=self.root", source)


if __name__ == "__main__":
    unittest.main()
