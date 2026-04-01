"""Streamlit frontend environment configuration."""

import os

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")

