from playwright.sync_api import Page, TimeoutError as PlaywrightTimeout
import time

class BrowserController:
    """
    Purely deterministic controller for Playwright actions. No LLM logic.
    """
    def __init__(self, page: Page):
        self.page = page

    def goto(self, url: str):
        self.page.goto(url, wait_until="domcontentloaded")

    def click(self, selector: str):
        self.page.locator(selector).first.click(timeout=5000)

    def type(self, selector: str, value: str):
        loc = self.page.locator(selector).first
        loc.fill("")
        loc.type(value, delay=50)

    def select(self, selector: str, value: str):
        self.page.locator(selector).first.select_option(value)

    def check(self, selector: str):
        self.page.locator(selector).first.check()

    def upload(self, selector: str, file_path: str):
        self.page.locator(selector).first.set_input_files(file_path)

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
