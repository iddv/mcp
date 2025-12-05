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

"""Code Mode: Execute Python code with AWS operations in a sandboxed environment."""

from __future__ import annotations

import ast
import asyncio
import re
import time
from io import StringIO
from typing import Any, Callable

import nest_asyncio
from loguru import logger

# Apply nest_asyncio to allow nested event loops
# This is the standard solution for calling async code from sync code
# when already inside an async context (e.g., exec() calling async aws())
nest_asyncio.apply()


# Restricted modules that cannot be imported
RESTRICTED_MODULES = frozenset([
    'os', 'sys', 'subprocess', 'socket', 'urllib', 'requests',
    '__import__', 'importlib', 'builtins', 'pathlib', 'shutil',
    'tempfile', 'glob', 'fnmatch', 'linecache', 'pickle', 'shelve',
    'marshal', 'dbm', 'sqlite3', 'ctypes', 'multiprocessing',
    'threading', 'concurrent', 'asyncio', 'signal', 'mmap',
])

# Restricted function names that cannot be used
RESTRICTED_FUNCTIONS = frozenset([
    'open', 'exec', 'eval', 'compile', '__import__', 'globals',
    'locals', 'vars', 'dir', 'getattr', 'setattr', 'delattr',
    'hasattr', 'input', 'breakpoint', 'memoryview', 'object',
])


# Regex pattern to extract AWS operations from code
AWS_OPERATION_PATTERN = re.compile(r'aws\(["\']([^"\']+)["\']\)')

# Regex pattern to detect loops
LOOP_PATTERN = re.compile(r'\b(for|while)\b')

# Default execution timeout in seconds
DEFAULT_TIMEOUT = 30

# Maximum number of AWS operations per execution
MAX_AWS_OPERATIONS = 50


class CodeModeError(Exception):
    """Base exception for code mode errors."""
    pass


class ValidationError(CodeModeError):
    """Raised when code validation fails."""
    pass


class SecurityError(CodeModeError):
    """Raised when code attempts restricted operations."""
    pass


class ExecutionError(CodeModeError):
    """Raised when code execution fails."""
    pass


class TimeoutError(CodeModeError):
    """Raised when code execution times out."""
    pass


