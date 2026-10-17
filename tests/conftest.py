import os
import sys

# Make the app package importable without a bench (pure modules only: never import frappe in tests/).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
