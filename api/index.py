import os
import sys

# Ensure root project directory is in sys.path for Vercel execution
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import app
