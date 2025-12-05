# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for code_mode module."""

import pytest
from awslabs.aws_api_mcp_server.code_mode import (
    AwsOperationError,
    analyze_code,
    check_restricted_operations,
    detect_loops_with_aws,
    execute_aws_python,
    extract_aws_operations,
    validate_syntax,
)


class TestValidateSyntax:
    """Tests for validate_syntax function."""

    def test_valid_python_code(self):
        """Valid Python code should pass validation."""
        code = """
x = 1
y = 2
print(x + y)
"""
        is_valid, error = validate_syntax(code)
        assert is_valid is True
        assert error is None

    def test_syntax_error_detected(self):
        """Syntax errors should be detected with line number."""
        code = """
x = 1
y = 
print(x)
"""
        is_valid, error = validate_syntax(code)
        assert is_valid is False
        assert 'SyntaxError' in error
        assert 'line' in error.lower()

    def test_empty_code(self):
        """Empty code should be valid."""
        is_valid, error = validate_syntax('')
        assert is_valid is True
        assert error is None


class TestCheckRestrictedOperations:
    """Tests for check_restricted_operations function."""

    def test_safe_code_passes(self):
        """Safe code without restricted operations should pass."""
        code = """
result = aws("ec2 describe-instances")
print(result)
"""
        is_safe, error = check_restricted_operations(code)
        assert is_safe is True
        assert error is None

    def test_import_os_blocked(self):
        """Import of os module should be blocked."""
        code = "import os"
        is_safe, error = check_restricted_operations(code)
        assert is_safe is False
        assert "os" in error
        assert "not allowed" in error

    def test_import_subprocess_blocked(self):
        """Import of subprocess module should be blocked."""
        code = "import subprocess"
        is_safe, error = check_restricted_operations(code)
        assert is_safe is False
        assert "subprocess" in error

    def test_from_import_blocked(self):
        """From import of restricted module should be blocked."""
        code = "from os import path"
        is_safe, error = check_restricted_operations(code)
        assert is_safe is False
        assert "os" in error

    def test_open_function_blocked(self):
        """Use of open() function should be blocked."""
        code = "f = open('file.txt', 'r')"
        is_safe, error = check_restricted_operations(code)
        assert is_safe is False
        assert "open" in error

    def test_eval_blocked(self):
        """Use of eval() function should be blocked."""
        code = "eval('1+1')"
        is_safe, error = check_restricted_operations(code)
        assert is_safe is False
        assert "eval" in error

    def test_exec_blocked(self):
        """Use of exec() function should be blocked."""
        code = "exec('x=1')"
        is_safe, error = check_restricted_operations(code)
        assert is_safe is False
        assert "exec" in error

    def test_dunder_import_blocked(self):
        """Use of __import__ should be blocked."""
        code = "__import__('os')"
        is_safe, error = check_restricted_operations(code)
        assert is_safe is False
        assert "__import__" in error

    def test_os_path_blocked(self):
        """Use of os.path should be blocked."""
        code = "x = os.path.exists('/tmp')"
        is_safe, error = check_restricted_operations(code)
        assert is_safe is False
        assert "os" in error

    def test_pathlib_blocked(self):
        """Use of pathlib should be blocked."""
        code = "from pathlib import Path"
        is_safe, error = check_restricted_operations(code)
        assert is_safe is False
        assert "pathlib" in error


class TestExtractAwsOperations:
    """Tests for extract_aws_operations function."""

    def test_single_operation(self):
        """Single AWS operation should be extracted."""
        code = 'result = aws("ec2 describe-instances")'
        operations = extract_aws_operations(code)
        assert operations == ["ec2 describe-instances"]

    def test_multiple_operations(self):
        """Multiple AWS operations should all be extracted."""
        code = '''
instances = aws("ec2 describe-instances")
buckets = aws("s3 list-buckets")
'''
        operations = extract_aws_operations(code)
        assert len(operations) == 2
        assert "ec2 describe-instances" in operations
        assert "s3 list-buckets" in operations

    def test_single_quotes(self):
        """AWS operations with single quotes should be extracted."""
        code = "result = aws('ec2 describe-instances')"
        operations = extract_aws_operations(code)
        assert operations == ["ec2 describe-instances"]

    def test_no_operations(self):
        """Code without AWS operations should return empty list."""
        code = "x = 1 + 2"
        operations = extract_aws_operations(code)
        assert operations == []

    def test_operation_with_parameters(self):
        """AWS operations with parameters should be extracted."""
        code = 'result = aws("ec2 describe-instances --region us-east-1")'
        operations = extract_aws_operations(code)
        assert operations == ["ec2 describe-instances --region us-east-1"]


