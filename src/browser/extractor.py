from selectolax.parser import HTMLParser
from src.models.browser_models import PageSummary, ExtractedElement, ExtractedForm
from src.browser.selector import SelectorManager


def _is_valid_css_ident(value: str) -> bool:
    """
    Very small check for whether `value` can be used unescaped after a bare
    '#' in a CSS ID selector. CSS identifiers cannot start with a digit (or a
    hyphen followed by a digit), and must not contain characters outside
    [a-zA-Z0-9_-] for our purposes here. Real-world IDs that fail this most
    commonly look like site-internal numeric IDs (e.g. HackerNews' `id="49010345"`
    on story rows), which are perfectly valid HTML `id` attributes but not
    valid unescaped CSS selectors.
    """
    if not value:
        return False
    if value[0].isdigit():
        return False
    if value[0] == '-' and len(value) > 1 and value[1].isdigit():
        return False
    return all(ch.isalnum() or ch in ('-', '_') for ch in value)


class DOMExtractor:
    def __init__(self, selector_manager: SelectorManager):
        self.selector_manager = selector_manager
        
    def _build_selector(self, node) -> str:
        """Heuristically build a CSS selector for a given selectolax node."""
        path = []
        current = node
        while current and current.tag != '-ROOT-':
            # Identify by ID if present
            node_id = current.attributes.get('id')
            if node_id:
                if _is_valid_css_ident(node_id):
                    path.insert(0, f"#{node_id}")
                else:
                    # Fall back to an attribute selector, which works for any
                    # ID value (numeric-leading, special characters, etc.)
                    # without needing manual CSS escaping.
                    escaped = node_id.replace('"', '\\"')
                    path.insert(0, f'[id="{escaped}"]')
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
                attributes={"href": a.attributes.get('href') or ''}
            ))
            
        # Extract inputs
        for inp in parser.css('input:not([type="hidden"]), textarea, select'):
            if self._is_hidden(inp): continue
            selector = self._build_selector(inp)
            el_id = self.selector_manager.register(selector)
            attrs = {
                k: (v if v is not None else "")
                for k, v in inp.attributes.items()
                if k in ['type', 'name', 'placeholder', 'value']
            }
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
        style = (node.attributes.get('style') or '').lower()
        if 'display: none' in style or 'display:none' in style or 'visibility: hidden' in style:
            return True
        if node.attributes.get('hidden') is not None:
            return True
        return False
