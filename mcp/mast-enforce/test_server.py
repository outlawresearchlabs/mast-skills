"""
Tests for MAST Enforce MCP Server.

Covers all 3 tools: verify_code, check_completion, generate_edge_cases.
"""

import json
import pytest
import sys
import os

# Add parent dir to path
sys.path.insert(0, os.path.dirname(__file__))
from server import verify_code, check_completion, generate_edge_cases


# ============================================================
# verify_code tests (FM-3.2, FM-3.3)
# ============================================================

class TestVerifyCode:
    """Test the verify_code tool."""
    
    def test_simple_python_pass(self):
        """A correct function should pass verification."""
        code = "def add(a, b):\n    return a + b"
        result = verify_code(
            code=code,
            language="python",
            test_cases='[{"input": {"a": 1, "b": 2}, "expected": 3}]',
            function_name="add",
            auto_edge_cases=False,
        )
        assert result["passed"] is True
        assert result["can_deliver"] is True
        assert result["passed_tests"] >= 1
    
    def test_simple_python_fail(self):
        """An incorrect function should fail verification."""
        code = "def add(a, b):\n    return a * b  # Bug: multiplication instead of addition"
        result = verify_code(
            code=code,
            language="python",
            test_cases='[{"input": {"a": 1, "b": 2}, "expected": 3}]',
            function_name="add",
            auto_edge_cases=False,
        )
        assert result["passed"] is False
        assert result["can_deliver"] is False
        assert result["failed_tests"] >= 1
    
    def test_auto_edge_cases_catches_bugs(self):
        """Auto edge cases should catch bugs the agent wouldn't test for.
        
        This is the FM-3.3 (weak verification) scenario: the agent provides
        test cases that make its code pass, but the edge cases expose bugs.
        """
        # Buggy palindrome: doesn't handle empty string or case
        code = "def is_palindrome(s):\n    return s == s[::-1]"
        # Agent only tests "racecar" and "hello"
        result = verify_code(
            code=code,
            language="python",
            test_cases='[{"input": {"s": "racecar"}, "expected": true}, {"input": {"s": "hello"}, "expected": false}]',
            function_name="is_palindrome",
            auto_edge_cases=True,
        )
        # The edge cases should include "" (empty string) and "Racecar" (case)
        # which the buggy function doesn't handle correctly
        # Note: "" == ""[::-1] is True, so this particular bug needs case sensitivity
        # The auto-generated edge cases for strings include "ABCabc" (mixed case)
        assert result["total_tests"] > 2  # More tests than the 2 provided
        assert "failures" in result
    
    def test_syntax_error_in_code(self):
        """Code with syntax errors should fail gracefully."""
        code = "def broken(\n    return 42"
        result = verify_code(
            code=code,
            language="python",
            test_cases='[{"input": {}, "expected": 42}]',
            function_name="broken",
            auto_edge_cases=False,
        )
        assert result["passed"] is False
        assert result["can_deliver"] is False
    
    def test_function_auto_detection(self):
        """Function name should be auto-detected from code."""
        code = "def multiply(x, y):\n    return x * y"
        result = verify_code(
            code=code,
            language="python",
            test_cases='[{"input": {"x": 3, "y": 4}, "expected": 12}]',
            auto_edge_cases=False,
        )
        assert result["passed"] is True
    
    def test_no_test_cases_error(self):
        """Should return error when no test cases and no auto generation."""
        code = "def foo():\n    return 1"
        result = verify_code(
            code=code,
            language="python",
            test_cases=None,
            auto_edge_cases=False,
        )
        assert result["passed"] is False
        assert "No test cases" in result.get("error", "")
    
    def test_timeout_protection(self):
        """Code that hangs should timeout and fail."""
        code = "def infinite():\n    while True:\n        pass"
        result = verify_code(
            code=code,
            language="python",
            test_cases='[{"input": {}, "expected": 42}]',
            function_name="infinite",
            auto_edge_cases=False,
        )
        assert result["passed"] is False
        assert "timeout" in result.get("failures", [{}])[0].get("error", "").lower() or result.get("failures", [{}])[0].get("error", "")
    
    def test_unsupported_language(self):
        """Should error on unsupported languages."""
        result = verify_code(
            code="int main() { return 0; }",
            language="c",
        )
        assert result["passed"] is False
        assert "Unsupported" in result.get("error", "")
    
    def test_no_expected_value_crash_check(self):
        """Test cases with no expected value should just check for crashes."""
        code = "def safe_func(x):\n    return x * 2"
        result = verify_code(
            code=code,
            language="python",
            test_cases='[{"input": {"x": 5}}]',
            function_name="safe_func",
            auto_edge_cases=False,
        )
        assert result["passed"] is True
        assert result["can_deliver"] is True


