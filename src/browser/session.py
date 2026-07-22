from playwright.sync_api import BrowserContext, Page
from typing import List, Optional

class SessionManager:
    def __init__(self, context: BrowserContext):
        self.context = context
        self.pages: List[Page] = context.pages

    def get_current_page(self) -> Page:
        if not self.pages:
            self.pages.append(self.context.new_page())
        return self.pages[-1]

    def new_tab(self) -> Page:
        page = self.context.new_page()
        self.pages.append(page)
        return page

    def close_tab(self):
        if len(self.pages) > 1:
            page = self.pages.pop()
            page.close()

    def get_cookies(self) -> list:
        return self.context.cookies()
    
    def set_cookies(self, cookies: list):
        self.context.add_cookies(cookies)

    def close(self):
        self.context.close()
