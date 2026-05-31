import json
import urllib.request
import urllib.parse
import re
from typing import List, Dict, Any

class WebSearch:
    """
    Web search tool using DuckDuckGo's lite HTML interface.
    No API key required. Rate-limited but functional.
    """

    def __init__(self):
        self._user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DeepGravity/0.2"
        self._search_url = "https://lite.duckduckgo.com/lite/"

    def search(self, query: str, max_results: int = 8) -> Dict[str, Any]:
        """
        Search the web via DuckDuckGo lite interface.
        
        Args:
            query: The search query string.
            max_results: Maximum number of results to return (1-15).
        
        Returns:
            Dict with:
              - "results": List of {title, snippet, url}
              - "total": Number of results returned
              - "error": Error message if something went wrong
        """
        max_results = max(1, min(15, max_results))

        try:
            data = urllib.parse.urlencode({"q": query}).encode()
            req = urllib.request.Request(
                self._search_url,
                data=data,
                headers={"User-Agent": self._user_agent}
            )
            
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")

        except Exception as e:
            return {
                "results": [],
                "total": 0,
                "error": f"Search request failed: {e}"
            }

        # Parse the HTML response for result links and snippets
        results = []
        # DuckDuckGo lite returns results in a specific table structure
        # We extract from the raw HTML using simple pattern matching
        
        # Find result rows: <a href="...">title</a> with preceding <td>s
        link_pattern = re.compile(
            r'<a[^>]*href="(https?://[^"]+)"[^>]*>(.*?)</a>',
            re.IGNORECASE | re.DOTALL
        )
        snippet_pattern = re.compile(
            r'<td[^>]*class="result-snippet"[^>]*>(.*?)</td>',
            re.IGNORECASE | re.DOTALL
        )

        links = link_pattern.findall(html)
        snippets = snippet_pattern.findall(html)

        # Clean up HTML entities in snippets
        def clean_html(text: str) -> str:
            text = re.sub(r'<[^>]+>', '', text)
            text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')
            text = text.replace('&quot;', '"').replace('&#x27;', "'").replace('&#39;', "'")
            return text.strip()

        # Results are interleaved: link, then snippet, link, snippet...
        result_count = min(len(links), max_results)
        for i in range(result_count):
            url, title = links[i]
            snippet = clean_html(snippets[i]) if i < len(snippets) else ""
            title = clean_html(title)
            
            results.append({
                "title": title or "(no title)",
                "snippet": snippet,
                "url": url
            })

        return {
            "results": results,
            "total": len(results),
            "error": None
        }
