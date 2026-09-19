import hashlib
import re
from datetime import datetime, timezone

import httpx
from bs4 import BeautifulSoup

from backend.database.connection import get_connection


COCOBOD_BASE_URL = "https://cocobod.gh"
COCOBOD_NEWS_URL = f"{COCOBOD_BASE_URL}/news"


def fetch_page(url):
    response = httpx.get(
        url,
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )
    response.encoding = "utf-8"
    response.raise_for_status()
    return response.text


def get_news_links(html):
    soup = BeautifulSoup(html, "html.parser")

    links = []

    for a in soup.find_all("a", href=True):
        href = a["href"]

        if href.startswith("/news/"):
            url = COCOBOD_BASE_URL + href

            if url not in links:
                links.append(url)

    return links


def parse_article(url):
    html = fetch_page(url)
    soup = BeautifulSoup(html, "html.parser")

    h1 = soup.find("h1")

    if not h1:
        return None

    title = h1.get_text(" ", strip=True)

    published_at = None

    for tag in soup.find_all(["h5", "h6", "p", "div"]):
        text = tag.get_text(" ", strip=True)

        if "Date:" in text:
            match = re.search(
                r"Date:\s*(\d{1,2})(?:st|nd|rd|th)?\s+"
                r"([A-Za-z]+)\s+(\d{4})",
                text,
                re.IGNORECASE,
            )

            if match:
                day = int(match.group(1))
                month = match.group(2)
                year = int(match.group(3))

                try:
                    published_at = datetime.strptime(
                        f"{day} {month} {year}",
                        "%d %B %Y",
                    ).replace(tzinfo=timezone.utc)

                except ValueError:
                    published_at = None

                break

    paragraphs = []

    for p in soup.find_all("p"):
        text = p.get_text(" ", strip=True)

        if text and text not in paragraphs:
            paragraphs.append(text)

    content = "\n\n".join(paragraphs)

    content_hash = hashlib.sha256(
        content.encode("utf-8")
    ).hexdigest()

    return {
        "title": title,
        "url": url,
        "published_at": published_at,
        "content": content,
        "content_hash": content_hash,
    }


def save_articles(articles):
    conn = get_connection()

    try:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT id
                FROM sources
                WHERE name = 'Ghana COCOBOD'
                LIMIT 1
            """)

            source_row = cur.fetchone()

            if not source_row:
                raise RuntimeError(
                    "Ghana COCOBOD source was not found in the database."
                )

            source_id = source_row[0]

            cur.execute("""
                SELECT id
                FROM countries
                WHERE code = 'GHA'
                LIMIT 1
            """)

            country_row = cur.fetchone()

            if not country_row:
                raise RuntimeError(
                    "Ghana country was not found in the database."
                )

            country_id = country_row[0]

            saved = 0

            for article in articles:

                cur.execute("""
                    INSERT INTO articles (
                        source_id,
                        country_id,
                        title,
                        url,
                        published_at,
                        content,
                        content_hash
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s
                    )
                    ON CONFLICT (url) DO NOTHING
                """, (
                    source_id,
                    country_id,
                    article["title"],
                    article["url"],
                    article["published_at"],
                    article["content"],
                    article["content_hash"],
                ))

                if cur.rowcount == 1:
                    saved += 1

        conn.commit()

        return saved

    finally:
        conn.close()


def collect_cocobod_news():
    print("COCOBOD CONNECTION: OK")

    html = fetch_page(COCOBOD_NEWS_URL)

    links = get_news_links(html)

    print(f"NEWS LINKS FOUND: {len(links)}")

    articles = []

    for url in links[:10]:
        try:
            article = parse_article(url)

            if article:
                articles.append(article)

        except Exception as error:
            print(f"ERROR: {url}")
            print(error)

    return articles


if __name__ == "__main__":

    articles = collect_cocobod_news()

    print()
    print(f"ARTICLES PARSED: {len(articles)}")

    saved = save_articles(articles)

    print(f"ARTICLES SAVED TO DATABASE: {saved}")