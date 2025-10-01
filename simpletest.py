from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
import time
# Step 1: Setup Chrome WebDriver
driver = webdriver.Chrome()  # Ensure chromedriver is in PATH
# Step 2: Go to ChatGPT login page
driver.get("https://chatgpt.com/?model=auto")  

# Step 3: Find the input textarea (ChatGPT prompt box
input_box = driver.find_element(By.TAG_NAME, "textarea")
print(input_box)
time.sleep(20)
# Step 4: Type a message
input_box.send_keys("Hello ChatGPT, can you print a simple Python script?")
input_box.send_keys(Keys.RETURN)

# Step 5: Wait for response to appear (adjust sleep if needed)
time.sleep(10)

# Step 6: Get response from ChatGPT
# The responses are typically in divs with role="presentation"
responses = driver.find_elements(By.CSS_SELECTOR, "div[class*='prose']")  

for r in responses:
    print("ChatGPT:", r.text)

# Step 7: Close browser
driver.quit()
