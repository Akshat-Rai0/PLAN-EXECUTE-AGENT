import pytest
from src.browser.selector import SelectorManager
from src.browser.extractor import DOMExtractor
from src.browser.compressor import DOMCompressor
from src.models.browser_models import BrowserAction

def test_selector_manager():
    sm = SelectorManager()
    id1 = sm.register("div.test")
    id2 = sm.register("#login")
    
    assert id1 == 1
    assert id2 == 2
    assert sm.get_selector(1) == "div.test"
    assert sm.get_selector(2) == "#login"
    
    sm.clear()
    id3 = sm.register("a.link")
    assert id3 == 1
    assert sm.get_selector(1) == "a.link"

def test_extractor_no_html_leak():
    sm = SelectorManager()
    ext = DOMExtractor(sm)
    
    html = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1>Welcome</h1>
        <script>alert('hidden');</script>
        <form action="/login" id="login-form">
            <input type="text" name="username" placeholder="User" />
            <input type="password" name="password" style="display:none;" />
            <button type="submit">Login</button>
        </form>
        <a href="/forgot">Forgot Password?</a>
        <p>This is a paragraph.</p>
    </body>
    </html>
    """
    
    summary = ext.extract(html, "http://test.local", "Test Page")
    
    assert summary.title == "Test Page"
    
    # Check hidden elements are excluded (like the password field with display:none)
    assert len(summary.inputs) == 1
    assert summary.inputs[0].attributes['name'] == 'username'
    
    # Script tag should be gone
    assert len(summary.buttons) == 1
    assert summary.buttons[0].text == "Login"
    
    assert len(summary.links) == 1
    assert summary.links[0].text == "Forgot Password?"
    
def test_compressor_token_footprint():
    sm = SelectorManager()
    ext = DOMExtractor(sm)
    
    html = """
    <html><body>
        <h1>Test</h1>
        <input type="text" name="q" placeholder="Search">
        <button>Go</button>
        <a href="/link">Link 1</a>
        <p>Lots of text over 20 chars here to be picked up.</p>
    </body></html>
    """
    summary = ext.extract(html, "http://test.local", "Test")
    compressed = DOMCompressor.compress(summary)
    
    # Make sure compressed is concise and doesn't contain HTML brackets
    assert "Title: Test" in compressed
    assert "[1]" in compressed # Selectors are mapped
    assert "<html>" not in compressed
    assert "<button>" not in compressed
    
    # Rough token count proxy: length of string is small
    assert len(compressed) < 1000