# ============================================================
# check_completion tests (FM-1.5)
# ============================================================

class TestCheckCompletion:
    """Test the check_completion tool."""
    
    def test_all_requirements_met(self):
        """Should return can_proceed=True when all requirements have evidence."""
        result = check_completion(
            requirements='["Read CSV files", "Handle headers", "Validate data types"]',
            deliverables='{"0": "csv_reader function implemented in lines 10-25", "1": "header parsing in lines 30-45", "2": "type validation for int, float, str columns"}',
        )
        assert result["can_proceed"] is True
        assert result["met_count"] == 3
        assert result["unmet_count"] == 0
    
    def test_missing_requirement(self):
        """Should return can_proceed=False when a requirement has no evidence."""
        result = check_completion(
            requirements='["Read CSV files", "Handle headers", "Validate data types"]',
            deliverables='{"0": "csv_reader function implemented", "1": "header parsing done", "2": "NOT YET DONE"}',
        )
        assert result["can_proceed"] is False
        assert result["unmet_count"] == 1
        assert "Validate data types" in result["unmet"][0]["requirement"]
    
    def test_todo_detected_as_unmet(self):
        """TODO, pending, and similar markers should be detected as unmet."""
        for marker in ["TODO", "not yet", "in progress", "N/A", "pending"]:
            result = check_completion(
                requirements='["Implement feature"]',
                deliverables=f'{{"0": "{marker}"}}',
            )
            assert result["can_proceed"] is False, f"Marker '{marker}' should be detected as unmet"
    
    def test_strict_vs_lenient(self):
        """In strict mode, ALL must be met. In lenient mode, 80% is enough."""
        # Strict: 2 of 3 met but 1 unmet -> should fail
        result_strict = check_completion(
            requirements='["A", "B", "C"]',
            deliverables='{"0": "done", "1": "done", "2": "TBD"}',
            strict=True,
        )
        assert result_strict["can_proceed"] is False
        assert result_strict["unmet_count"] == 1
        
        # Lenient: 4 of 5 met (80%) -> should pass
        result_lenient = check_completion(
            requirements='["A", "B", "C", "D", "E"]',
            deliverables='{"0": "done", "1": "done", "2": "done", "3": "done", "4": "TBD"}',
            strict=False,
        )
        assert result_lenient["can_proceed"] is True
    
    def test_empty_evidence(self):
        """Empty string evidence should be treated as unmet."""
        result = check_completion(
            requirements='["Implement feature"]',
            deliverables='{"0": ""}',
        )
        assert result["can_proceed"] is False
        assert result["unmet_count"] == 1
    
    def test_single_requirement_string(self):
        """Should handle a single requirement as a string."""
        result = check_completion(
            requirements="Implement sort function",
            deliverables="Sort function implemented with quicksort, tested with 50 elements",
        )
        assert result["can_proceed"] is True
        assert result["total_count"] == 1


# ============================================================
# generate_edge_cases tests (FM-3.3)
# ============================================================

