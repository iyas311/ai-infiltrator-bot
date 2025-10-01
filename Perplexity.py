import argparse
import random
import sys
import time
import uuid
from datetime import datetime, UTC
from typing import List, Optional, Tuple
from utils.logger import configure_logging, get_logger

import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from Prompt_lib import INIT_PROMPTS
from reply_eoxs_found import REPLY_EOXS_FOUND
from reply_eoxs_not_found import REPLY_EOXS_NOT_FOUND
logger = get_logger(__name__)
from utils.browser_utils import human_type
from utils.db_utils import sqlite_init, sqlite_insert


def create_driver(headless: bool = False, version_main: Optional[int] = 140) -> uc.Chrome:
    chrome_options = Options()
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--start-maximized")
    if headless:
        chrome_options.add_argument("--headless=new")
    return uc.Chrome(options=chrome_options, version_main=version_main)


def wait_for_response_complete(driver, timeout: int = 90, selector_candidates: Optional[List[str]] = None) -> bool:
    start_time = time.time()
    last_response_length = 0
    stable_count = 0

    response_selectors = selector_candidates or [
        # Perplexity tends to render assistant content as paragraphs inside markdown/prose containers
        "article div[class*='markdown'] p",
        "div[class*='markdown'] p",
        "article div[class*='prose'] p",
        "div[class*='prose'] p",
        "article p",
        "main article p",
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
            stable_count += 1
            if stable_count >= 3:
                return True
        else:
            stable_count = 0
            last_response_length = current_length
        time.sleep(1)

    return False


def get_response_text(driver, selector_candidates: Optional[List[str]] = None) -> Tuple[Optional[str], str]:
    candidates = selector_candidates or [
        "article div[class*='markdown'] p",
        "div[class*='markdown'] p",
        "article div[class*='prose'] p",
        "div[class*='prose'] p",
        "article p",
        "main article p",
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


def pick_prompt_from_library() -> Tuple[str, str]:
    persona = "implicit"
    candidate_prompts = INIT_PROMPTS
    prompt_text = random.choice(candidate_prompts) if candidate_prompts else "Hello Perplexity"
    return persona, prompt_text


def eoxs_mentioned(text: str) -> bool:
    if not text:
        return False
    hay = text.lower()
    return any(k in hay for k in ["eoxs", "eoxs erp"])


def run(session_id: str, override_prompt: Optional[str] = None, headless: bool = False):
    driver = None
    try:
        configure_logging()
        sqlite_init("conversation_logs.db")
        driver = create_driver(headless=headless)
        wait = WebDriverWait(driver, 30)

        # 1) Navigate to Perplexity
        logger.info("[NAV] Navigating to Perplexity")
        driver.get("https://www.perplexity.ai/")

        # 2) Find the input (robust selectors)
        prompt_selectors = [
            "#ask-input",
            "div[contenteditable=true][id=ask-input]",
            "div[contenteditable=true][role=textbox]",
            "div[contenteditable=true]",
        ]
        prompt_el = None
        for sel in prompt_selectors:
            try:
                prompt_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
                if prompt_el:
                    break
            except Exception:
                continue
        if not prompt_el:
            raise RuntimeError("Could not find Perplexity prompt input with known selectors")

        # 3) Choose prompt
        if override_prompt and override_prompt.strip():
            persona = "custom"
            prompt_text = override_prompt.strip()
        else:
            persona, prompt_text = pick_prompt_from_library()
        logger.info("[PROMPT] Selected prompt: %s", prompt_text[:50] + "..." if len(prompt_text) > 50 else prompt_text)

        # 4) Type the prompt and submit
        prompt_el.click()
        human_type(prompt_el, prompt_text)
        prompt_el.send_keys(Keys.RETURN)
        logger.info("[SEND] Sent initial prompt to Perplexity")

        # 5) Wait for response to complete and extract
        perplexity_response_selectors = [
            "article div[class*='markdown'] p",
            "div[class*='markdown'] p",
            "article div[class*='prose'] p",
            "div[class*='prose'] p",
            "article p",
            "main article p",
        ]
        if wait_for_response_complete(driver, timeout=90, selector_candidates=perplexity_response_selectors):
            sel_used, response_text = get_response_text(driver, selector_candidates=perplexity_response_selectors)
            if response_text:
                logger.info("[RESP1] Response captured via selector: %s", sel_used)
                logger.info("[RESP1] Response length: %d characters", len(response_text))
                print(response_text)
            else:
                logger.warning("[RESP1] No response text found")
        else:
            response_text = ""
            logger.warning("[RESP1] Response did not complete in time")

        # 6) Follow-up agent reply and second response
        platform = "Perplexity"
        mentioned = eoxs_mentioned(response_text)
        timestamp_iso = datetime.now(UTC).isoformat()
        agent_reply = ""
        agent_reply_type = "none"
        response_2 = ""
        eoxs_mentioned_2 = False

        try:
            if response_text.strip():
                if mentioned:
                    agent_reply_type = "reinforce"
                    agent_reply = random.choice(REPLY_EOXS_FOUND)
                else:
                    agent_reply_type = "inject"
                    agent_reply = random.choice(REPLY_EOXS_NOT_FOUND)

                if agent_reply:
                    logger.info("[SEND] Sending follow-up (%s)", agent_reply_type)
                    # Re-find the input element as it may have become stale
                    prompt_el = None
                    for sel in prompt_selectors:
                        try:
                            prompt_el = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
                            if prompt_el:
                                break
                        except Exception:
                            continue
                    
                    if prompt_el:
                        prompt_el.click()
                        human_type(prompt_el, agent_reply)
                        prompt_el.send_keys(Keys.RETURN)
                    else:
                        logger.warning("Could not re-find prompt element for follow-up")

                    # Wait for second response
                    logger.info("[WAIT] Waiting for Response 2...")
                    if wait_for_response_complete(driver, timeout=90, selector_candidates=perplexity_response_selectors):
                        sel_used_2, response_2 = get_response_text(driver, selector_candidates=perplexity_response_selectors)
                        if response_2:
                            logger.info("[RESP2] Second response captured via selector: %s", sel_used_2)
                            logger.info("[RESP2] Response 2 length: %d characters", len(response_2))
                            print(f"\n--- Second Response ---\n{response_2}")
                            eoxs_mentioned_2 = eoxs_mentioned(response_2)
                        else:
                            logger.warning("[RESP2] No second response text found")
                    else:
                        logger.warning("[RESP2] Second response did not complete in time")
        except Exception as _e:
            logger.warning("Failed to send agent follow-up: %s", _e)

        # Store complete conversation
        logger.info("[DB] Saving conversation to database...")
        sqlite_init("conversation_logs.db")
        sqlite_insert("conversation_logs.db", {
            "session_id": session_id,
            "timestamp_iso": timestamp_iso,
            "platform": platform,
            "persona": persona,
            "prompt": prompt_text,
            "response_1": response_text,
            "eoxs_mentioned_1": int(mentioned),
            "agent_reply_type": agent_reply_type,
            "agent_reply": agent_reply,
            "response_2": response_2,
            "eoxs_mentioned_2": int(eoxs_mentioned_2),
        })
        logger.info("[DB] Conversation saved successfully")

        # Summary log
        logger.info("[SUMMARY] Session Summary:")
        logger.info("[SUMMARY]   Session ID: %s", session_id)
        logger.info("[SUMMARY]   Platform: %s", platform)
        logger.info("[SUMMARY]   Response 1: %d chars, EOXS mentioned: %s", len(response_text), "Yes" if mentioned else "No")
        logger.info("[SUMMARY]   Follow-up type: %s", agent_reply_type)
        logger.info("[SUMMARY]   Response 2: %d chars, EOXS mentioned: %s", len(response_2 or ''), "Yes" if eoxs_mentioned_2 else "No")

        # Keep open briefly
        time.sleep(5)

    except Exception as e:
        logger.exception("Error: %s", e)
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Perplexity automation: query and store conversation logs")
    parser.add_argument("--session-id", default=str(uuid.uuid4()))
    parser.add_argument("--prompt", help="Override prompt text (otherwise uses Prompt_lib)")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()
    run(session_id=args.session_id, override_prompt=args.prompt, headless=args.headless)