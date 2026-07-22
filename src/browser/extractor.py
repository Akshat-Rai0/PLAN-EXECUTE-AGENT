from selectolax.parser import HTMLParser
from typing import Dict, Any, List, Optional
import json
from src.models.browser_models import PageSummary, ExtractedElement, ExtractedForm
from src.browser.selector import SelectorManager

class DOMExtractor:
    def __init__(self, selector_manager: SelectorManager):
        self.selector_manager = selector_manager
        
    def _build_selector(self, node) -> str:
        """Heuristically build a CSS selector for a given selectolax node."""
        path = []
        current = node
        while current and current.tag != '-ROOT-':
            # Identify by ID if present
            if current.attributes.get('id'):
                path.insert(0, f"#{current.attributes['id']}")
                break
            # Else try by classes or structural
            tag = current.tag
            cls = current.attributes.get('class')
            if cls:
                classes = '.'.join(cls.split())
                path.insert(0, f"{tag}.{classes}")
            else:
                path.insert(0, tag)
            current = current.parent
            
        return " > ".join(path)

    def extract(self, html: str, url: str, title: str) -> PageSummary:
        parser = HTMLParser(html)
        
        # Remove unwanted tags
        for tag in parser.css('script, style, svg, canvas, noscript'):
            tag.decompose()
            
        summary = PageSummary(url=url, title=title)
        
        # Extract headings
        for h in parser.css('h1, h2, h3, h4, h5, h6'):
            text = h.text(strip=True)
            if not text or self._is_hidden(h): continue
            selector = self._build_selector(h)
            el_id = self.selector_manager.register(selector)
            summary.headings.append(ExtractedElement(
                id=el_id, tag=h.tag, text=text
            ))
            
        # Extract links
        for a in parser.css('a[href]'):
            text = a.text(strip=True)
            if not text or self._is_hidden(a): continue
            selector = self._build_selector(a)
            el_id = self.selector_manager.register(selector)
            summary.links.append(ExtractedElement(
                id=el_id, tag=a.tag, text=text,
                attributes={"href": a.attributes.get('href', '')}
            ))
            
        # Extract inputs
        for inp in parser.css('input:not([type="hidden"]), textarea, select'):
            if self._is_hidden(inp): continue
            selector = self._build_selector(inp)
            el_id = self.selector_manager.register(selector)
            attrs = {k: v for k, v in inp.attributes.items() if k in ['type', 'name', 'placeholder', 'value']}
            text = inp.text(strip=True) if inp.tag != 'input' else None
            summary.inputs.append(ExtractedElement(
                id=el_id, tag=inp.tag, text=text, attributes=attrs
            ))
            
        # Extract buttons
        for btn in parser.css('button, input[type="submit"], input[type="button"]'):
            if self._is_hidden(btn): continue
            text = btn.text(strip=True) or btn.attributes.get('value', '')
            selector = self._build_selector(btn)
            el_id = self.selector_manager.register(selector)
            summary.buttons.append(ExtractedElement(
                id=el_id, tag=btn.tag, text=text
            ))

        # Forms
        for form in parser.css('form'):
            if self._is_hidden(form): continue
            selector = self._build_selector(form)
            el_id = self.selector_manager.register(selector)
            summary.forms.append(ExtractedForm(
                id=el_id, action=form.attributes.get('action')
            ))
            
        # Paragraphs (sample)
        for p in parser.css('p'):
            text = p.text(strip=True)
            if text and len(text) > 20 and not self._is_hidden(p):
                summary.paragraphs.append(text)
                
        return summary
        
    def _is_hidden(self, node) -> bool:
        style = node.attributes.get('style', '').lower()
        if 'display: none' in style or 'display:none' in style or 'visibility: hidden' in style:
            return True
        if node.attributes.get('hidden') is not None:
            return True
        return False