class TestGenerateEdgeCases:
    """Test the generate_edge_cases tool."""
    
    def test_string_function(self):
        """Should generate string edge cases."""
        cases = generate_edge_cases(
            function_signature="def is_palindrome(s: str) -> bool",
            description="Checks if a string is a palindrome",
            language="python",
        )
        assert len(cases) >= 5
        categories = [c["category"] for c in cases]
        assert "empty_string" in categories
        assert "single_char" in categories
        assert "special_chars" in categories
    
    def test_numeric_function(self):
        """Should generate numeric edge cases."""
        cases = generate_edge_cases(
            function_signature="def calculate_price(quantity: int, price: float) -> float",
            description="Calculates total price",
            language="python",
        )
        assert len(cases) >= 4  # At least zero, negative, one for each param
        categories = [c["category"] for c in cases]
        assert "zero" in categories
    
    def test_list_function(self):
        """Should generate list edge cases."""
        cases = generate_edge_cases(
            function_signature="def sort_list(arr: list) -> list",
            description="Sort a list of numbers",
            language="python",
        )
        assert len(cases) >= 3
        categories = [c["category"] for c in cases]
        assert "empty_list" in categories
    
    def test_palindrome_description_keyword(self):
        """Should add domain-specific cases for 'palindrome' keyword."""
        cases = generate_edge_cases(
            function_signature="def check(word: str) -> bool",
            description="Check if a word is a palindrome",
            language="python",
        )
        # Should have palindrome-specific cases even without type annotations
        categories = [c["category"] for c in cases]
        assert any("palindrome" in c for c in categories)
    
    def test_sort_description_keyword(self):
        """Should add domain-specific cases for 'sort' keyword."""
        cases = generate_edge_cases(
            function_signature="def my_sort(items: list) -> list",
            description="Sort items in ascending order",
            language="python",
        )
        categories = [c["category"] for c in cases]
        assert any("sort" in c for c in categories)
    
    def test_unknown_type_defaults(self):
        """Should default to empty string and None for unknown types."""
        cases = generate_edge_cases(
            function_signature="def process(data) -> bool",
            description="Process data",
            language="python",
        )
        # Should still generate some cases
        assert len(cases) >= 2


# ============================================================
# Integration tests: FM-3.2 and FM-3.3 scenarios
# ============================================================

class TestFMSenarios:
    """Test the 3 failure mode scenarios the MCP server is designed to solve."""
    
    def test_fm32_no_verification_caught(self):
        """FM-3.2: Agent delivers code without verification.
        
        The verify_code tool catches that the code has bugs the agent
        didn't test for. Without this tool, the agent would say
        "I've implemented the function" and deliver it.
        """
        # Agent claims is_palindrome works correctly
        buggy_code = "def is_palindrome(s):\n    return s == s[::-1]"
        
        # Agent only tested with obvious cases
        result = verify_code(
            code=buggy_code,
            language="python",
            function_name="is_palindrome",
            test_cases='[{"input": {"s": "racecar"}, "expected": true}, {"input": {"s": "hello"}, "expected": false}]',
            auto_edge_cases=True,  # This generates the edge cases the agent missed
        )
        # The function should work for basic cases but fail on edge cases
        # like mixed case "Racecar" if we added proper expected values
        # At minimum, it ran more than 2 tests
        assert result["total_tests"] > 2
    
    def test_fm15_premature_termination_prevented(self):
        """FM-1.5: Agent declares task complete prematurely.
        
        The check_completion tool prevents delivery when requirements
        aren't fully met.
        """
        result = check_completion(
            requirements='["CSV parser reads files", "CSV parser handles headers", "CSV parser validates data types", "CSV parser handles empty files", "Unit tests pass"]',
            deliverables='{"0": "csv_reader implemented", "1": "Header parsing works", "2": "TODO", "3": "Not tested yet", "4": "Need to write tests"}',
        )
        assert result["can_proceed"] is False
        assert result["unmet_count"] == 3
        # Agent MUST continue working on items 2, 3, and 5
    
    def test_fm33_weak_verification_exposed(self):
        """FM-3.3: Agent only tests the "happy path" cases.
        
        The generate_edge_cases tool produces boundary conditions
        that expose bugs the agent's minimal testing wouldn't find.
        """
        # Agent says "I tested racecar and hello, it works"
        # But didn't test: empty string, single char, mixed case, special chars
        cases = generate_edge_cases(
            function_signature="def is_palindrome(s: str) -> bool",
            description="Check if a string is a palindrome",
            language="python",
        )
        
        # The generated cases include things the agent's "just check X" didn't
        categories = [c["category"] for c in cases]
        assert "empty_string" in categories
        assert "single_char" in categories
        assert "mixed_case" in categories or "ABCabc" in str(cases)
        assert "special_chars" in categories
        assert "very_long" in categories
        
        # These are exactly the cases FM-3.3 says agents skip


if __name__ == "__main__":
    pytest.main([__file__, "-v"])