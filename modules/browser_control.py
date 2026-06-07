"""Browser and YouTube control for Arrow."""

import platform
import re
import subprocess
import urllib.parse
import webbrowser

import requests
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from webdriver_manager.chrome import ChromeDriverManager

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Arrow/1.0; +https://example.com)"
}

CHROME_COMMANDS = {
    "Windows": ["cmd", "/c", "start", "chrome"],
    "Linux": ["google-chrome"],
    "Darwin": ["open", "-a", "Google Chrome"],
}

_DRIVER = None


def _run_command(command: list[str]) -> bool:
    try:
        subprocess.Popen(command)
        return True
    except FileNotFoundError:
        return False
    except Exception:
        return False


def _init_driver() -> webdriver.Chrome | None:
    global _DRIVER
    if _DRIVER is not None:
        return _DRIVER

    options = webdriver.ChromeOptions()
    options.add_argument("--start-maximized")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_experimental_option("excludeSwitches", ["enable-logging"])

    try:
        service = Service(ChromeDriverManager().install())
        _DRIVER = webdriver.Chrome(service=service, options=options)
        return _DRIVER
    except WebDriverException:
        _DRIVER = None
        return None
    except Exception:
        _DRIVER = None
        return None


def open_chrome(url: str | None = None) -> bool:
    """Open Chrome, optionally with a target URL."""
    system_name = platform.system()
    command = CHROME_COMMANDS.get(system_name)
    if not command:
        return False

    if url:
        command = command + [url]

    if _run_command(command):
        return True

    try:
        if url:
            webbrowser.open(url)
        else:
            webbrowser.open("https://www.google.com")
        return True
    except Exception:
        return False


def open_url(url: str) -> bool:
    driver = _init_driver()
    if not driver:
        return open_chrome(url)

    try:
        driver.get(url)
        return True
    except Exception:
        return open_chrome(url)


def _youtube_search_url(query: str) -> str:
    encoded = urllib.parse.quote_plus(query)
    return f"https://www.youtube.com/results?search_query={encoded}"


def get_first_youtube_video_url(query: str) -> str | None:
    """Fetch the first YouTube video URL for a search query."""
    url = _youtube_search_url(query)
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        html = response.text
    except Exception:
        return None

    match = re.search(r'"videoId":"([^"]+)"', html)
    if not match:
        return None

    video_id = match.group(1)
    return f"https://www.youtube.com/watch?v={video_id}&autoplay=1"


def extract_youtube_query(text: str) -> str:
    """Extract the search terms for YouTube from a user input."""
    lower = text.lower()
    match = re.search(r"play (?:the )?(.+?) on youtube", lower)
    if match:
        return match.group(1).strip()

    match = re.search(r"youtube (?:search|for) (.+)", lower)
    if match:
        return match.group(1).strip()

    return text.strip()


def play_youtube(query: str) -> bool:
    """Open the first YouTube video result for a query."""
    if not query:
        return False

    video_url = get_first_youtube_video_url(query)
    driver = _init_driver()
    if driver:
        if not open_url(_youtube_search_url(query)):
            return False
        try:
            results = driver.find_elements(By.CSS_SELECTOR, "ytd-video-renderer,ytd-grid-video-renderer")
            if results:
                results[0].click()
                return True
            return open_url(video_url) if video_url else False
        except Exception:
            return open_url(video_url) if video_url else False

    if video_url:
        return open_chrome(video_url)

    return open_chrome(_youtube_search_url(query))


def click_element(selector: str, by: str = "css") -> bool:
    driver = _init_driver()
    if not driver:
        return False

    try:
        element = driver.find_element(By.CSS_SELECTOR if by == "css" else By.XPATH, selector)
        element.click()
        return True
    except Exception:
        return False


def fill_input(selector: str, text: str, by: str = "css") -> bool:
    driver = _init_driver()
    if not driver:
        return False

    try:
        element = driver.find_element(By.CSS_SELECTOR if by == "css" else By.XPATH, selector)
        element.clear()
        element.send_keys(text)
        element.send_keys(Keys.RETURN)
        return True
    except Exception:
        return False
