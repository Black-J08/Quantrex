"""Tests for the Zerodha example script."""

from __future__ import annotations

import ast
from pathlib import Path

EXAMPLE_PATH = Path(__file__).resolve().parents[2] / "examples" / "zerodha_example.py"


class TestZerodhaExample:
    """Tests for the Zerodha example script."""

    def test_example_file_exists(self) -> None:
        """Test that the example file exists."""
        assert EXAMPLE_PATH.exists()

    def test_example_is_valid_python(self) -> None:
        """Test that the example file is valid Python."""
        source = EXAMPLE_PATH.read_text()
        ast.parse(source)

    def test_example_has_main_function(self) -> None:
        """Test that the example defines a main async function."""
        source = EXAMPLE_PATH.read_text()
        tree = ast.parse(source)

        has_main = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "main":
                has_main = True
                break

        assert has_main, "Example should define a main() function"

    def test_example_has_if_main_block(self) -> None:
        """Test that the example has an if __name__ == '__main__' block."""
        source = EXAMPLE_PATH.read_text()
        tree = ast.parse(source)

        has_main_block = False
        for node in ast.walk(tree):
            if isinstance(node, ast.If):
                test = node.test
                if (
                    isinstance(test, ast.Compare)
                    and isinstance(test.left, ast.Name)
                    and test.left.id == "__name__"
                ):
                    has_main_block = True
                    break

        assert has_main_block, "Example should have if __name__ == '__main__' block"

    def test_example_imports_resolve(self) -> None:
        """Test that the example's imports can be resolved."""
        source = EXAMPLE_PATH.read_text()
        tree = ast.parse(source)

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        # Verify key imports are present
        assert any("quantrex.core.broker.zerodha.session.session" in imp for imp in imports)
        assert any("quantrex.core.data.historical.zerodha_provider" in imp for imp in imports)
        assert any("quantrex.core.models.timeframe" in imp for imp in imports)
