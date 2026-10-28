import unittest

from app import build_tutor_prompt, safe_filename


class SafeFilenameTests(unittest.TestCase):
    def test_removes_parent_path(self):
        self.assertEqual(safe_filename("../../main.py"), "main.py")

    def test_removes_windows_path(self):
        self.assertEqual(safe_filename(r"C:\\temp\\programa.py"), "programa.py")

    def test_empty_name_falls_back(self):
        self.assertEqual(safe_filename("../"), "main.py")

    def test_keeps_normal_python_filename(self):
        self.assertEqual(safe_filename("exercicio_01.py"), "exercicio_01.py")


class TutorPromptTests(unittest.TestCase):
    def test_explain_mode_includes_code(self):
        prompt = build_tutor_prompt("explain", "Explique", "print(1 + 1)", "")
        self.assertIn("linha por linha", prompt)
        self.assertIn("print(1 + 1)", prompt)

    def test_debug_mode_includes_error(self):
        prompt = build_tutor_prompt("debug", "", "print(nome)", "NameError: nome")
        self.assertIn("Investigue os erros", prompt)
        self.assertIn("NameError: nome", prompt)

    def test_unknown_mode_falls_back_to_question(self):
        prompt = build_tutor_prompt("other", "O que é len?", "", "")
        self.assertIn("O que é len?", prompt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
