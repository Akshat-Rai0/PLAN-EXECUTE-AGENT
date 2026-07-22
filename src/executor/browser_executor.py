import os
from playwright.sync_api import sync_playwright
from src.browser.controller import BrowserController
from src.browser.extractor import DOMExtractor
from src.browser.compressor import DOMCompressor
from src.browser.selector import SelectorManager
from src.browser.session import SessionManager
from src.browser.state import StateManager
from src.models.browser_models import BrowserAction
from src.browser.actions import ActionType

class BrowserExecutor:
    def __init__(self, headless: bool = True):
        # Override with env var if provided
        env_headless = os.environ.get("PLAYWRIGHT_HEADLESS", "").lower()
        if env_headless in ["true", "1"]:
            headless = True
        elif env_headless in ["false", "0"]:
            headless = False
            
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=headless)
        self.context = self.browser.new_context()
        
        self.session_manager = SessionManager(self.context)
        self.state_manager = StateManager()
        self.selector_manager = SelectorManager()
        self.extractor = DOMExtractor(self.selector_manager)
        
        self.controller = BrowserController(self.session_manager.get_current_page())
        
    def execute(self, action: BrowserAction) -> str:
        """
        Executes a browser action and returns a compressed summary of the new page state.
        Errors are caught and returning error messages that planner can use to retry.
        """
        try:
            return self._execute_internal(action)
        except Exception as e:
            # Attempt basic recovery
            return f"Action failed: {str(e)}. Try a different target or wait."

    def _execute_internal(self, action: BrowserAction) -> str:
        act_type = action.action.lower()
        
        if act_type == ActionType.GOTO:
            self.selector_manager.clear() # New page
            self.controller.goto(action.value)
            self.state_manager.record_visit(action.value)
            
        elif act_type in [ActionType.CLICK, ActionType.TYPE, ActionType.SELECT, ActionType.CHECK, ActionType.UPLOAD]:
            if not action.target:
                return "Error: target ID required for this action."
            
            selector = self.selector_manager.get_selector(action.target)
            if not selector:
                return f"Error: No selector found for ID {action.target}."
                
            if act_type == ActionType.CLICK:
                self.controller.click(selector)
            elif act_type == ActionType.TYPE:
                # Support auto-profile mapping if value starts with $PROFILE_
                val = action.value
                if val and val.startswith("$PROFILE_"):
                    key = val.replace("$PROFILE_", "")
                    val = self.state_manager.get_profile_value(key)
                self.controller.type(selector, val)
                self.state_manager.record_field_fill(action.target, val)
            elif act_type == ActionType.SELECT:
                self.controller.select(selector, action.value)
            elif act_type == ActionType.CHECK:
                self.controller.check(selector)
            elif act_type == ActionType.UPLOAD:
                self.controller.upload(selector, action.value)
                
        elif act_type == ActionType.SCROLL:
            self.controller.scroll(action.value or "down")
            
        elif act_type == ActionType.WAIT:
            # value could be seconds
            sec = int(action.value) if action.value and action.value.isdigit() else 2
            self.controller.wait(sec)
            
        elif act_type == ActionType.BACK:
            self.controller.back()
            
        elif act_type == ActionType.FORWARD:
            self.controller.forward()
            
        elif act_type == ActionType.EXTRACT:
            pass # Just falls through to extraction
            
        elif act_type == ActionType.FINISH:
            return "Task finished successfully."
            
        else:
            return f"Error: Unknown action {act_type}"

        # Record successful action
        self.state_manager.record_action(action)
        
        # Always return compressed DOM of the current state
        html = self.controller.get_html()
        url = self.controller.get_url()
        title = self.controller.get_title()
        
        summary = self.extractor.extract(html, url, title)
        compressed = DOMCompressor.compress(summary)
        
        return compressed
        
    def close(self):
        self.session_manager.close()
        self.browser.close()
        self.playwright.stop()
