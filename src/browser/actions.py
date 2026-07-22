from enum import Enum

class ActionType(str, Enum):
    GOTO = "goto"
    CLICK = "click"
    TYPE = "type"
    SELECT = "select"
    CHECK = "check"
    UPLOAD = "upload"
    SCROLL = "scroll"
    WAIT = "wait"
    EXTRACT = "extract"
    FINISH = "finish"
    BACK = "back"
    FORWARD = "forward"
    SCREENSHOT = "screenshot"
