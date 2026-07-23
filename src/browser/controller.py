from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout
import time

class BrowserController:
    """
    Purely deterministic controller for Playwright actions. No LLM logic.
    """
    def __init__(self, page: Page):
        self.page = page

    def goto(self, url: str):
        try:
            self.page.goto(url, wait_until="domcontentloaded")
        except PlaywrightTimeout as e:
            raise TimeoutError(f"Timed out navigating to {url!r}: {e}") from e

    def click(self, selector: str):
        try:
            self.page.locator(selector).first.click(timeout=5000)
        except PlaywrightTimeout as e:
            raise TimeoutError(f"Timed out clicking {selector!r}: {e}") from e

    def type(self, selector: str, value: str):
        try:
            loc = self.page.locator(selector).first
            loc.fill("")
            loc.type(value, delay=50)
        except PlaywrightTimeout as e:
            raise TimeoutError(f"Timed out typing into {selector!r}: {e}") from e

    def select(self, selector: str, value: str):
        try:
            self.page.locator(selector).first.select_option(value)
        except PlaywrightTimeout as e:
            raise TimeoutError(f"Timed out selecting on {selector!r}: {e}") from e

    def check(self, selector: str):
        try:
            self.page.locator(selector).first.check()
        except PlaywrightTimeout as e:
            raise TimeoutError(f"Timed out checking {selector!r}: {e}") from e

    def upload(self, selector: str, file_path: str):
        try:
            self.page.locator(selector).first.set_input_files(file_path)
        except PlaywrightTimeout as e:
            raise TimeoutError(f"Timed out uploading to {selector!r}: {e}") from e

    def scroll(self, direction: str = "down"):
        if direction == "down":
            self.page.mouse.wheel(0, 600)
        else:
            self.page.mouse.wheel(0, -600)
        time.sleep(1) # wait for render

    def wait(self, seconds: int):
        time.sleep(seconds)

    def back(self):
        self.page.go_back()

    def forward(self):
        self.page.go_forward()

    def screenshot(self, path: str):
        self.page.screenshot(path=path)

    def get_html(self) -> str:
        return self.page.content()

    def get_url(self) -> str:
        return self.page.url

    def get_title(self) -> str:
        return self.page.title()
