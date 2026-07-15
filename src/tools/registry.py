from tavily import TavilyClient
from dotenv import load_dotenv
import os
import re

load_dotenv()

client = TavilyClient(os.getenv("TAVILY_API_KEY"))


def _filter_noise(content: str) -> str:
    """
    Filter out navigation bars, footers, and other noise from search results.
    Removes lines containing common navigation/footer patterns.
    """
    noise_patterns = [
        r"subscribe", r"follow", r"channel", r"nav", r"footer", r"menu",
        r"subscribers?", r"views", r"like", r"share", r"comment",
        r"FOLLOW.*CHANNELS?", r"SUBSCRIBE", r"©\s*\d{4}",
        r"privacy policy", r"terms of service", r"cookie",
    ]
    
    lines = content.split("\n")
    filtered_lines = []
    
    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            continue
        
        # Skip lines that match noise patterns (case-insensitive)
        if any(re.search(pattern, line_stripped, re.IGNORECASE) for pattern in noise_patterns):
            continue
        
        # Skip lines that are all caps (likely headers/ads)
        if line_stripped.isupper() and len(line_stripped) > 3:
            continue
        
        # Skip lines with excessive punctuation (likely ads/promotions)
        if len(re.findall(r"[!?.]{3,}", line_stripped)) > 0:
            continue
        
        filtered_lines.append(line)
    
    return "\n".join(filtered_lines)


def tavily_search(query: str, search_depth: str = "basic") -> str:
    """
    Use web search to get relevant information using Tavily and return a response.
    
    Args:
        query: The search query string
        search_depth: Either "basic" or "advanced" - basic for status checks, advanced for detailed searches
    
    Returns:
        Filtered search results with noise removed
    """
    response = client.search(
        query=query,
        search_depth=search_depth,
        chunks_per_source=3,
        max_results=3,
        include_answer=False,   
        include_raw_content=False,
        days=7,                 
    )

    if response.get("answer"):
        return _filter_noise(response["answer"])

    if response.get("results"):
        filtered_results = []
        for result in response["results"]:
            filtered_content = _filter_noise(result["content"])
            if filtered_content.strip():
                filtered_results.append(filtered_content)
        
        return "\n\n".join(filtered_results)

    return "No results found."