class TestDetectLoopsWithAws:
    """Tests for detect_loops_with_aws function."""

    def test_loop_with_aws_detected(self):
        """Loop containing AWS operations should generate warning."""
        code = '''
for region in regions:
    result = aws("ec2 describe-instances")
'''
        warnings = detect_loops_with_aws(code)
        assert len(warnings) == 1
        assert "Loop detected" in warnings[0]

    def test_while_loop_with_aws_detected(self):
        """While loop containing AWS operations should generate warning."""
        code = '''
while True:
    result = aws("ec2 describe-instances")
    break
'''
        warnings = detect_loops_with_aws(code)
        assert len(warnings) == 1
        assert "Loop detected" in warnings[0]

    def test_no_loop_no_warning(self):
        """Code without loops should not generate warnings."""
        code = 'result = aws("ec2 describe-instances")'
        warnings = detect_loops_with_aws(code)
        assert warnings == []

    def test_loop_without_aws_no_warning(self):
        """Loop without AWS operations should not generate warnings."""
        code = '''
for i in range(10):
    print(i)
'''
        warnings = detect_loops_with_aws(code)
        assert warnings == []


class TestAnalyzeCode:
    """Tests for analyze_code function."""

    def test_valid_code_analysis(self):
        """Valid code should be analyzed correctly."""
        code = 'result = aws("ec2 describe-instances")'
        analysis = analyze_code(code)
        assert analysis["valid"] is True
        assert analysis["operation_count"] == 1
        assert "ec2 describe-instances" in analysis["operations"]

    def test_syntax_error_in_analysis(self):
        """Syntax errors should be reported in analysis."""
        code = "x = "
        analysis = analyze_code(code)
        assert analysis["valid"] is False
        assert len(analysis["warnings"]) > 0
        assert "SyntaxError" in analysis["warnings"][0]

    def test_security_error_in_analysis(self):
        """Security errors should be reported in analysis."""
        code = "import os"
        analysis = analyze_code(code)
        assert analysis["valid"] is False
        assert len(analysis["warnings"]) > 0
        assert "Security error" in analysis["warnings"][0]

    def test_loop_warning_in_analysis(self):
        """Loop warnings should be included in analysis."""
        code = '''
for region in regions:
    result = aws("ec2 describe-instances")
'''
        analysis = analyze_code(code)
        assert analysis["valid"] is True
        assert any("Loop detected" in w for w in analysis["warnings"])


