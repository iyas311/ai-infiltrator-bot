from selenium import webdriver
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
from datetime import datetime, UTC
from Prompt_lib import INIT_PROMPTS
from reply_eoxs_found import REPLY_EOXS_FOUND
from reply_eoxs_not_found import REPLY_EOXS_NOT_FOUND
from utils.logger import configure_logging, get_logger
import uuid
from utils.browser_utils import human_type
from utils.db_utils import sqlite_init, sqlite_insert, sqlite_update_second_response


def eoxs_mentioned(text: str) -> bool:
    if not text:
        return False
    hay = text.lower()
    keywords = ["eoxs", "eoxs erp"]
    return any(k in hay for k in keywords)

logger = get_logger(__name__)

def wait_for_response_complete(driver, timeout: int = 75, selector_candidates=None) -> bool:
    start_time = time.time()
    last_change_time = start_time
    last_length = 0
    stable_count = 0
    required_stable_cycles = 3
    idle_grace_seconds = 4  # allow brief gap before we start checking idle
    max_idle_seconds = 7    # if no growth for this long (after grace), consider done
    logger = get_logger(__name__)

    response_selectors = selector_candidates or [
        "p[data-start][data-end]",
        "div[data-message-author-role=assistant] p",
        "div.markdown p",
        "div.prose p",
        "[data-testid=conversation-turn-text] p",
        "article p",
    ]

    while True:
        now = time.time()
        elapsed = now - start_time
        if elapsed > timeout:
            logger.warning("Response timeout reached after %ss", timeout)
            return last_length > 0

        # Keep viewport at the bottom to let new content render
        try:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        except Exception:
            pass

        current_length = 0
        for sel in response_selectors:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                current_length += sum(len(e.text) for e in elems if e.text.strip())
            except Exception:
                continue

        if current_length > last_length:
            last_change_time = now
            last_length = current_length
            stable_count = 0
            # Log progress every 100 characters
            if current_length % 100 == 0 or current_length - last_length > 50:
                logger.debug("[PROGRESS] Response progress: %d characters", current_length)
        elif current_length > 0:
            stable_count += 1

        # Early finish if content present and idle too long after grace
        if last_length > 0 and (now - start_time) > idle_grace_seconds and (now - last_change_time) > max_idle_seconds:
            logger.debug("[COMPLETE] Response complete (idle): %d chars, idle for %ds", last_length, int(now - last_change_time))
            return True

        # Or if a few consecutive stable cycles reached with content
        if last_length > 0 and stable_count >= required_stable_cycles:
            logger.debug("[COMPLETE] Response complete (stable): %d chars, %d stable cycles", last_length, stable_count)
            return True

        time.sleep(0.8)

