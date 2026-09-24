# invisible_selenium

Selenium's API on a patched Firefox with a deterministic stealth profile. Change
the import, keep the script.

```bash
uv venv
uv pip install -e .
uv run invisible-selenium fetch
```

```python
from invisible_selenium import webdriver
from invisible_selenium.webdriver.common.by import By
from invisible_selenium.webdriver.support.ui import WebDriverWait
from invisible_selenium.webdriver.support import expected_conditions as EC

driver = webdriver.Firefox(seed=42)
driver.get("https://example.com")
WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.TAG_NAME, "a"))).click()
driver.quit()
```

```python
driver = webdriver.Firefox(
    seed=42,                        # same seed, same fingerprint
    proxy={"server": "socks5://host:1080", "username": "u", "password": "p"},
    headless=True,                  # hidden desktop, real rendering
    profile_dir="./profile",        # cookies and storage survive the run
)
```

```bash
uv run pytest -q                      # unit
uv run pytest -q -m e2e               # against the real browser
```
