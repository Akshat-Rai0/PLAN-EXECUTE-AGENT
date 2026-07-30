#!/usr/bin/env python3
"""
Demo site integration test script for browser pipelines.

Tests each pipeline on actual demo sites to validate functionality.
Run with: python3 test_demo_sites.py
"""
import asyncio
import os
import sys

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.tools.browser_tool import BrowserTool
from src.agents.plan_execute.browser_pipelines.form_filling import run_form_filling_pipeline
from src.agents.plan_execute.browser_pipelines.comparison import run_comparison_pipeline
from src.agents.plan_execute.browser_pipelines.info_retrieval import run_info_retrieval_pipeline


async def test_demoqa_form():
    """Test form filling on demoqa.com."""
    print("\n" + "="*60)
    print("Testing Form Filling on demoqa.com")
    print("="*60)
    
    browser_tool = BrowserTool(headless=False)
    
    try:
        context = """
        Fill out the form with:
        - First Name: John
        - Last Name: Doe
        - Email: john.doe@example.com
        """
        
        result = await run_form_filling_pipeline(browser_tool, context)
        
        print(f"\nResult: {result.status.value}")
        print(f"Success: {result.success}")
        print(f"Error: {result.error}")
        print(f"Extracted: {result.extracted_text[:200] if result.extracted_text else 'N/A'}...")
        
        if result.metadata and "structured_result" in result.metadata:
            print(f"\nStructured Result: {result.metadata['structured_result']}")
        
    finally:
        await browser_tool.close_session()


async def test_opencart_comparison():
    """Test product comparison on demo.opencart.com."""
    print("\n" + "="*60)
    print("Testing Product Comparison on demo.opencart.com")
    print("="*60)
    
    browser_tool = BrowserTool(headless=False)
    
    try:
        task = "Compare prices of desktop computers"
        targets = ["https://demo.opencart.com/index.php?route=product/category&path=20"]
        extraction_goal = "product name, price, and rating"
        
        result = await run_comparison_pipeline(browser_tool, task, targets, extraction_goal)
        
        print(f"\nResult: {result.status.value}")
        print(f"Success: {result.success}")
        print(f"Error: {result.error}")
        print(f"\nComparison Table:\n{result.extracted_text[:500] if result.extracted_text else 'N/A'}...")
        
        if result.metadata and "structured_result" in result.metadata:
            print(f"\nStructured Result: {result.metadata['structured_result']}")
        
    finally:
        await browser_tool.close_session()


async def test_selenium_info_retrieval():
    """Test info retrieval on selenium.dev web form."""
    print("\n" + "="*60)
    print("Testing Info Retrieval on selenium.dev")
    print("="*60)
    
    browser_tool = BrowserTool(headless=False)
    
    try:
        task = "What is the purpose of this web form page?"
        targets = ["https://www.selenium.dev/selenium/web/web-form.html"]
        
        result = await run_info_retrieval_pipeline(browser_tool, task, targets)
        
        print(f"\nResult: {result.status.value}")
        print(f"Success: {result.success}")
        print(f"Error: {result.error}")
        print(f"Extracted: {result.extracted_text[:300] if result.extracted_text else 'N/A'}...")
        
        if result.metadata and "structured_result" in result.metadata:
            print(f"\nStructured Result: {result.metadata['structured_result']}")
        
    finally:
        await browser_tool.close_session()


async def main():
    """Run all demo site tests."""
    print("\n" + "="*60)
    print("Browser Pipelines Demo Site Integration Tests")
    print("="*60)
    print("\nNote: These tests require OPENROUTER_API_KEY to be set")
    print("and will open a browser window (headless=False)")
    print("\nPress Ctrl+C to skip a test or exit\n")
    
    tests = [
        ("demoqa.com Form Filling", test_demoqa_form),
        ("opencart.com Comparison", test_opencart_comparison),
        ("selenium.dev Info Retrieval", test_selenium_info_retrieval),
    ]
    
    for name, test_func in tests:
        try:
            await test_func()
        except KeyboardInterrupt:
            print(f"\n⚠️  Skipped {name}")
            continue
        except Exception as e:
            print(f"\n❌ {name} failed: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("Demo site tests completed")
    print("="*60)


if __name__ == "__main__":
    asyncio.run(main())