def wait_for_response_complete_simple(driver, timeout: int = 90, selector_candidates=None) -> bool:
    """Simple waiting logic from Perplexity - more reliable for second responses"""
    start_time = time.time()
    last_response_length = 0
    stable_count = 0

    response_selectors = selector_candidates or [
        "p[data-start][data-end]",
        "div[data-message-author-role=assistant] p",
        "div.markdown p",
        "div.prose p",
        "[data-testid=conversation-turn-text] p",
        "article p",
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

def get_response_text(driver, selector_candidates=None):
    candidates = selector_candidates or [
        "p[data-start][data-end]",
        "div[data-message-author-role=assistant] p",
        "div.markdown p",
        "div.prose p",
        "[data-testid=conversation-turn-text] p",
        "article p",
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


if __name__ == "__main__":
    configure_logging()
    driver = None
    session_id = str(uuid.uuid4())
    try:
        # Ensure DB schema exists before any inserts
        sqlite_init("conversation_logs.db")
        # Step 1: Setup Chrome WebDriver (undetected-chromedriver)
        chrome_options = Options()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--start-maximized")
        # Match installed Chrome major version to avoid driver mismatch errors
        driver = uc.Chrome(options=chrome_options, version_main=140)

        # Step 2: Go to ChatGPT login page
        logger.info("[NAV] Navigating to ChatGPT")
        driver.get("https://chatgpt.com")  

        # Wait for and click the specified button
        wait = WebDriverWait(driver, 30)
        css_selector = r"body > div.flex.h-full.w-full.flex-col > div.z-10.w-\[100vw\].max-w-\[100vw\].overflow-hidden > div > div.flex.w-full.flex-row.justify-end.gap-3.sm\:w-auto.sm\:min-w-\[300px\] > button:nth-child(3)"
        logger.info("[BTN] Waiting for login button to be clickable")
        button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector)))
        button.click()
        logger.info("[BTN] Login button clicked successfully")

        # Step 3: Focus prompt and type message (robust selector fallbacks)
        logger.info("[PROMPT] Looking for prompt input field")
        prompt_selectors = [
            "#prompt-textarea > p",
            "textarea",
            "[data-testid=prompt-textarea]",
            "div[contenteditable=true][role=textbox]",
            "div[contenteditable=true]"
        ]
        prompt = None
        for sel in prompt_selectors:
            try:
                prompt = wait.until(EC.visibility_of_element_located((By.CSS_SELECTOR, sel)))
                if prompt:
                    logger.info("[PROMPT] Found prompt input field")
                    break
            except Exception:
                continue

        if not prompt:
            raise RuntimeError("Could not find prompt input with known selectors")

        # Pick prompt from INIT_PROMPTS
        persona = "implicit"
        prompt_text = random.choice(INIT_PROMPTS) if INIT_PROMPTS else "Hello ChatGPT"
        logger.info("[PROMPT] Selected prompt: %s", prompt_text[:50] + "..." if len(prompt_text) > 50 else prompt_text)

        prompt.click()
        human_type(prompt, prompt_text)
        prompt.send_keys(Keys.RETURN)
        logger.info("[SEND] Sent initial prompt to ChatGPT")

        # Step 4: Wait for response to complete, then extract (ChatGPT selectors)
        logger.info("[WAIT] Waiting for ChatGPT response...")
        chatgpt_response_selectors = [
            "p[data-start][data-end]",
            "div[data-message-author-role=assistant] p",
            "div.markdown p",
            "div.prose p",
            "[data-testid=conversation-turn-text] p",
            "article p",
        ]
        if wait_for_response_complete(driver, timeout=75, selector_candidates=chatgpt_response_selectors):
            sel_used, response_text = get_response_text(driver, selector_candidates=chatgpt_response_selectors)
            if response_text:
                logger.info("[RESP1] Got Response 1 via selector: %s", sel_used)
                logger.info("[RESP1] Response 1 length: %d characters", len(response_text))
            else:
                logger.warning("[RESP1] No response text found")
        else:
            logger.warning("[RESP1] Response did not complete in time")
        
        # Step 5: Process responses and prepare data for database
        platform = "ChatGPT"
        response_str = response_text if 'response_text' in locals() else ""
        mentioned = eoxs_mentioned(response_str)
        timestamp_iso = datetime.now(UTC).isoformat()
        
        # Initialize response_2 variables
        response_2_str = ""
        eoxs_mentioned_2 = 0
        agent_reply = ""
        agent_reply_type = "none"

        # Decide on EOXS follow-up based on mention and send a second turn
        if response_str.strip():
            try:
                if mentioned:
                    agent_reply_type = "reinforce"
                    agent_reply = random.choice(REPLY_EOXS_FOUND)
                    logger.info("[FOLLOW] EOXS mentioned in Response 1 - preparing reinforce follow-up")
                else:
                    agent_reply_type = "inject"
                    agent_reply = random.choice(REPLY_EOXS_NOT_FOUND)
                    logger.info("[FOLLOW] EOXS not mentioned in Response 1 - preparing inject follow-up")

                if agent_reply:
                    logger.info("[SEND] Sending follow-up (%s): %s", agent_reply_type, agent_reply[:50] + "..." if len(agent_reply) > 50 else agent_reply)
                    prompt.click()
                    human_type(prompt, agent_reply)
                    prompt.send_keys(Keys.RETURN)
                    
                    # Wait for second response to complete and capture it
                    logger.info("[WAIT] Waiting for Response 2...")
                    if wait_for_response_complete_simple(
                        driver, timeout=90, selector_candidates=chatgpt_response_selectors
                    ):
                        sel_used_2, response_text_2 = get_response_text(
                            driver, selector_candidates=chatgpt_response_selectors
                        )
                        if response_text_2:
                            response_2_str = response_text_2
                            eoxs_mentioned_2 = int(eoxs_mentioned(response_text_2))
                            logger.info("[RESP2] Got Response 2 via selector: %s", sel_used_2)
                            logger.info("[RESP2] Response 2 length: %d characters", len(response_text_2))
                            logger.info("[RESP2] EOXS mentioned in Response 2: %s", "Yes" if eoxs_mentioned_2 else "No")
                            print("Second response:")
                            print(response_text_2)
                            # Update only the second response fields
                            sqlite_update_second_response(
                                "conversation_logs.db", 
                                session_id, 
                                response_text_2, 
                                eoxs_mentioned_2
                            )
                        else:
                            logger.warning("[RESP2] No response text found")
                    else:
                        logger.warning("[RESP2] Response did not complete in time")
            except Exception as e:
                logger.warning("[ERROR] Failed to send agent follow-up: %s", e)

        # Prepare complete record for database
        record = {
            "session_id": session_id,
            "timestamp_iso": timestamp_iso,
            "platform": platform,
            "persona": persona,
            "prompt": prompt_text,
            "response_1": response_str,
            "eoxs_mentioned_1": int(mentioned),
            "agent_reply_type": agent_reply_type,
            "agent_reply": agent_reply,
            "response_2": response_2_str,
            "eoxs_mentioned_2": eoxs_mentioned_2,
        }

        # Single database operation with all data
        logger.info("[DB] Saving conversation to database...")
        sqlite_init("conversation_logs.db")
        sqlite_insert("conversation_logs.db", record)
        logger.info("[DB] Conversation saved successfully")
        
        # Summary log
        logger.info("[SUMMARY] Session Summary:")
        logger.info("[SUMMARY]   Session ID: %s", session_id)
        logger.info("[SUMMARY]   Platform: %s", platform)
        logger.info("[SUMMARY]   Response 1: %d chars, EOXS mentioned: %s", len(response_str), "Yes" if mentioned else "No")
        logger.info("[SUMMARY]   Follow-up type: %s", agent_reply_type)
        logger.info("[SUMMARY]   Response 2: %d chars, EOXS mentioned: %s", len(response_2_str), "Yes" if eoxs_mentioned_2 else "No")
            
        # Keep browser open for a moment to see the result
        logger.info("[WAIT] Keeping browser open for 10 seconds...")
        time.sleep(10)
        
    except Exception as e:
        logger.exception("[ERROR] Error occurred: %s", e)
    finally:
        if driver:
            driver.quit()
            logger.info("[CLEANUP] Browser closed")
