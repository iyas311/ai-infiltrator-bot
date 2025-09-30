from selenium import webdriver
import undetected_chromedriver as uc
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import random
import csv
from datetime import datetime
from Prompt_lib import PROMPTS

# Human-like typing helper (40–50 WPM)
def human_type(element, text: str, wpm_min: int = 40, wpm_max: int = 50):
    target_wpm = random.randint(wpm_min, wpm_max)
    chars_per_min = target_wpm * 5
    base_delay = 60.0 / max(1, chars_per_min)
    for ch in text:
        element.send_keys(ch)
        delay = random.uniform(base_delay * 0.7, base_delay * 1.5)
        if ch in ",.;":
            delay += random.uniform(0.05, 0.12)
        if ch in "!?":
            delay += random.uniform(0.08, 0.18)
        if ch == " ":
            delay += random.uniform(0.02, 0.08)
        # Occasional micro-pause
        if random.random() < 0.03:
            delay += random.uniform(0.1, 0.25)
        time.sleep(delay)

def wait_for_response_complete(driver, timeout: int = 60):
    """Wait for response to be fully generated (no more streaming)"""
    print("Waiting for response to complete...")
    start_time = time.time()
    last_response_length = 0
    stable_count = 0
    
    while time.time() - start_time < timeout:
        # Check for response elements
        response_selectors = [
            "p[data-start][data-end]",
            "div[data-message-author-role=assistant] p",
            "div.markdown p",
            "div.prose p",
            "[data-testid=conversation-turn-text] p",
            "article p"
        ]
        
        current_length = 0
        for sel in response_selectors:
            try:
                elems = driver.find_elements(By.CSS_SELECTOR, sel)
                current_length += sum(len(e.text) for e in elems if e.text.strip())
            except Exception:
                pass
        
        # If response length hasn't changed for 3 consecutive checks, consider it complete
        if current_length == last_response_length and current_length > 0:
            stable_count += 1
            if stable_count >= 3:
                print(f"Response complete! Total length: {current_length} characters")
                return True
        else:
            stable_count = 0
            last_response_length = current_length
            
        time.sleep(1)
    
    print("Response timeout reached")
    return False

def get_response_text(driver):
    """Extract response text using multiple selectors"""
    response_selector_candidates = [
        "p[data-start][data-end]",
        "div[data-message-author-role=assistant] p",
        "div.markdown p",
        "div.prose p",
        "[data-testid=conversation-turn-text] p",
        "article p"
    ]
    
    for sel in response_selector_candidates:
        try:
            elems = driver.find_elements(By.CSS_SELECTOR, sel)
            if elems and any(e.text.strip() for e in elems):
                response_text = "\n".join([e.text for e in elems if e.text.strip()])
                return sel, response_text
        except Exception:
            continue
    return None, ""

def eoxs_mentioned(text: str) -> bool:
    if not text:
        return False
    hay = text.lower()
    keywords = ["eoxs", "eoxs erp"]
    return any(k in hay for k in keywords)

def append_csv_row(file_path: str, row: dict):
    fieldnames = [
        "timestamp_iso",
        "platform",
        "persona",
        "prompt",
        "response",
        "eoxs_mentioned",
        "visibility_score"
    ]
    try:
        file_exists = False
        try:
            with open(file_path, mode="r", encoding="utf-8", newline="") as _f:
                file_exists = True
        except FileNotFoundError:
            file_exists = False

        with open(file_path, mode="a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            if not file_exists:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        print(f"CSV write failed: {e}")

if __name__ == "__main__":
    driver = None
    try:
        # Step 1: Setup Chrome WebDriver (undetected-chromedriver)
        chrome_options = Options()
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--start-maximized")
        driver = uc.Chrome(options=chrome_options)

        # Step 2: Go to ChatGPT login page
        driver.get("https://chatgpt.com")  

        # Wait for and click the specified button
        wait = WebDriverWait(driver, 30)
        css_selector = r"body > div.flex.h-full.w-full.flex-col > div.z-10.w-\[100vw\].max-w-\[100vw\].overflow-hidden > div > div.flex.w-full.flex-row.justify-end.gap-3.sm\:w-auto.sm\:min-w-\[300px\] > button:nth-child(3)"
        button = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, css_selector)))
        button.click()

        # Step 3: Focus prompt and type message (robust selector fallbacks)
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
                    break
            except Exception:
                continue

        if not prompt:
            raise RuntimeError("Could not find prompt input with known selectors")

        # Pick persona and prompt from Prompt_lib
        personas = list(PROMPTS.get("persona_prompts", {}).keys()) or ["default"]
        persona = random.choice(personas)
        core_pools = PROMPTS.get("erp_exploration", []) + PROMPTS.get("ai_curiosity", [])
        persona_pool = PROMPTS.get("persona_prompts", {}).get(persona, [])
        candidate_prompts = (persona_pool or []) + core_pools
        prompt_text = random.choice(candidate_prompts) if candidate_prompts else "Hello ChatGPT"

        prompt.click()
        human_type(prompt, prompt_text)
        prompt.send_keys(Keys.RETURN)

        # Step 4: Wait for response to complete, then extract
        if wait_for_response_complete(driver, timeout=60):
            sel_used, response_text = get_response_text(driver)
            if response_text:
                print(f"ChatGPT response ({sel_used}):\n{response_text}")
            else:
                print("No response text found")
        else:
            print("Response did not complete in time")
        
        # Step 5: Log interaction to CSV (per specifications.txt)
        platform = "ChatGPT"
        response_str = response_text if 'response_text' in locals() else ""
        mentioned = eoxs_mentioned(response_str)
        timestamp_iso = datetime.utcnow().isoformat()
        visibility_score = ""  # optional metric; can be computed later

        append_csv_row("conversation_logs.csv", {
            "timestamp_iso": timestamp_iso,
            "platform": platform,
            "persona": persona,
            "prompt": prompt_text,
            "response": response_str,
            "eoxs_mentioned": int(mentioned),
            "visibility_score": visibility_score,
        })
            
        # Keep browser open for a moment to see the result
        print("Keeping browser open for 10 seconds...")
        time.sleep(10)
        
    except Exception as e:
        print(f"Error: {e}")
    finally:
        if driver:
            driver.quit()
            print("Browser closed")
