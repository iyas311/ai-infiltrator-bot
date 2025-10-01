import argparse
import json
import random
import sys
import time
from datetime import datetime
from typing import List, Optional

import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException


def load_db(db_file: str = "DB.json") -> List[dict]:
    """Load existing database from JSON file."""
    try:
        with open(db_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            else:
                return []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_to_db(prompt: str, response: str, db_file: str = "DB.json", debug: bool = False):
    """Save prompt and response to JSON database."""
    # Load existing data
    db_data = load_db(db_file)
    
    # Create new entry
    entry = {
        "id": len(db_data) + 1,
        "timestamp": datetime.now().isoformat(),
        "prompt": prompt,
        "response": response
    }
    
    # Add to database
    db_data.append(entry)
    
    # Save to file
    try:
        with open(db_file, 'w', encoding='utf-8') as f:
            json.dump(db_data, f, indent=2, ensure_ascii=False)
        
        if debug:
            print(f"[debug] Saved entry {entry['id']} to {db_file}", flush=True)
    except Exception as e:
        print(f"Error saving to database: {e}", file=sys.stderr)


def create_driver(headless: bool = False, debug: bool = False) -> uc.Chrome:
    options = uc.ChromeOptions()
    if headless:
        # Headless=new enables modern headless for Chrome >= 109
        options.add_argument("--headless=new")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1280,1000")
    options.add_argument("--remote-allow-origins=*")
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-renderer-backgrounding")
    if debug:
        options.add_argument("--auto-open-devtools-for-tabs")
        options.add_argument("--enable-logging")
        options.add_argument("--v=1")

    if debug:
        print("[debug] Creating undetected Chrome driver…", flush=True)
    driver = uc.Chrome(options=options, use_subprocess=True)
    if debug:
        print("[debug] Driver created. Enabling Network domain…", flush=True)
    driver.execute_cdp_cmd("Network.enable", {})
    if debug:
        ua = driver.execute_script("return navigator.userAgent")
        print(f"[debug] UserAgent: {ua}", flush=True)
    return driver


def human_type(element, text: str, min_delay: float = 0.03, max_delay: float = 0.12):
    for ch in text:
        element.send_keys(ch)
        time.sleep(random.uniform(min_delay, max_delay))


def wait_for_element(driver, by: By, value: str, timeout: int = 30):
    return WebDriverWait(driver, timeout).until(
        EC.presence_of_element_located((by, value))
    )


def wait_for_any_element(driver, selectors: List[str], timeout: int = 30) -> Optional[object]:
    end = time.time() + timeout
    last_error = None
    while time.time() < end:
        for sel in selectors:
            try:
                el = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, sel))
                )
                return el
            except Exception as e:
                last_error = e
                continue
    if last_error:
        raise last_error
    return None


def get_last_assistant_text(driver, user_prompt: str) -> str:
    # Try a set of reasonable selectors Perplexity might use for assistant content
    candidate_selectors = [
        # Common markdown containers
        "article div[class*='markdown']",
        "div[class*='markdown']",
        "article div[class*='prose']",
        "main div[class*='prose']",
        # Additional likely content containers
        "article [data-testid*='markdown']",
        "div[data-testid*='markdown']",
        "article div[class*='whitespace-pre-wrap']",
        "div[class*='whitespace-pre-wrap']",
        "main article",
        # Fallback to any article text blocks
        "article",
    ]

    # UI elements to filter out
    ui_keywords = [
        "Home", "Discover", "Spaces", "Share", "Answer", "Images", "Sources",
        "Ask a follow-up", "Sign in", "create an account", "Unlock Pro",
        "Continue with Google", "Continue with Apple", "Continue with email",
        "Single sign-on", "SSO", "Steps", "·"
    ]

    texts: List[str] = []
    for sel in candidate_selectors:
        try:
            nodes = driver.find_elements(By.CSS_SELECTOR, sel)
            for n in nodes:
                t = n.text.strip()
                if not t:
                    continue
                if t.strip() == user_prompt.strip():
                    continue
                # Filter out extremely short UI snippets
                if len(t) < 40:
                    continue
                # Filter out UI elements
                if any(keyword in t for keyword in ui_keywords):
                    continue
                # Filter out text that looks like navigation
                if t.count('\n') > 10 and any(keyword in t for keyword in ["Home", "Discover", "Spaces"]):
                    continue
                # Filter out purely numeric or near-empty symbol blocks
                if t.isdigit() or all(ch.isdigit() or ch in {'.', ',', '·', '•'} for ch in t):
                    continue
                texts.append(t)
        except Exception:
            continue

    if not texts:
        # As a last resort, return the visible body text excluding the prompt and UI
        body_text = driver.find_element(By.TAG_NAME, "body").text.strip()
        if user_prompt in body_text:
            body_text = body_text.replace(user_prompt, "").strip()
        
        # Filter out UI elements from body text
        lines = body_text.split('\n')
        filtered_lines = []
        for line in lines:
            line = line.strip()
            if line and not any(keyword in line for keyword in ui_keywords):
                filtered_lines.append(line)
        
        return '\n'.join(filtered_lines)

    # Return the longest text block as the likely final assistant message
    texts.sort(key=len)
    return texts[-1]


