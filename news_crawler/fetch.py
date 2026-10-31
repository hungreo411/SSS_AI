"""HTTP: session có retry, cache đĩa, giới hạn đồng thời + độ trễ lịch sự theo từng domain."""
import hashlib
import os
import threading
import time
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/130.0 Safari/537.36")


class Fetcher:
    def __init__(self, cache_dir=".cache", per_host=2, delay=0.4, timeout=20, listing_ttl=900, verbose=False):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.per_host = per_host
        self.delay = delay
        self.timeout = timeout
        self.listing_ttl = listing_ttl
        self.verbose = verbose
        self._local = threading.local()
        self._host_sem = {}
        self._host_last = {}
        self._lock = threading.Lock()
        self.stats = {"ok": 0, "fail": 0, "cache": 0}
        self.errors = {}  # host -> lỗi gần nhất

    def _session(self):
        s = getattr(self._local, "s", None)
        if s is None:
            s = requests.Session()
            retry = Retry(total=2, backoff_factor=0.8, status_forcelist=(429, 500, 502, 503, 504),
                          allowed_methods=("GET",), raise_on_status=False)
            s.mount("http://", HTTPAdapter(max_retries=retry, pool_maxsize=8))
            s.mount("https://", HTTPAdapter(max_retries=retry, pool_maxsize=8))
            s.headers.update({"User-Agent": UA, "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
                              "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"})
            self._local.s = s
        return s

    def _cache_path(self, url):
        return os.path.join(self.cache_dir, hashlib.sha1(url.encode()).hexdigest() + ".html")

    def get(self, url, ttl=None):
        """Trả về text (str) hoặc None. ttl=None: cache vĩnh viễn (bài viết); ttl=giây: trang danh mục/RSS."""
        path = self._cache_path(url)
        if os.path.exists(path):
            age = time.time() - os.path.getmtime(path)
            if ttl is None or age < ttl:
                with self._lock:
                    self.stats["cache"] += 1
                with open(path, encoding="utf-8", errors="replace") as f:
                    return f.read()
        host = urlparse(url).netloc
        with self._lock:
            sem = self._host_sem.setdefault(host, threading.Semaphore(self.per_host))
        with sem:
            with self._lock:
                wait = self._host_last.get(host, 0) + self.delay - time.time()
                self._host_last[host] = max(time.time(), self._host_last.get(host, 0) + self.delay)
            if wait > 0:
                time.sleep(wait)
            try:
                r = self._session().get(url, timeout=self.timeout, allow_redirects=True)
            except requests.RequestException as e:
                return self._fail(host, url, type(e).__name__)
        if r.status_code != 200:
            return self._fail(host, url, f"HTTP {r.status_code}")
        if not r.encoding or r.encoding.lower() == "iso-8859-1":
            r.encoding = "utf-8" if b"utf-8" in r.content[:2000].lower() else r.apparent_encoding
        text = r.text
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        with self._lock:
            self.stats["ok"] += 1
        return text

    def _fail(self, host, url, why):
        with self._lock:
            self.stats["fail"] += 1
            self.errors[host] = why
        if self.verbose:
            print(f"  ! {why}: {url}")
        return None
