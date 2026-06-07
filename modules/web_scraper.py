"""Internet scraping helpers for Arrow."""

import re
import requests
import urllib.parse
import xml.etree.ElementTree as ET

HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; Arrow/1.0; +https://example.com)"
}


def get_weather(location: str = "Kolkata") -> str:
    """Fetch weather information for a location using wttr.in."""
    location = location.strip() or "Kolkata"
    encoded = urllib.parse.quote(location)
    url = f"https://wttr.in/{encoded}?format=j1"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return f"I could not fetch weather data right now. {exc}"

    current = data.get("current_condition")
    if not current:
        return "Weather data is unavailable for that location."

    current = current[0]
    temp_c = current.get("temp_C")
    desc = current.get("weatherDesc", [{}])[0].get("value", "")
    feels_like = current.get("FeelsLikeC")
    humidity = current.get("humidity")

    return (
        f"The weather in {location} is {desc} with a temperature of {temp_c} degrees Celsius. "
        f"It feels like {feels_like} degrees and humidity is {humidity} percent."
    )


def get_top_news_headlines(count: int = 5) -> str:
    """Fetch top tech news headlines from Google News RSS."""
    url = "https://news.google.com/rss/headlines/section/topic/TECHNOLOGY?hl=en-US&gl=US&ceid=US:en"

    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        root = ET.fromstring(response.content)
    except Exception as exc:
        return f"I could not fetch news headlines right now. {exc}"

    items = root.findall(".//item")
    if not items:
        return "No tech news headlines were found."

    headlines = []
    for item in items[:count]:
        title = item.findtext("title")
        if title:
            headlines.append(title.strip())

    if not headlines:
        return "No news headlines were found."

    return "Top news headlines are: " + ", ".join(headlines)


def get_wikipedia_summary(query: str) -> str:
    """Fetch a short Wikipedia summary for a topic."""
    query = query.strip() or "Wikipedia"
    encoded = urllib.parse.quote(query)
    summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{encoded}"

    try:
        response = requests.get(summary_url, headers=HEADERS, timeout=15)
        if response.status_code == 404:
            return _search_wikipedia(query)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        return f"I could not fetch Wikipedia information right now. {exc}"

    extract = data.get("extract")
    if not extract:
        return "I could not find a summary for that topic on Wikipedia."

    return extract


def _search_wikipedia(query: str) -> str:
    search_url = (
        "https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch="
        f"{urllib.parse.quote(query)}&format=json&utf8=1"
    )
    try:
        response = requests.get(search_url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        data = response.json()
        results = data.get("query", {}).get("search", [])
    except Exception as exc:
        return f"I could not search Wikipedia right now. {exc}"

    if not results:
        return "I could not find anything on Wikipedia for that topic."

    title = results[0].get("title")
    if not title:
        return "I could not find anything on Wikipedia for that topic."

    return get_wikipedia_summary(title)


def extract_weather_location(text: str) -> str:
    """Extract the location from a weather query."""
    text = text.lower()
    match = re.search(r"weather(?: in| for)? ([\w\s]+)", text)
    if match:
        return match.group(1).strip()

    match = re.search(r"in ([\w\s]+) weather", text)
    if match:
        return match.group(1).strip()

    return "Kolkata"


def extract_wikipedia_query(text: str) -> str:
    """Extract the Wikipedia query from a request."""
    text = text.lower()
    patterns = [
        r"wikipedia(?: summary)?(?: for)? (.+)",
        r"who is (.+)",
        r"what is (.+)",
        r"define (.+)",
        r"tell me about (.+)",
        r"search wikipedia for (.+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip().rstrip("?.")

    return text.strip().rstrip("?.")
