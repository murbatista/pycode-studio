import tempfile
import unittest
from pathlib import Path

from app import build_tutor_prompt, get_workspace_lock, health, safe_filename, write_project_files


class SafeFilenameTests(unittest.TestCase):
    def test_removes_parent_path(self):
        self.assertEqual(safe_filename("../../main.py"), "main.py")

    def test_removes_windows_absolute_path(self):
        self.assertEqual(safe_filename(r"C:\\temp\\programa.py"), "programa.py")

    def test_empty_name_falls_back(self):
        self.assertEqual(safe_filename("../"), "main.py")

    def test_keeps_normal_python_filename(self):
        self.assertEqual(safe_filename("exercicio_01.py"), "exercicio_01.py")

    def test_keeps_nested_project_path(self):
        self.assertEqual(safe_filename("funcoes/calculos.py"), "funcoes/calculos.py")

    def test_rejects_too_deep_path(self):
        with self.assertRaises(ValueError):
            safe_filename("a/b/c/d/e/f/g/h/i/j/k.py")


class WorkspaceLockTests(unittest.TestCase):
    def test_lock_is_shared_only_by_the_same_workspace(self):
        self.assertIs(get_workspace_lock("workspace-a"), get_workspace_lock("workspace-a"))
        self.assertIsNot(get_workspace_lock("workspace-a"), get_workspace_lock("workspace-b"))


class ProjectFileTests(unittest.TestCase):
    def test_writes_nested_files_inside_workspace(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            workspace = Path(temp_dir)
            main_path = write_project_files(
                {"funcoes/calculos.py": "def soma(a, b):\n    return a + b\n"},
                "main.py",
                "from funcoes.calculos import soma\nprint(soma(2, 3))\n",
                workspace,
            )
            self.assertEqual(main_path.read_text(encoding="utf-8").splitlines()[-1], "print(soma(2, 3))")
            self.assertTrue((workspace / "funcoes" / "calculos.py").is_file())


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


class HealthEndpointTests(unittest.TestCase):
    def test_health_reports_server_instance_id(self):
        result = health()
        self.assertTrue(result["ok"])
        self.assertTrue(result["pythonVersion"])
        self.assertTrue(result["bootId"])
        self.assertTrue(result["model"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