class AwsOperationError(CodeModeError):
    """Raised when an AWS operation fails."""

    def __init__(self, message: str, operation: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.operation = operation
        self.details = details or {}


def validate_syntax(code: str) -> tuple[bool, str | None]:
    """Validate Python syntax using ast.parse().

    Args:
        code: Python code string to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        ast.parse(code)
        return True, None
    except SyntaxError as e:
        line_info = f" (line {e.lineno})" if e.lineno else ""
        return False, f"SyntaxError: {e.msg}{line_info}"


def check_restricted_operations(code: str) -> tuple[bool, str | None]:
    """Check for restricted imports and function calls.

    Args:
        code: Python code string to check

    Returns:
        Tuple of (is_safe, error_message)
    """
    # Check for import statements
    for module in RESTRICTED_MODULES:
        # Check for 'import module' or 'from module import'
        import_pattern = rf'\bimport\s+{re.escape(module)}\b'
        from_pattern = rf'\bfrom\s+{re.escape(module)}\b'
        if re.search(import_pattern, code) or re.search(from_pattern, code):
            return False, f"Security error: import of '{module}' module is not allowed"

    # Check for restricted function calls
    for func in RESTRICTED_FUNCTIONS:
        # Match function calls like 'open(' but not 'myopen(' or 'open_file('
        func_pattern = rf'(?<![a-zA-Z_]){re.escape(func)}\s*\('
        if re.search(func_pattern, code):
            return False, f"Security error: use of '{func}()' function is not allowed"

    # Check for file system operations via string patterns
    file_patterns = [
        (r'os\.', "Security error: use of 'os' module is not allowed"),
        (r'pathlib\.', "Security error: use of 'pathlib' module is not allowed"),
        (r'__import__', "Security error: use of '__import__' is not allowed"),
    ]
    for pattern, error_msg in file_patterns:
        if re.search(pattern, code):
            return False, error_msg

    return True, None


def extract_aws_operations(code: str) -> list[str]:
    """Extract AWS operations from code using regex.

    Args:
        code: Python code string to analyze

    Returns:
        List of AWS CLI command strings found in the code
    """
    return AWS_OPERATION_PATTERN.findall(code)


def detect_loops_with_aws(code: str) -> list[str]:
    """Detect loops that may contain AWS operations.

    Args:
        code: Python code string to analyze

    Returns:
        List of warning messages about loops with AWS operations
    """
    warnings = []
    operations = extract_aws_operations(code)

    if operations and LOOP_PATTERN.search(code):
        # Simple heuristic: if there are loops and AWS operations, warn
        warnings.append(
            f"Loop detected with AWS operations: {len(operations)} potential calls"
        )

    return warnings


def analyze_code(code: str) -> dict[str, Any]:
    """Analyze code without executing it.

    Args:
        code: Python code string to analyze

    Returns:
        Analysis results including operations, warnings, and validity
    """
    result = {
        "operation_count": 0,
        "warnings": [],
        "valid": False,
        "operations": [],
    }

    # Validate syntax
    is_valid, syntax_error = validate_syntax(code)
    if not is_valid:
        result["warnings"].append(syntax_error)
        return result

    # Check for restricted operations
    is_safe, security_error = check_restricted_operations(code)
    if not is_safe:
        result["warnings"].append(security_error)
        return result

    # Extract operations
    operations = extract_aws_operations(code)
    result["operations"] = operations
    result["operation_count"] = len(operations)

    # Detect loops with AWS operations
    loop_warnings = detect_loops_with_aws(code)
    result["warnings"].extend(loop_warnings)

    result["valid"] = True
    return result


def create_sandbox_globals(
    aws_function: Callable[[str], dict[str, Any]],
    output_buffer: StringIO,
) -> dict[str, Any]:
    """Create restricted globals dictionary for sandbox execution.

    Args:
        aws_function: Function to execute AWS CLI commands
        output_buffer: StringIO buffer to capture print output

    Returns:
        Dictionary of safe globals for exec()
    """
    def safe_print(*args, **kwargs):
        """Capture print output to buffer."""
        kwargs['file'] = output_buffer
        print(*args, **kwargs)

    safe_builtins = {
        # Type constructors
        'dict': dict,
        'list': list,
        'set': set,
        'tuple': tuple,
        'str': str,
        'int': int,
        'float': float,
        'bool': bool,
        # Iteration
        'len': len,
        'range': range,
        'enumerate': enumerate,
        'zip': zip,
        'map': map,
        'filter': filter,
        'sorted': sorted,
        'reversed': reversed,
        # Utilities
        'any': any,
        'all': all,
        'sum': sum,
        'min': min,
        'max': max,
        'abs': abs,
        'round': round,
        'pow': pow,
        # Type checking
        'type': type,
        'isinstance': isinstance,
        # Exceptions
        'Exception': Exception,
        'ValueError': ValueError,
        'TypeError': TypeError,
        'KeyError': KeyError,
        'IndexError': IndexError,
        'AttributeError': AttributeError,
        'RuntimeError': RuntimeError,
        'TimeoutError': TimeoutError,
        # None, True, False
        'None': None,
        'True': True,
        'False': False,
    }

    return {
        'aws': aws_function,
        'print': safe_print,
        '__builtins__': safe_builtins,
    }


async def execute_aws_python(
    code: str,
    aws_executor: Callable[[str], Any] | None = None,
    dry_run: bool = False,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    """Execute Python code with AWS operations in a sandboxed environment.

    Args:
        code: Python code string to execute
        aws_executor: Async function to execute AWS CLI commands.
                     Should accept a command string and return parsed JSON response.
                     If None, a mock executor is used (for dry_run mode).
        dry_run: If True, analyze without executing AWS operations
        timeout: Maximum execution time in seconds

    Returns:
        Dictionary with:
            - status: "success" | "error" | "validation_error"
            - output: Captured print() output
            - result: Return value from code (if any)
            - operations: List of AWS operations executed
            - error: Error message if status is error
            - execution_time: Time taken to execute
            - analysis: Present when dry_run=True
    """
    start_time = time.time()
    executed_operations: list[str] = []
    output_buffer = StringIO()

    result = {
        "status": "success",
        "output": "",
        "result": None,
        "operations": [],
        "error": None,
        "execution_time": 0.0,
    }

    # Validate syntax first
    is_valid, syntax_error = validate_syntax(code)
    if not is_valid:
        result["status"] = "validation_error"
        result["error"] = syntax_error
        result["execution_time"] = time.time() - start_time
        return result

    # Check for restricted operations
    is_safe, security_error = check_restricted_operations(code)
    if not is_safe:
        result["status"] = "validation_error"
        result["error"] = security_error
        result["execution_time"] = time.time() - start_time
        return result


    # Analyze code
    analysis = analyze_code(code)

    # If dry_run, return analysis without executing
    if dry_run:
        result["operations"] = analysis["operations"]
        result["analysis"] = {
            "operation_count": analysis["operation_count"],
            "warnings": analysis["warnings"],
            "valid": analysis["valid"],
        }
        result["execution_time"] = time.time() - start_time
        return result

    # Create AWS function wrapper
    def aws_function(command: str) -> dict[str, Any]:
        """Execute AWS CLI command and return response."""
        nonlocal executed_operations

        if len(executed_operations) >= MAX_AWS_OPERATIONS:
            raise ExecutionError(
                f"Maximum number of AWS operations ({MAX_AWS_OPERATIONS}) exceeded"
            )

        executed_operations.append(command)
        logger.info(f"Code mode executing AWS command: {command}")

        if aws_executor is None:
            # No executor provided, return empty dict (for testing)
            return {}

        # Execute the AWS command
        try:
            # With nest_asyncio applied, we can safely use asyncio.run() or
            # get_event_loop().run_until_complete() even from within an async context
            if asyncio.iscoroutinefunction(aws_executor):
                # Get the current event loop (nest_asyncio allows nested runs)
                loop = asyncio.get_event_loop()
                response = loop.run_until_complete(aws_executor(command))
            else:
                response = aws_executor(command)

            # Handle different response types
            if hasattr(response, 'response') and response.response:
                # ProgramInterpretationResponse
                if response.response.error:
                    raise AwsOperationError(
                        response.response.error,
                        command,
                        {"error_code": response.response.error_code}
                    )
                if response.response.as_json:
                    import json
                    return json.loads(response.response.as_json)
            elif hasattr(response, 'error') and response.error:
                raise AwsOperationError(response.error, command)
            elif isinstance(response, dict):
                return response

            return {}
        except AwsOperationError:
            raise
        except Exception as e:
            raise AwsOperationError(str(e), command)


    # Create sandbox globals
    sandbox_globals = create_sandbox_globals(aws_function, output_buffer)
    sandbox_locals: dict[str, Any] = {}

    # Execute code directly - nest_asyncio allows this to work even in async context
    try:
        exec(code, sandbox_globals, sandbox_locals)

        result["output"] = output_buffer.getvalue()
        result["operations"] = executed_operations

        # Check if there's a result variable
        if '_result' in sandbox_locals:
            result["result"] = sandbox_locals['_result']

    except AwsOperationError as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["output"] = output_buffer.getvalue()
        result["operations"] = executed_operations

    except TimeoutError as e:
        result["status"] = "error"
        result["error"] = f"Execution timeout: code did not complete within {timeout} seconds"
        result["output"] = output_buffer.getvalue()
        result["operations"] = executed_operations

    except Exception as e:
        result["status"] = "error"
        result["error"] = f"{type(e).__name__}: {str(e)}"
        result["output"] = output_buffer.getvalue()
        result["operations"] = executed_operations

    result["execution_time"] = time.time() - start_time
    return result