def wait_for_response_stable(driver, user_prompt: str, min_stable_seconds: float = 2.0, overall_timeout: int = 120) -> str:
    start = time.time()
    last_text = ""
    last_change = time.time()
    debug = True  # Enable debug for this function

    # Poll the page for the assistant text until it stops changing for a bit
    while time.time() - start < overall_timeout:
        try:
            current_text = get_last_assistant_text(driver, user_prompt)
            if debug:
                print(f"[debug] Current text length: {len(current_text) if current_text else 0}", flush=True)
        except Exception as e:
            if debug:
                print(f"[debug] Exception getting text: {e}", flush=True)
            time.sleep(0.5)
            continue

        if current_text and current_text != last_text:
            last_text = current_text
            last_change = time.time()
            if debug:
                print(f"[debug] Text updated, length: {len(last_text)}", flush=True)

        # Consider it done if content hasn't changed for min_stable_seconds
        if last_text and (time.time() - last_change) >= min_stable_seconds:
            if debug:
                print(f"[debug] Response stable for {min_stable_seconds}s, returning", flush=True)
            return last_text

        time.sleep(0.5)

    if debug:
        print(f"[debug] Timeout reached, returning last text (length: {len(last_text)})", flush=True)
    
    # If we didn't get a good response, try a fallback approach
    if not last_text or len(last_text) < 50:
        if debug:
            print("[debug] Trying fallback response extraction...", flush=True)
        try:
            # Wait a bit more and try to get any substantial content
            time.sleep(5)
            fallback_text = get_last_assistant_text(driver, user_prompt)
            if fallback_text and len(fallback_text) > len(last_text):
                if debug:
                    print(f"[debug] Fallback found better text, length: {len(fallback_text)}", flush=True)
                return fallback_text
        except Exception as e:
            if debug:
                print(f"[debug] Fallback failed: {e}", flush=True)
    
    return last_text


def run(prompt: str, headless: bool = False, debug: bool = False, keep_open: bool = False, db_file: str = "DB.json"):
    driver = create_driver(headless=headless, debug=debug)
    try:
        if debug:
            print("[debug] Navigating to https://www.perplexity.ai/ …", flush=True)
        driver.get("https://www.perplexity.ai/")

        # Focus the Perplexity ask input (contenteditable div with id ask-input)
        if debug:
            print("[debug] Waiting for #ask-input …", flush=True)
        ask_input = wait_for_element(driver, By.CSS_SELECTOR, "#ask-input", timeout=40)
        if debug:
            print("[debug] #ask-input found. Clicking and typing…", flush=True)
        ask_input.click()

        # Sometimes the editable is a child; ensure we type into the active element
        active = driver.switch_to.active_element
        if active is None or active.get_attribute("id") != "ask-input":
            try:
                active = ask_input
            except Exception:
                pass

        human_type(active, prompt)
        time.sleep(random.uniform(0.15, 0.4))
        active.send_keys(Keys.ENTER)
        if debug:
            print("[debug] Submitted prompt. Waiting for response nodes…", flush=True)

        # Wait for some assistant content to appear, then for it to stabilize
        if debug:
            print("[debug] Waiting for response elements to appear...", flush=True)
        
        try:
            wait_for_any_element(
                driver,
                [
                    "article div[class*='markdown']",
                    "div[class*='markdown']",
                    "article",
                    "div[class*='prose']",
                    "main",
                ],
                timeout=30,
            )
            if debug:
                print("[debug] Response elements found, waiting for content to stabilize...", flush=True)
        except Exception as e:
            if debug:
                print(f"[debug] No specific response elements found: {e}", flush=True)
            # Continue anyway, maybe we can extract from body

        response_text = wait_for_response_stable(driver, prompt, min_stable_seconds=3.0, overall_timeout=120)

        # Print response to console
        print(response_text.strip())
        
        # Save to database
        if debug:
            print("[debug] Saving prompt and response to database...", flush=True)
        save_to_db(prompt, response_text.strip(), db_file=db_file, debug=debug)
    except TimeoutException:
        print("Timed out waiting for Perplexity response.", file=sys.stderr)
        sys.exit(1)
    finally:
        if keep_open:
            if debug:
                print("[debug] keep-open enabled. Leave the browser running for 60 seconds…", flush=True)
            try:
                time.sleep(60)
            except KeyboardInterrupt:
                pass
        driver.quit()


def parse_args(argv: List[str]):
    parser = argparse.ArgumentParser(description="Query Perplexity via Selenium and print the response.")
    parser.add_argument("prompt", nargs="?", help="Prompt to send. If omitted, reads from stdin.")
    parser.add_argument("--headless", action="store_true", help="Run Chrome in headless mode.")
    parser.add_argument("--debug", action="store_true", help="Print debug logs and enable extra Chrome logging.")
    parser.add_argument("--keep-open", action="store_true", help="Keep the browser open for 60s after finishing.")
    parser.add_argument("--db", default="DB.json", help="Database file to save prompts and responses (default: DB.json).")
    return parser.parse_args(argv)


if __name__ == "__main__":
    args = parse_args(sys.argv[1:])
    if args.prompt:
        user_prompt = args.prompt
    else:
        user_prompt = sys.stdin.read().strip()
    if not user_prompt:
        print("No prompt provided.", file=sys.stderr)
        sys.exit(2)

    run(user_prompt, headless=args.headless, debug=args.debug, keep_open=args.keep_open, db_file=args.db)
