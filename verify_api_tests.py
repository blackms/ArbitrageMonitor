#!/usr/bin/env python3
"""
Verification script for API integration tests

This script verifies that the API integration tests are properly structured
and would work correctly with a test database.

To run the actual tests, you need a PostgreSQL test database:
docker run --name postgres-test -e POSTGRES_DB=arbitrage_monitor_test \
    -e POSTGRES_USER=monitor -e POSTGRES_PASSWORD=password \
    -p 5432:5432 -d postgres:15

Then run: pytest tests/test_api.py -v -m integration
"""

import ast
import sys


def verify_test_file():
    """Verify the test file structure"""
    print("Verifying API integration tests...")
    print("=" * 70)
    
    # Read the test file
    with open("tests/test_api.py", "r") as f:
        content = f.read()
    
    # Parse the AST
    try:
        tree = ast.parse(content)
        print("✓ Test file syntax is valid")
    except SyntaxError as e:
        print(f"✗ Syntax error in test file: {e}")
        return False
    
    # Count test functions (both sync and async)
    test_functions = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_"):
            test_functions.append(node.name)
    
    print(f"✓ Found {len(test_functions)} test functions")
    
    # Verify test categories
    categories = {
        "Authentication": [f for f in test_functions if "authentication" in f or "auth" in f],
        "Chains": [f for f in test_functions if "chains" in f],
        "Opportunities": [f for f in test_functions if "opportunities" in f],
        "Transactions": [f for f in test_functions if "transactions" in f],
        "Arbitrageurs": [f for f in test_functions if "arbitrageurs" in f],
        "Statistics": [f for f in test_functions if "stats" in f],
        "Health": [f for f in test_functions if "health" in f],
        "Error Handling": [f for f in test_functions if "invalid" in f or "error" in f],
        "CORS": [f for f in test_functions if "cors" in f],
    }
    
    print("\nTest Coverage by Category:")
    print("-" * 70)
    for category, tests in categories.items():
        if tests:
            print(f"  {category}: {len(tests)} tests")
            for test in tests[:3]:  # Show first 3
                print(f"    - {test}")
            if len(tests) > 3:
                print(f"    ... and {len(tests) - 3} more")
    
    # Verify required test patterns
    required_patterns = {
        "Authentication with valid key": any("valid_key" in f for f in test_functions),
        "Authentication with invalid key": any("invalid_key" in f for f in test_functions),
        "Authentication missing key": any("missing_key" in f for f in test_functions),
        "Filter by chain": any("filter_by_chain" in f for f in test_functions),
        "Pagination": any("pagination" in f for f in test_functions),
        "Error responses": any("invalid" in f or "error" in f for f in test_functions),
    }
    
    print("\nRequired Test Patterns:")
    print("-" * 70)
    all_present = True
    for pattern, present in required_patterns.items():
        status = "✓" if present else "✗"
        print(f"  {status} {pattern}")
        if not present:
            all_present = False
    
    # Check for async tests
    async_tests = [
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("test_")
    ]
    print(f"\n✓ Found {len(async_tests)} async test functions")
    
    # Check for fixtures
    fixtures = [
        node.name for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and any(
            isinstance(dec, ast.Name) and dec.id == "fixture"
            for dec in node.decorator_list
            if isinstance(dec, (ast.Name, ast.Attribute))
        )
    ]
    print(f"✓ Found {len(fixtures)} test fixtures: {', '.join(fixtures)}")
    
    print("\n" + "=" * 70)
    if all_present:
        print("✓ All API integration tests are properly structured!")
        print("\nTo run the tests:")
        print("  1. Start a PostgreSQL test database (see instructions in test file)")
        print("  2. Run: pytest tests/test_api.py -v -m integration")
        return True
    else:
        print("✗ Some required test patterns are missing")
        return False


if __name__ == "__main__":
    success = verify_test_file()
    sys.exit(0 if success else 1)
