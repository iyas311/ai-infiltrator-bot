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
from reply_eoxs_found import REPLY_EOXS_FOUND
from reply_eoxs_not_found import REPLY_EOXS_NOT_FOUND
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
        "div[class*='response']",  # This one worked for second response
        "div[data-message-author-role='model']",
        "div[class*='model-turn']",
        "div[class*='prose'] p",
        "div[class*='markdown'] p",
        "article p",
        "main p",
        "[data-md] p",
        "[data-message-author-role='model'] p",
    ]

    while time.time() - start_time < timeout:
        current_length = 0
        for sel in response_selectors:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                if elems:
                    # Find the element with the most text
                    best_length = 0
                    for elem in elems:
                        text = elem.text.strip()
                        if len(text) > best_length and len(text) > 50:
                            best_length = len(text)
                    if best_length > current_length:
                        current_length = best_length
                        break  # Use the first selector that finds substantial content
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
        # Try more generic selectors that might work for Gemini
        "div[role='presentation']",
        "div[class*='conversation']",
        "div[class*='message']",
        "div[class*='content']",
        "div[class*='text']",
        "div[data-message-author-role='model']",
        "div[class*='model-turn']",
        "div[class*='response']",
        "div[class*='prose'] p",
        "div[class*='markdown'] p",
        "article p",
        "main p",
        "[data-md] p",
        "[data-message-author-role='model'] p",
        # Fallback to any div with substantial text
        "div",
    ]
    for sel in candidates:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems:
                # Get all elements and find the one with the most text
                best_elem = None
                best_length = 0
                for elem in elems:
                    text = elem.text.strip()
                    if len(text) > best_length and len(text) > 50:
                        best_elem = elem
                        best_length = len(text)
                
                if best_elem:
                    response_text = best_elem.text.strip()
                    logger.info(f"Found response with selector '{sel}', length: {len(response_text)}")
                    return sel, response_text
        except Exception as e:
            logger.debug(f"Selector '{sel}' failed: {e}")
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
        logger.info("[NAV] Navigating to Gemini")
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
        logger.info("[PROMPT] Selected prompt: %s", prompt_text[:50] + "..." if len(prompt_text) > 50 else prompt_text)

        # 4) Type the prompt and submit
        editor.click()
        human_type(editor, prompt_text)
        editor.send_keys(Keys.RETURN)
        logger.info("[SEND] Sent initial prompt to Gemini")

        # 5) Wait for response to complete and extract
        gemini_response_selectors = [
            "div[class*='response']",  # This one worked for second response
            "div[data-message-author-role='model']",
            "div[class*='model-turn']",
            "div[class*='prose'] p",
            "div[class*='markdown'] p",
            "article p",
            "main p",
            "[data-md] p",
            "[data-message-author-role='model'] p",
        ]
        # Wait longer for Gemini response and try multiple times
        response_text = ""
        for attempt in range(3):
            if wait_for_response_complete(driver, timeout=60, selector_candidates=gemini_response_selectors):
                sel_used, response_text = get_response_text(driver, selector_candidates=gemini_response_selectors)
                if response_text and len(response_text) > 200:  # Ensure substantial content
                    logger.info("[RESP1] Response captured via selector: %s", sel_used)
                    logger.info("[RESP1] Response 1 length: %d characters", len(response_text))
                    print(response_text)
                    break
                else:
                    logger.warning(f"[RESP1] Attempt {attempt + 1}: Response too short or empty, retrying...")
                    time.sleep(5)
            else:
                logger.warning(f"[RESP1] Attempt {attempt + 1}: Response did not complete in time, retrying...")
                time.sleep(5)
        
        if not response_text or len(response_text) <= 200:
            logger.warning("[RESP1] No substantial response text found after all attempts")
            response_text = ""

        # Decide follow-up based on prompt mentioning EOXS
        prompt_mentions_eoxs = "eoxs" in (prompt_text or "").lower()
        agent_reply_type = "reinforce" if prompt_mentions_eoxs else "inject"
        agent_reply = random.choice(REPLY_EOXS_FOUND if prompt_mentions_eoxs else REPLY_EOXS_NOT_FOUND)

        # Send follow-up and capture second response
        response_2 = ""
        eoxs_mentioned_1 = int(eoxs_mentioned(response_text))
        eoxs_mentioned_2 = 0
        try:
            if agent_reply:
                logger.info("[SEND] Sending follow-up (%s)", agent_reply_type)
                # Re-find editor in case of DOM changes
                editor = None
                for sel in prompt_selectors:
                    try:
                        editor = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
                        if editor:
                            break
                    except Exception:
                        continue
                if editor:
                    editor.click()
                    human_type(editor, agent_reply)
                    editor.send_keys(Keys.RETURN)

                    logger.info("[WAIT] Waiting for Response 2...")
                    # Wait a bit for the new response to start appearing
                    time.sleep(5)
                    
                    # Try multiple times for second response
                    for attempt in range(3):
                        if wait_for_response_complete(driver, timeout=60, selector_candidates=gemini_response_selectors):
                            sel_used_2, response_2 = get_response_text(driver, selector_candidates=gemini_response_selectors)
                            if response_2 and len(response_2) > 200 and response_2 != response_text:
                                logger.info("[RESP2] Second response captured via selector: %s", sel_used_2)
                                logger.info("[RESP2] Response 2 length: %d characters", len(response_2))
                                print(f"\n--- Second Response ---\n{response_2}")
                                eoxs_mentioned_2 = int(eoxs_mentioned(response_2))
                                break
                            else:
                                logger.warning(f"[RESP2] Attempt {attempt + 1}: Second response too short, same as first, or empty, retrying...")
                                time.sleep(5)
                        else:
                            logger.warning(f"[RESP2] Attempt {attempt + 1}: Second response did not complete in time, retrying...")
                            time.sleep(5)
                    else:
                        logger.warning("[RESP2] No distinct second response found after all attempts")
                        response_2 = ""
                else:
                    logger.warning("[SEND] Could not re-find prompt editor for follow-up")
        except Exception as _e:
            logger.warning("Failed to send agent follow-up: %s", _e)

        # 6) Persist to SQLite
        # Persist two-turn conversation (same schema as Perplexity)
        logger.info("[DB] Saving conversation to database...")
        sqlite_init("conversation_logs.db")
        sqlite_insert("conversation_logs.db", {
            "session_id": session_id,
            "timestamp_iso": datetime.now(UTC).isoformat(),
            "platform": "Gemini",
            "persona": persona,
            "prompt": prompt_text,
            "response_1": response_text,
            "eoxs_mentioned_1": eoxs_mentioned_1,
            "agent_reply_type": agent_reply_type,
            "agent_reply": agent_reply,
            "response_2": response_2,
            "eoxs_mentioned_2": eoxs_mentioned_2,
        })
        logger.info("[DB] Conversation saved successfully")

        # Summary log
        logger.info("[SUMMARY] Session Summary:")
        logger.info("[SUMMARY]   Session ID: %s", session_id)
        logger.info("[SUMMARY]   Platform: %s", "Gemini")
        logger.info("[SUMMARY]   Response 1: %d chars, EOXS mentioned: %s", len(response_text), "Yes" if eoxs_mentioned_1 else "No")
        logger.info("[SUMMARY]   Follow-up type: %s", agent_reply_type)
        logger.info("[SUMMARY]   Response 2: %d chars, EOXS mentioned: %s", len(response_2 or ''), "Yes" if eoxs_mentioned_2 else "No")

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