class TestExecuteAwsPython:
    """Tests for execute_aws_python function."""

    @pytest.mark.asyncio
    async def test_valid_code_execution(self):
        """Valid code should execute successfully."""
        code = """
x = 1 + 2
print(x)
"""
        result = await execute_aws_python(code)
        assert result["status"] == "success"
        assert "3" in result["output"]

    @pytest.mark.asyncio
    async def test_aws_function_available(self):
        """aws() function should be available in sandbox."""
        code = 'result = aws("ec2 describe-instances")'
        result = await execute_aws_python(code)
        assert result["status"] == "success"
        assert "ec2 describe-instances" in result["operations"]

    @pytest.mark.asyncio
    async def test_aws_executor_called(self):
        """Custom aws_executor should be called."""
        mock_response = {"Reservations": []}
        
        def mock_executor(command):
            return mock_response
        
        code = '''
result = aws("ec2 describe-instances")
print(len(result.get("Reservations", [])))
'''
        result = await execute_aws_python(code, aws_executor=mock_executor)
        assert result["status"] == "success"
        assert "0" in result["output"]

    @pytest.mark.asyncio
    async def test_print_output_captured(self):
        """print() output should be captured."""
        code = """
print("Hello")
print("World")
"""
        result = await execute_aws_python(code)
        assert result["status"] == "success"
        assert "Hello" in result["output"]
        assert "World" in result["output"]

    @pytest.mark.asyncio
    async def test_syntax_error_returns_validation_error(self):
        """Syntax errors should return validation_error status."""
        code = "x = "
        result = await execute_aws_python(code)
        assert result["status"] == "validation_error"
        assert "SyntaxError" in result["error"]

    @pytest.mark.asyncio
    async def test_restricted_import_returns_validation_error(self):
        """Restricted imports should return validation_error status."""
        code = "import os"
        result = await execute_aws_python(code)
        assert result["status"] == "validation_error"
        assert "Security error" in result["error"]

    @pytest.mark.asyncio
    async def test_restricted_function_returns_validation_error(self):
        """Restricted functions should return validation_error status."""
        code = "open('file.txt')"
        result = await execute_aws_python(code)
        assert result["status"] == "validation_error"
        assert "Security error" in result["error"]

    @pytest.mark.asyncio
    async def test_dry_run_mode(self):
        """Dry run mode should analyze without executing."""
        code = 'result = aws("ec2 describe-instances")'
        result = await execute_aws_python(code, dry_run=True)
        assert result["status"] == "success"
        assert "analysis" in result
        assert result["analysis"]["operation_count"] == 1
        assert result["analysis"]["valid"] is True

    @pytest.mark.asyncio
    async def test_dry_run_with_loop_warning(self):
        """Dry run should include loop warnings."""
        code = '''
for region in ["us-east-1", "us-west-2"]:
    result = aws("ec2 describe-instances")
'''
        result = await execute_aws_python(code, dry_run=True)
        assert result["status"] == "success"
        assert "analysis" in result
        assert any("Loop detected" in w for w in result["analysis"]["warnings"])

    @pytest.mark.asyncio
    async def test_control_flow_support(self):
        """Control flow statements should work."""
        code = """
x = 5
if x > 3:
    print("greater")
else:
    print("lesser")
"""
        result = await execute_aws_python(code)
        assert result["status"] == "success"
        assert "greater" in result["output"]

    @pytest.mark.asyncio
    async def test_loop_execution(self):
        """Loops should execute correctly."""
        code = """
total = 0
for i in range(5):
    total += i
print(total)
"""
        result = await execute_aws_python(code)
        assert result["status"] == "success"
        assert "10" in result["output"]

    @pytest.mark.asyncio
    async def test_data_structure_support(self):
        """Data structures should be supported."""
        code = """
data = {"key": "value", "numbers": [1, 2, 3]}
print(data["key"])
print(len(data["numbers"]))
"""
        result = await execute_aws_python(code)
        assert result["status"] == "success"
        assert "value" in result["output"]
        assert "3" in result["output"]

    @pytest.mark.asyncio
    async def test_list_comprehension(self):
        """List comprehensions should work."""
        code = """
numbers = [1, 2, 3, 4, 5]
evens = [n for n in numbers if n % 2 == 0]
print(evens)
"""
        result = await execute_aws_python(code)
        assert result["status"] == "success"
        assert "[2, 4]" in result["output"]

    @pytest.mark.asyncio
    async def test_exception_handling_try_except(self):
        """Try-except blocks should work."""
        # Use Exception base class since ZeroDivisionError is not in sandbox builtins
        code = """
try:
    x = 1 / 0
except Exception:
    print("caught division error")
"""
        result = await execute_aws_python(code)
        assert result["status"] == "success"
        assert "caught division error" in result["output"]

    @pytest.mark.asyncio
    async def test_uncaught_exception_returns_error(self):
        """Uncaught exceptions should return error status."""
        code = "x = 1 / 0"
        result = await execute_aws_python(code)
        assert result["status"] == "error"
        assert "ZeroDivisionError" in result["error"]

    @pytest.mark.asyncio
    async def test_aws_operation_error_handling(self):
        """AWS operation errors should be catchable."""
        def failing_executor(command):
            raise AwsOperationError("Access denied", command)
        
        code = """
try:
    result = aws("ec2 describe-instances")
except Exception as e:
    print(f"Error: {e}")
"""
        result = await execute_aws_python(code, aws_executor=failing_executor)
        assert result["status"] == "success"
        assert "Error:" in result["output"]

    @pytest.mark.asyncio
    async def test_aws_operation_error_uncaught(self):
        """Uncaught AWS operation errors should return error status."""
        def failing_executor(command):
            raise AwsOperationError("Access denied", command)
        
        code = 'result = aws("ec2 describe-instances")'
        result = await execute_aws_python(code, aws_executor=failing_executor)
        assert result["status"] == "error"
        assert "Access denied" in result["error"]

    @pytest.mark.asyncio
    async def test_data_filtering(self):
        """Data filtering should work correctly."""
        mock_response = {
            "Reservations": [
                {"Instances": [{"State": {"Name": "running"}, "InstanceId": "i-1"}]},
                {"Instances": [{"State": {"Name": "stopped"}, "InstanceId": "i-2"}]},
            ]
        }
        
        def mock_executor(command):
            return mock_response
        
        code = '''
instances = aws("ec2 describe-instances")
running = [i for r in instances.get("Reservations", []) 
           for i in r.get("Instances", []) 
           if i.get("State", {}).get("Name") == "running"]
print(f"Running: {len(running)}")
'''
        result = await execute_aws_python(code, aws_executor=mock_executor)
        assert result["status"] == "success"
        assert "Running: 1" in result["output"]

    @pytest.mark.asyncio
    async def test_nested_structure_processing(self):
        """Nested structure processing should work."""
        mock_response = {
            "Buckets": [
                {"Name": "bucket1", "CreationDate": "2023-01-01"},
                {"Name": "bucket2", "CreationDate": "2023-02-01"},
            ]
        }
        
        def mock_executor(command):
            return mock_response
        
        code = '''
response = aws("s3 list-buckets")
names = [b["Name"] for b in response.get("Buckets", [])]
print(names)
'''
        result = await execute_aws_python(code, aws_executor=mock_executor)
        assert result["status"] == "success"
        assert "bucket1" in result["output"]
        assert "bucket2" in result["output"]

    @pytest.mark.asyncio
    async def test_multiple_aws_operations(self):
        """Multiple AWS operations should be tracked."""
        def mock_executor(command):
            return {}
        
        code = '''
result1 = aws("ec2 describe-instances")
result2 = aws("s3 list-buckets")
'''
        result = await execute_aws_python(code, aws_executor=mock_executor)
        assert result["status"] == "success"
        assert len(result["operations"]) == 2
        assert "ec2 describe-instances" in result["operations"]
        assert "s3 list-buckets" in result["operations"]

    @pytest.mark.asyncio
    async def test_execution_time_tracked(self):
        """Execution time should be tracked."""
        code = "x = 1"
        result = await execute_aws_python(code)
        assert "execution_time" in result
        assert result["execution_time"] >= 0

    @pytest.mark.asyncio
    async def test_builtin_functions_available(self):
        """Builtin functions should be available."""
        code = """
numbers = [3, 1, 4, 1, 5]
print(len(numbers))
print(sum(numbers))
print(min(numbers))
print(max(numbers))
print(sorted(numbers))
"""
        result = await execute_aws_python(code)
        assert result["status"] == "success"
        assert "5" in result["output"]  # len
        assert "14" in result["output"]  # sum
        assert "1" in result["output"]  # min
        assert "[1, 1, 3, 4, 5]" in result["output"]  # sorted

    @pytest.mark.asyncio
    async def test_type_constructors_available(self):
        """Type constructors should be available."""
        code = """
d = dict(a=1, b=2)
l = list(range(3))
s = set([1, 2, 2, 3])
t = tuple([1, 2, 3])
print(d)
print(l)
print(len(s))
print(t)
"""
        result = await execute_aws_python(code)
        assert result["status"] == "success"
        assert "{'a': 1, 'b': 2}" in result["output"]
        assert "[0, 1, 2]" in result["output"]
        assert "3" in result["output"]  # set length
        assert "(1, 2, 3)" in result["output"]
