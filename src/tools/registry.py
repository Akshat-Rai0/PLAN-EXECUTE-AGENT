from tavily import TavilyClient
from dotenv import load_dotenv
import os

load_dotenv()

client = TavilyClient(os.getenv("TAVILY_API_KEY"))

response = client.search(
    "who is leo messi",
    search_depth="advanced",
    chunks_per_source=3,
    max_results=5,
    include_answer=True,  
)

answer = response.get("answer")
print("ANSWER:", answer)
print()

for result in response["results"]:
    print(result["title"])
    print(result["content"][:200])
    print()