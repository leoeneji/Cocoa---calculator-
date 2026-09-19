import re
from datetime import datetime

import httpx
from bs4 import BeautifulSoup
from psycopg import connect

from backend.database.config import settings


CRIN_URL = "https://crin.gov.ng/news/"


def fetch_crin_page():
    response = httpx.get(
        CRIN_URL,
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    response.encoding = "utf-8"
    response.raise_for_status()

    return response.text


def parse_crin_news(html):
    soup = BeautifulSoup(html, "html.parser")

    articles = []

    for heading in soup.find_all("h3"):
        link = heading.find("a")

        if not link:
            continue

        title = link.get_text(" ", strip=True)
        url = link.get("href")

        if not title or not url:
            continue

        if not url.startswith("http"):
            continue

        parent = heading.parent

        if not parent:
            continue

        text = parent.get_text(" ", strip=True)

        date_match = re.search(
            r"(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},\s+\d{4}",
            text,
        )

        published_at = None

        if date_match:
            published_at = datetime.strptime(
                date_match.group(0),
                "%B %d, %Y",
            )

        articles.append(
            {
                "title": title,
                "url": url,
                "published_at": published_at,
            }
        )

    return articles


def save_crin_articles(articles):
    conn = connect(settings.database_url)

    try:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT id
                FROM sources
                WHERE name = 'Nigeria CRIN'
                LIMIT 1
            """)

            source = cur.fetchone()

            if not source:
                raise RuntimeError(
                    "Nigeria CRIN source not found in database."
                )

            source_id = source[0]

            cur.execute("""
                SELECT id
                FROM countries
                WHERE code = 'NGA'
                LIMIT 1
            """)

            country = cur.fetchone()

            if not country:
                raise RuntimeError(
                    "Nigeria country record not found in database."
                )

            country_id = country[0]

            saved = 0

            for article in articles:

                cur.execute(
                    """
                    INSERT INTO articles (
                        source_id,
                        country_id,
                        title,
                        url,
                        published_at
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
                    """,
                    (
                        source_id,
                        country_id,
                        article["title"],
                        article["url"],
                        article["published_at"],
                    ),
                )

                if cur.rowcount:
                    saved += 1

        conn.commit()

        return saved

    finally:
        conn.close()


if __name__ == "__main__":

    html = fetch_crin_page()

    articles = parse_crin_news(html)

    print("CRIN CONNECTION: OK")
    print(f"NEWS ARTICLES FOUND: {len(articles)}")

    saved = save_crin_articles(articles)

    print(f"ARTICLES SAVED TO DATABASE: {saved}")