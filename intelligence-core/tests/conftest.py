"""
Pytest configuration for intelligence-core tests.

This module configures the Python path to allow importing from the parent
package without modifying sys.path in individual test files.
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
# This allows tests to import from cashback, retailer, optimizer, etc.
sys.path.insert(0, str(Path(__file__).parent.parent))
