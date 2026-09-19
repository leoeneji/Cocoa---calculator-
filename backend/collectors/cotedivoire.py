import subprocess
from bs4 import BeautifulSoup
from email.utils import parsedate_to_datetime
from psycopg import connect

from backend.database.config import settings


COTE_DIVOIRE_RSS_URL = (
    "https://conseilcafecacao.ci/index.php"
    "?format=feed"
    "&id=11%3Aactualit%C3%A9s"
    "&option=com_k2"
    "&task=category"
    "&view=itemlist"
)


def fetch_cotedivoire_feed():
 result = subprocess.run([
 "curl",
 "-k",
 "-L",
 COTE_DIVOIRE_RSS_URL,
 ], capture_output=True, check=True)

 return result.stdout.decode("utf-8", errors="replace")


def parse_cotedivoire_news(xml):
    soup = BeautifulSoup(xml, "xml")

    articles = []

    for item in soup.find_all("item"):

        title_tag = item.find("title")
        link_tag = item.find("link")
        date_tag = item.find("pubDate")
        description_tag = item.find("description")

        if not title_tag or not link_tag:
            continue

        title = title_tag.get_text(" ", strip=True)
        url = link_tag.get_text(" ", strip=True)

        if not title or not url:
            continue

        published_at = None

        if date_tag:
            try:
                published_at = parsedate_to_datetime(
                    date_tag.get_text(strip=True)
                )
            except (TypeError, ValueError):
                published_at = None

        content = None

        if description_tag:
            content = description_tag.get_text(
                " ",
                strip=True
            )

        articles.append(
            {
                "title": title,
                "url": url,
                "published_at": published_at,
                "content": content,
            }
        )

    return articles


def save_cotedivoire_articles(articles):
    conn = connect(settings.database_url)

    try:
        with conn.cursor() as cur:

            cur.execute("""
                SELECT id
                FROM sources
                WHERE name = 'Côte d’Ivoire Conseil Café-Cacao'
                LIMIT 1
            """)

            source = cur.fetchone()

            if not source:
                raise RuntimeError(
                    "Côte d’Ivoire source not found in database."
                )

            source_id = source[0]

            cur.execute("""
                SELECT id
                FROM countries
                WHERE code = 'CIV'
                LIMIT 1
            """)

            country = cur.fetchone()

            if not country:
                raise RuntimeError(
                    "Côte d’Ivoire country record not found in database."
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
                        published_at,
                        content
                    )
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (url) DO NOTHING
                    """,
                    (
                        source_id,
                        country_id,
                        article["title"],
                        article["url"],
                        article["published_at"],
                        article["content"],
                    ),
                )

                if cur.rowcount:
                    saved += 1

        conn.commit()

        return saved

    finally:
        conn.close()


if __name__ == "__main__":

    xml = fetch_cotedivoire_feed()

    articles = parse_cotedivoire_news(xml)

    print("CÔTE D'IVOIRE CONNECTION: OK")
    print(f"NEWS ARTICLES FOUND: {len(articles)}")

    saved = save_cotedivoire_articles(articles)

    print(f"ARTICLES SAVED TO DATABASE: {saved}")
