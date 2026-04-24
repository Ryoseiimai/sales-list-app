"""
スクレイピングエンジン
- 会社名+URLのリストを受け取り、メアド/問い合わせフォーム/特商法ページから情報取得
- User-Agent 3種ローテ、SSL verify False、タイムアウト20秒
- sample@等のノイズメアド除外
"""
import re
import time
import sys
from urllib.parse import urljoin, urlparse
from typing import Callable
import requests
from bs4 import BeautifulSoup
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0",
]

BASE_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")
EXCLUDE_PATTERNS = [
    re.compile(r"\.(png|jpg|jpeg|gif|svg|webp|ico|css|js|woff|woff2|ttf)$", re.IGNORECASE),
    re.compile(r"@(sentry|wixpress|example|test|your-domain|domain|sample)\."),
    re.compile(r"(noreply|no-reply|donotreply|bounce)@", re.IGNORECASE),
    re.compile(r"\bsample@", re.I),
    re.compile(r"@mail\.(com|jp)\b", re.I),
    re.compile(r"@co\.jp$", re.I),
    re.compile(r"^taro[_.-]", re.I),
    re.compile(r"^yamada[_.-]", re.I),
    re.compile(r"^test[_.-]", re.I),
]

CONTACT_KEYWORDS = ["contact", "inquiry", "toiawase", "問い合わせ", "問合せ", "お問合", "お問い合"]
DEEP_KEYWORDS = ["privacy", "policy", "tokushoho", "特商法", "特定商取引", "運営会社", "会社概要", "company", "about", "ir"]


def is_valid_email(email: str) -> bool:
    for pat in EXCLUDE_PATTERNS:
        if pat.search(email):
            return False
    if len(email) > 80 or "example" in email.lower():
        return False
    return True


def get_domain(url: str) -> str:
    host = urlparse(url).netloc.lower().replace("www.", "")
    parts = host.split(".")
    return ".".join(parts[-2:]) if len(parts) >= 2 else host


def fetch(url: str, ua_idx: int = 0, timeout: int = 20) -> tuple[str, str] | None:
    headers = {**BASE_HEADERS, "User-Agent": USER_AGENTS[ua_idx % len(USER_AGENTS)]}
    try:
        r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True, verify=False)
        r.raise_for_status()
        if r.encoding is None or r.encoding.lower() == "iso-8859-1":
            r.encoding = r.apparent_encoding
        return r.text, r.url
    except Exception as e:
        print(f"  ! fetch error {url}: {str(e)[:100]}", file=sys.stderr)
        return None


def find_emails(html: str, domain: str) -> list[str]:
    candidates = set(EMAIL_RE.findall(html))
    valid = [e for e in candidates if is_valid_email(e)]
    same = [e for e in valid if domain in e.lower()]
    other = [e for e in valid if domain not in e.lower()]
    return same + other


def find_pages(html: str, base_url: str, keywords: list[str], limit: int = 3) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    seen = set()
    for a in soup.find_all("a", href=True):
        combined = (a["href"] + " " + (a.get_text() or "")).lower()
        if any(kw.lower() in combined for kw in keywords):
            full = urljoin(base_url, a["href"])
            if full.startswith("http") and full not in seen:
                seen.add(full)
                urls.append(full)
    return urls[:limit]


def process_one(name: str, url: str, category: str = "") -> dict:
    """1社分を処理"""
    result = {
        "会社名": name,
        "公式サイトURL": url,
        "メアド": "",
        "問い合わせフォームURL": "",
        "業種": category,
        "備考": "",
    }

    # User-Agent3種でリトライ
    fetched = None
    for ua in range(3):
        fetched = fetch(url, ua)
        if fetched:
            break
        time.sleep(0.8)

    if not fetched:
        result["備考"] = "トップページ取得失敗"
        return result

    html, final_url = fetched
    domain = get_domain(final_url)
    emails = list(find_emails(html, domain))

    # お問い合わせページ探索
    contact_urls = find_pages(html, final_url, CONTACT_KEYWORDS, limit=2)
    if contact_urls:
        result["問い合わせフォームURL"] = contact_urls[0]
        time.sleep(0.8)
        f2 = fetch(contact_urls[0])
        if f2:
            for e in find_emails(f2[0], domain):
                if e not in emails:
                    emails.append(e)

    # メアド見つからなければ特商法/運営会社ページも探す
    if not emails:
        deep_urls = find_pages(html, final_url, DEEP_KEYWORDS, limit=2)
        for du in deep_urls[:2]:
            time.sleep(0.8)
            f3 = fetch(du)
            if f3:
                for e in find_emails(f3[0], domain):
                    if e not in emails:
                        emails.append(e)
            if emails:
                break

    if emails:
        result["メアド"] = "; ".join(emails[:3])
    elif not result["問い合わせフォームURL"]:
        result["備考"] = "コンタクト手段見つからず"
    else:
        result["備考"] = "メアド見つからず（フォームのみ）"

    return result


def process_batch(
    companies: list[dict],
    progress_callback: Callable[[int, int, str, dict], None] | None = None,
    delay_sec: float = 2.0,
) -> list[dict]:
    """バッチ処理。companies=[{name,url,category?},...]"""
    results = []
    total = len(companies)
    for i, c in enumerate(companies, 1):
        name = c.get("name", c.get("会社名", "")).strip()
        url = c.get("url", c.get("公式サイトURL", "")).strip()
        cat = c.get("category", c.get("業種", "")).strip()
        if not name or not url:
            continue
        if not url.startswith("http"):
            url = "https://" + url
        try:
            r = process_one(name, url, cat)
        except Exception as e:
            r = {
                "会社名": name, "公式サイトURL": url, "メアド": "",
                "問い合わせフォームURL": "", "業種": cat, "備考": f"例外: {str(e)[:80]}",
            }
        results.append(r)
        if progress_callback:
            progress_callback(i, total, name, r)
        if i < total:
            time.sleep(delay_sec)
    return results
