import random
import time


def human_type(element, text: str, wpm_min: int = 100, wpm_max: int = 300):
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
        if random.random() < 0.03:
            delay += random.uniform(0.1, 0.25)
        time.sleep(delay)
