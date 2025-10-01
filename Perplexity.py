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

from Prompt_lib import PROMPTS
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
    personas = list(PROMPTS.get("persona_prompts", {}).keys()) or ["default"]
    persona = random.choice(personas)
    core_pools = PROMPTS.get("erp_exploration", []) + PROMPTS.get("ai_curiosity", [])
    persona_pool = PROMPTS.get("persona_prompts", {}).get(persona, [])
    candidate_prompts = (persona_pool or []) + core_pools
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
        driver = create_driver(headless=headless)
        wait = WebDriverWait(driver, 30)

        # 1) Navigate to Perplexity
        logger.info("Navigating to Perplexity")
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

        # 4) Type the prompt and submit
        prompt_el.click()
        human_type(prompt_el, prompt_text)
        prompt_el.send_keys(Keys.RETURN)

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
                logger.info("Perplexity response captured")
                print(response_text)
            else:
                logger.warning("No response text found")
        else:
            response_text = ""
            logger.warning("Response did not complete in time")

        # 6) Persist to SQLite
        platform = "Perplexity"
        mentioned = eoxs_mentioned(response_text)
        timestamp_iso = datetime.now(UTC).isoformat()
        record = {
            "session_id": session_id,
            "timestamp_iso": timestamp_iso,
            "platform": platform,
            "persona": persona,
            "prompt": prompt_text,
            "response": response_text,
            "eoxs_mentioned": int(mentioned),
            "visibility_score": "",
        }
        sqlite_init("conversation_logs.db")
        sqlite_insert("conversation_logs.db", record)

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
