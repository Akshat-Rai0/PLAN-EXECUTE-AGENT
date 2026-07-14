from tavily import TavilyClient
from dotenv import load_dotenv
import os

load_dotenv()

client = TavilyClient(os.getenv("TAVILY_API_KEY"))

def tavily_search(query: str) -> str:
    """
    use web search to get relevant information using Tavily and return a response.
    """
    response = client.search(
        query=query,
        search_depth="advanced",
        chunks_per_source=3,
        max_results=5,
        include_answer=True,
    )


    if response.get("answer"):
        return response["answer"]


    if response.get("results"):
        return "\n\n".join(
            result["content"] for result in response["results"]
        )

    return "No results found."