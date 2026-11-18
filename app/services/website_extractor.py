"""Website content extraction and cleaning service.

Fetches a website's HTML, parses it with BeautifulSoup, and extracts
clean, structured content suitable for LLM analysis.
"""

import re
from dataclasses import dataclass, field
from typing import Optional

import httpx
from bs4 import BeautifulSoup, Comment

from app.config import settings


@dataclass
class WebsiteContent:
    """Structured content extracted from a website."""

    url: str
    title: str = ""
    meta_description: str = ""
    headings: list[str] = field(default_factory=list)
    body_text: str = ""
    links: list[str] = field(default_factory=list)
    extraction_success: bool = True
    error: Optional[str] = None


# Tags to remove entirely (scripts, styles, non-visible elements)
REMOVE_TAGS = [
    "script", "style", "noscript", "iframe", "svg",
    "form", "input", "button", "select", "textarea",
    "canvas", "video", "audio", "source", "picture",
    "object", "embed", "applet",
]

# Tags that typically contain navigational/boilerplate content
NOISE_TAGS = ["nav", "footer"]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


async def fetch_website(url: str) -> str:
    """Fetch website HTML content asynchronously.

    Args:
        url: The website URL to fetch.

    Returns:
        Raw HTML string of the website.

    Raises:
        httpx.TimeoutException: If the request times out.
        httpx.HTTPStatusError: If the server returns an error status.
    """
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(settings.request_timeout),
        verify=True,
    ) as client:
        response = await client.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
            },
        )
        response.raise_for_status()
        return response.text


def clean_text(text: str) -> str:
    """Clean and normalize extracted text content."""
    # Collapse all whitespace into single spaces
    text = re.sub(r"[\t\r]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r" {2,}", " ", text)
    # Remove very short lines (likely noise)
    lines = [line.strip() for line in text.split("\n")]
    lines = [line for line in lines if len(line) > 2]
    return "\n".join(lines).strip()


def extract_content(html: str, url: str) -> WebsiteContent:
    """Extract and clean meaningful content from raw HTML.

    Args:
        html: Raw HTML string.
        url: Original website URL.

    Returns:
        WebsiteContent with extracted fields.
    """
    content = WebsiteContent(url=url)

    try:
        soup = BeautifulSoup(html, "lxml")

        # --- Title ---
        title_tag = soup.find("title")
        content.title = title_tag.get_text(strip=True) if title_tag else ""

        # --- Meta description ---
        meta_desc = soup.find("meta", attrs={"name": re.compile(r"description", re.I)})
        if meta_desc and meta_desc.get("content"):
            content.meta_description = meta_desc["content"].strip()

        # --- OG description fallback ---
        if not content.meta_description:
            og_desc = soup.find("meta", attrs={"property": "og:description"})
            if og_desc and og_desc.get("content"):
                content.meta_description = og_desc["content"].strip()

        # --- Remove unwanted elements ---
        for tag_name in REMOVE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # Remove HTML comments
        for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
            comment.extract()

        # --- Extract headings (h1-h3) ---
        for level in range(1, 4):
            for heading in soup.find_all(f"h{level}"):
                text = heading.get_text(strip=True)
                if text and len(text) > 2:
                    content.headings.append(f"H{level}: {text}")

        # --- Remove noise elements before extracting body text ---
        for tag_name in NOISE_TAGS:
            for tag in soup.find_all(tag_name):
                tag.decompose()

        # --- Extract body text ---
        body = soup.find("body")
        if body:
            text_elements = body.find_all(
                ["p", "li", "td", "th", "article", "section", "blockquote", "figcaption"]
            )

            text_parts = []
            seen = set()

            for element in text_elements:
                text = element.get_text(strip=True)
                if text and len(text) > 15:
                    # Deduplicate by normalized content
                    normalized = text.lower().strip()[:100]
                    if normalized not in seen:
                        seen.add(normalized)
                        text_parts.append(text)

            content.body_text = clean_text(" ".join(text_parts))

        # --- Extract link texts for additional context ---
        seen_links = set()
        for a_tag in soup.find_all("a", href=True):
            link_text = a_tag.get_text(strip=True)
            if link_text and len(link_text) > 3 and link_text.lower() not in seen_links:
                seen_links.add(link_text.lower())
                content.links.append(link_text)

        # --- Truncate to configured max length ---
        if len(content.body_text) > settings.max_content_length:
            content.body_text = content.body_text[: settings.max_content_length] + "..."

        # Limit headings and links to avoid token bloat
        content.headings = content.headings[:30]
        content.links = content.links[:25]

    except Exception as e:
        content.extraction_success = False
        content.error = f"Content extraction failed: {str(e)}"

    return content


async def extract_website_content(url: str) -> WebsiteContent:
    """Full pipeline: fetch website HTML and extract structured content.

    Args:
        url: The website URL to extract content from.

    Returns:
        WebsiteContent with extraction results (check extraction_success).
    """
    try:
        html = await fetch_website(url)
        return extract_content(html, url)
    except httpx.TimeoutException:
        return WebsiteContent(
            url=url,
            extraction_success=False,
            error="Website request timed out. The website may be slow or unreachable.",
        )
    except httpx.HTTPStatusError as e:
        return WebsiteContent(
            url=url,
            extraction_success=False,
            error=f"Website returned HTTP error {e.response.status_code}",
        )
    except httpx.ConnectError:
        return WebsiteContent(
            url=url,
            extraction_success=False,
            error="Could not connect to the website. It may be down or blocking requests.",
        )
    except Exception as e:
        return WebsiteContent(
            url=url,
            extraction_success=False,
            error=f"Failed to fetch website: {str(e)}",
        )
