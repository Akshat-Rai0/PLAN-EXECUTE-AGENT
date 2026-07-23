from src.models.browser_models import PageSummary

# Known interstitial/bot-check page titles (lowercased substring match).
# These pages have no useful content to act on -- waiting longer is the
# only sane move, and after repeated waits the step should fail cleanly
# rather than loop on "goto" forever.
_INTERSTITIAL_TITLE_MARKERS = (
    "just a moment",       # Cloudflare
    "attention required",  # Cloudflare
    "checking your browser",
    "verify you are human",
    "access denied",
)


class DOMCompressor:
    @staticmethod
    def compress(summary: PageSummary) -> str:
        """
        Compresses the PageSummary into a dense text representation suitable for LLMs.
        Designed to stay strictly below 1000 tokens.
        """
        lines = []
        lines.append(f"Title: {summary.title}")
        lines.append(f"URL: {summary.url}")

        if DOMCompressor.is_interstitial(summary.title):
            lines.append(
                "\n[INTERSTITIAL PAGE DETECTED] This looks like a bot-check / "
                "loading page (e.g. Cloudflare), not real content. Do not repeat "
                "'goto' to the same URL. Use {\"action\": \"wait\", \"value\": \"5\"} "
                "to let it clear, or 'finish' if it does not clear after waiting."
            )
            return "\n".join(lines)
        
        if summary.headings:
            lines.append("\n# Headings:")
            for h in summary.headings[:10]: # Cap limits
                lines.append(f"[{h.id}] {h.text}")
                
        if summary.inputs:
            lines.append("\n# Inputs:")
            for i in summary.inputs:
                desc = i.attributes.get('name', '') or i.attributes.get('placeholder', '') or i.attributes.get('type', '')
                lines.append(f"[{i.id}] {i.tag} ({desc})")
                
        if summary.buttons:
            lines.append("\n# Buttons:")
            for b in summary.buttons:
                lines.append(f"[{b.id}] {b.text}")
                
        if summary.links:
            lines.append("\n# Links (sample):")
            for l in summary.links[:20]: # Cap to avoid bloat
                lines.append(f"[{l.id}] {l.text}")

        # Minimal paragraph snapshot
        if summary.paragraphs:
            lines.append("\n# Content Snapshot:")
            text_body = " ".join(summary.paragraphs)
            # Truncate to save tokens
            if len(text_body) > 500:
                text_body = text_body[:500] + "..."
            lines.append(text_body)

        return "\n".join(lines)

    @staticmethod
    def is_interstitial(title: str) -> bool:
        """True if the page title matches a known bot-check/loading interstitial."""
        if not title:
            return False
        lowered = title.lower()
        return any(marker in lowered for marker in _INTERSTITIAL_TITLE_MARKERS)
