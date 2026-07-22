#!/usr/bin/env python3
"""Test script for browser-use integration."""

import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Test the browser_use_tool function
from src.tools.registry import browser_use_tool

# Simple test task
test_task = "Go to example.com and tell me the page title"

print("Testing browser_use_tool...")
print(f"Task: {test_task}")
print(f"GROQ_API_KEY: {'SET' if os.getenv('GROQ_API_KEY') else 'NOT SET'}")
print(f"GROQ_MODEL: {os.getenv('GROQ_MODEL', 'llama-3.3-70b-versatile')}")
print(f"BROWSER_MODE: {os.getenv('BROWSER_MODE', 'headless')}")

result = browser_use_tool(test_task, headless=True)

print("\n" + "="*80)
print("RESULT:")
print("="*80)
print(result)
print("="*80)
