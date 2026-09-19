import httpx
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from psycopg import connect

from backend.database.config import settings


ONCC_URL = "https://www.oncc.cm/updates"


def fetch_oncc_page():
    response = httpx.get(
        ONCC_URL,
        timeout=30,
        follow_redirects=True,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
        verify=False,
    )

    response.encoding = "utf-8"
    response.raise_for_status()

    return response.text


def parse_oncc_news(html):
    soup = BeautifulSoup(html, "html.parser")

    articles = []

    for heading in soup.find_all("h5"):

        title = heading.get_text(" ", strip=True)

        if not title:
            continue

        link = heading.find_next("a")

        if not link:
            continue

        href = link.get("href")

        if not href:
            continue

        url = urljoin(ONCC_URL, href)

        articles.append(
            {
                "title": title,
                "url": url,
            }
        )

    return articles


def save_oncc_articles(articles):
    conn = connect(settings.database_url)

    try:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT id
                FROM sources
                WHERE name = 'Cameroon ONCC'
                LIMIT 1
            """)

            source = cur.fetchone()

            if not source:
                raise RuntimeError(
                    "Cameroon ONCC source not found in database."
                )

            source_id = source[0]

            cur.execute("""
                SELECT id
                FROM countries
                WHERE code = 'CMR'
                LIMIT 1
            """)

            country = cur.fetchone()

            if not country:
                raise RuntimeError(
                    "Cameroon country record not found in database."
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
                        url
                    )
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
                    """,
                    (
                        source_id,
                        country_id,
                        article["title"],
                        article["url"],
                    ),
                )

                if cur.rowcount:
                    saved += 1

        conn.commit()

        return saved

    finally:
        conn.close()


if __name__ == "__main__":

    html = fetch_oncc_page()

    articles = parse_oncc_news(html)

    print("CAMEROON ONCC CONNECTION: OK")
    print(f"NEWS ARTICLES FOUND: {len(articles)}")

    saved = save_oncc_articles(articles)

    print(f"ARTICLES SAVED TO DATABASE: {saved}")