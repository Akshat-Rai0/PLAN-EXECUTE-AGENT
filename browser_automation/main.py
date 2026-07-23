import asyncio
import os

from browser_use import Agent
from browser_use.llm import ChatOpenRouter
from dotenv import load_dotenv


MODEL = "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free"


async def main() -> None:
    load_dotenv()
    if not os.getenv("OPENROUTER_API_KEY"):
        raise RuntimeError(
            "OPENROUTER_API_KEY is missing. Copy .env.example to .env and add your key."
        )

    llm = ChatOpenRouter(model=MODEL,
                        api_key=os.getenv("OPENROUTER_API_KEY"))
    agent = Agent(
        task="Find the top HN post",
        llm=llm,
    )
    history = await agent.run()
    print(history.final_result())


if __name__ == "__main__":
    asyncio.run(main())

