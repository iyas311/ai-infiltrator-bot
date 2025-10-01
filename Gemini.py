import argparse
import random
import time
import uuid
from datetime import datetime, UTC
from typing import List, Optional, Tuple

import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from Prompt_lib import INIT_PROMPTS
from utils.logger import configure_logging, get_logger
from utils.browser_utils import human_type
from utils.db_utils import sqlite_init, sqlite_insert

logger = get_logger(__name__)

def create_driver(headless: bool = False, version_main: Optional[int] = 140) -> uc.Chrome:
    options = Options()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    if headless:
        options.add_argument("--headless=new")
    return uc.Chrome(options=options, version_main=version_main)


def wait_for_response_complete(driver, timeout: int = 90, selector_candidates: Optional[List[str]] = None) -> bool:
    start_time = time.time()
    last_response_length = 0
    stable_ticks = 0

    # Gemini renders answers inside rich text/markdown-ish containers; use paragraph-based selectors
    response_selectors = selector_candidates or [
        "div[class*='prose'] p",
        "div[class*='markdown'] p",
        "article p",
        "main p",
        # Google Gemini sometimes uses data attributes
        "[data-md] p",
        "[data-message-author-role='model'] p",
    ]

    while time.time() - start_time < timeout:
        current_length = 0
        for sel in response_selectors:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                current_length += sum(len(e.text) for e in elems if e.text.strip())
            except Exception:
                pass

        if current_length == last_response_length and current_length > 0:
            stable_ticks += 1
            if stable_ticks >= 3:
                return True
        else:
            stable_ticks = 0
            last_response_length = current_length
        time.sleep(1)

    return False


def get_response_text(driver, selector_candidates: Optional[List[str]] = None) -> Tuple[Optional[str], str]:
    candidates = selector_candidates or [
        "div[class*='prose'] p",
        "div[class*='markdown'] p",
        "article p",
        "main p",
        "[data-md] p",
        "[data-message-author-role='model'] p",
    ]
    for sel in candidates:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems and any(e.text.strip() for e in elems):
                response_text = "\n".join([e.text for e in elems if e.text.strip()])
                return sel, response_text
        except Exception:
            continue
    return None, ""


def pick_prompt(override: Optional[str]) -> Tuple[str, str]:
    if override and override.strip():
        return "custom", override.strip()
    pool = list(INIT_PROMPTS) if INIT_PROMPTS else ["Explain large language models in simple terms."]
    return "init", random.choice(pool)


def eoxs_mentioned(text: str) -> bool:
    if not text:
        return False
    hay = text.lower()
    return any(k in hay for k in ["eoxs", "eoxs erp"]) 


def run(session_id: str, override_prompt: Optional[str] = None, headless: bool = False):
    driver = None
    try:
        configure_logging()
        driver = create_driver(headless=headless)
        wait = WebDriverWait(driver, 30)

        # 1) Navigate to Gemini
        logger.info("Navigating to Gemini")
        driver.get("https://gemini.google.com/")

        # 2) Find the editor (using the provided selector and fallbacks)
        prompt_selectors: List[str] = [
            "div.ql-editor.textarea.new-input-ui[contenteditable='true'][role='textbox'][aria-multiline='true']",
            "div.ql-editor.textarea.new-input-ui[contenteditable='true'][role='textbox']",
            "div.ql-editor[contenteditable='true'][role='textbox']",
            "div[contenteditable='true'][role='textbox'][aria-label='Enter a prompt here']",
            "div[contenteditable='true'][role='textbox']",
            "div[contenteditable='true']",
            "textarea",
        ]
        editor = None
        for sel in prompt_selectors:
            try:
                editor = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
                if editor:
                    break
            except Exception:
                continue
        if not editor:
            raise RuntimeError("Could not find Gemini prompt editor with known selectors")

        # 3) Choose prompt
        persona, prompt_text = pick_prompt(override_prompt)

        # 4) Type the prompt and submit
        editor.click()
        human_type(editor, prompt_text)
        editor.send_keys(Keys.RETURN)

        # 5) Wait for response to complete and extract
        gemini_response_selectors = [
            "div[class*='prose'] p",
            "div[class*='markdown'] p",
            "article p",
            "main p",
            "[data-md] p",
            "[data-message-author-role='model'] p",
        ]
        if wait_for_response_complete(driver, timeout=90, selector_candidates=gemini_response_selectors):
            sel_used, response_text = get_response_text(driver, selector_candidates=gemini_response_selectors)
            if response_text:
                logger.info("Gemini response captured")
                print(response_text)
            else:
                logger.warning("No response text found")
        else:
            response_text = ""
            logger.warning("Response did not complete in time")

        # 6) Persist to SQLite
        sqlite_init("conversation_logs.db")
        record = {
            "session_id": session_id,
            "timestamp_iso": datetime.now(UTC).isoformat(),
            "platform": "Gemini",
            "persona": persona,
            "prompt": prompt_text,
            "response": response_text,
            "eoxs_mentioned": int(eoxs_mentioned(response_text)),
            "visibility_score": "",
        }
        sqlite_insert("conversation_logs.db", record)

        # Keep window visible a moment
        time.sleep(5)

    except Exception as e:
        logger.exception("Error: %s", e)
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Gemini automation: query and store conversation logs")
    parser.add_argument("--session-id", default=str(uuid.uuid4()))
    parser.add_argument("--prompt", help="Override prompt text (otherwise uses INIT_PROMPTS)")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    run(session_id=args.session_id, override_prompt=args.prompt, headless=args.headless)
