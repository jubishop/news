"""Browser page reader for reporters: a stdio MCP server with one fetch_page tool.

Claude Code's WebFetch is turned away by bot blocks and cookie walls, does not
follow redirects to other hosts, and cannot read PDFs. This server loads pages
in Playwright's Chromium with an ordinary desktop user agent and reads PDFs
with macOS PDFKit. Every browser connection passes through a local proxy that
reaches only public internet addresses, so pages, redirects, and DNS answers
cannot steer the browser into the owner's machine or network.
"""

import asyncio
import ipaddress
import json
import re
import socket
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


# Claude Code rejects MCP results over the worker's 5,000-token budget. Link
# lists run near two characters a token and non-Latin text near one, so a
# section holds 7,500 characters and other scripts count three each.
SECTION = 7_500
# Images come first so reporters see them, but may fill only half of the first section, leaving the rest for text.
IMAGES = SECTION // 2
PAGES = 4
NAVIGATION_MS = 30_000
CALL_SECONDS = 120
PDF_LIMIT = 50 * 1024 * 1024
CHALLENGE = re.compile(r"just a moment|attention required|checking your browser|are you a robot|verify you are human", re.I)
TEXT_TYPES = ("text/plain", "application/json", "text/xml", "application/xml", "text/csv")
TOOL = {
    "name": "fetch_page",
    "description": "Load a web page or PDF in a browser and return its text, images, and links. "
                   "Follows redirects and waits out bot checks. Long results continue from start.",
    "inputSchema": {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "An http or https URL."},
            "start": {"type": "integer", "minimum": 0, "description": "Character offset that continues a long result."},
        },
        "required": ["url"],
        "additionalProperties": False,
    },
}
EXTRACT = """() => {
  const skip = 'nav,footer,aside,dialog,[role=navigation],[role=contentinfo],[role=dialog],[aria-modal=true]';
  const hide = document.createElement('style');
  hide.textContent = skip + '{display:none!important}';
  document.documentElement.append(hide);
  const main = document.querySelector('main,[role=main]');
  const root = main && main.innerText.trim().length >= 500 ? main : document.body || document.documentElement;
  const text = root.innerText;
  hide.remove();
  const absolute = value => { try { return new URL(value, location.href).href; } catch { return ''; } };
  const seen = new Set(), images = [], links = [];
  const image = (src, alt, caption) => {
    if (!src.startsWith('https://') || /\\.svg(\\?|#|$)/i.test(src) || seen.has(src) || images.length >= 12) return;
    seen.add(src);
    images.push({src, alt: (alt || '').trim().slice(0, 200), caption: (caption || '').replace(/\\s+/g, ' ').trim().slice(0, 200)});
  };
  const og = document.querySelector('meta[property="og:image"]');
  if (og) image(absolute(og.content), document.querySelector('meta[property="og:image:alt"]')?.content, '');
  for (const img of root.querySelectorAll('img')) {
    if (img.closest(skip)) continue;
    const lazy = img.dataset.src || img.dataset.lazySrc || (img.srcset || '').split(/\\s+/)[0];
    const current = img.currentSrc || img.src;
    // Skip images the page does not show, such as hidden ad and tracking pixels. A lazy image keeps a
    // zero-size box until its source loads; lazy loaders never load one under display: none.
    const box = img.getBoundingClientRect();
    const pending = (!current || current.startsWith('data:')) && lazy || !img.complete;
    if (!img.getClientRects().length || (!box.width || !box.height) && !pending) continue;
    // A failed image renders as a small alt-text box; judge size by the file or its declared size, such as 0px.
    // A percentage or another unit says nothing about the file.
    const declared = name => Number(/^\\s*(\\d*\\.?\\d+)(px)?\\s*$/i.exec(img.getAttribute(name) || '')?.[1] ?? NaN);
    const width = img.naturalWidth || declared('width'), height = img.naturalHeight || declared('height');
    if (width < 150 || height < 100) continue;
    image(absolute(current && !current.startsWith('data:') ? current : lazy), img.alt,
          img.closest('figure')?.querySelector('figcaption')?.innerText);
  }
  for (const a of root.querySelectorAll('a[href]')) {
    if (a.closest(skip)) continue;
    const label = a.innerText.replace(/\\s+/g, ' ').trim(), href = absolute(a.getAttribute('href'));
    if (label.length < 20 || !/^https?:/.test(href) || seen.has(href) || links.length >= 40) continue;
    seen.add(href);
    links.push({label: label.slice(0, 150), href});
  }
  return {title: document.title, text, images, links};
}"""
PDFKIT = """ObjC.import("PDFKit");
function run(argv) {
  const pdf = $.PDFDocument.alloc.initWithURL($.NSURL.fileURLWithPath(argv[0]));
  return pdf.isNil() ? "" : (ObjC.unwrap(pdf.string) || "");
}"""


class Refused(Exception):
    pass


def public(address):
    ip = ipaddress.ip_address(address.split("%", 1)[0])
    if ip.version == 6 and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


async def resolve(host, port):
    """Return one public address for host, or raise Refused or OSError."""
    infos = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = [info[4][0] for info in infos]
    # Any private answer refuses the host; a mixed answer may be a rebinding attempt.
    if not addresses or not all(public(address) for address in addresses):
        raise Refused(host)
    return addresses[0]


async def pipe(reader, writer):
    try:
        while data := await reader.read(65536):
            writer.write(data)
            await writer.drain()
    finally:
        writer.close()


class Proxy:
    """Forward Chromium's connections only to vetted public addresses."""

    async def start(self):
        self.server = await asyncio.start_server(self.handle, "127.0.0.1", 0)
        return self.server.sockets[0].getsockname()[1]

    async def handle(self, reader, writer):
        upstream = None
        try:
            head = await asyncio.wait_for(reader.readuntil(b"\r\n\r\n"), 30)
            line, _, rest = head.partition(b"\r\n")
            method, target, version = line.decode("latin-1").split(" ", 2)
            if method == "CONNECT":
                host, _, port = target.rpartition(":")
                host, port, request = host.strip("[]"), int(port), b""
            else:
                parts = urlsplit(target)
                if parts.scheme != "http" or not parts.hostname:
                    raise ValueError(target)
                host, port = parts.hostname, parts.port or 80
                path = (parts.path or "/") + ("?" + parts.query if parts.query else "")
                headers = [header for header in rest.split(b"\r\n") if header and not header.lower().startswith(
                    (b"proxy-connection:", b"connection:", b"keep-alive:"))]
                # One request per connection: a reused client connection could name another host.
                request = b"\r\n".join([f"{method} {path} {version}".encode("latin-1"), *headers, b"Connection: close", b"", b""])
            try:
                address = await resolve(host, port)
            except (Refused, OSError):
                writer.write(b"HTTP/1.1 403 Forbidden\r\nContent-Length: 0\r\nConnection: close\r\n\r\n")
                return
            # Connect to the vetted address itself so DNS cannot change between check and use.
            upstream_reader, upstream = await asyncio.wait_for(asyncio.open_connection(address, port), 20)
            if request:
                upstream.write(request)
            else:
                writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await asyncio.gather(pipe(reader, upstream), pipe(upstream_reader, writer), return_exceptions=True)
        except (OSError, ValueError, asyncio.IncompleteReadError, asyncio.LimitOverrunError, asyncio.TimeoutError):
            pass
        finally:
            for stream in (upstream, writer):
                if stream is not None:
                    stream.close()


def pdf_text(path):
    if sys.platform != "darwin":
        raise RuntimeError("Reading PDFs requires macOS PDFKit.")
    result = subprocess.run(["/usr/bin/osascript", "-l", "JavaScript", "-e", PDFKIT, str(path)],
                            capture_output=True, text=True, timeout=60)
    return result.stdout.strip() if result.returncode == 0 else ""


def tidy(text):
    text = re.sub(r"[ \t ]+\n", "\n", text.replace("\r\n", "\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def weight(text):
    return sum(3 if ord(character) > 0x2FF else 1 for character in text)


def document(url, status, title, text, images=(), links=()):
    lines = [f"URL: {url}", f"HTTP status: {status}"]
    if title:
        lines.append(f"Title: {title.strip()}")
    listed, room = [], IMAGES
    for i in images:
        line = f"- {i['src']} | alt: {i['alt'] or 'none'}" + (f" | caption: {i['caption']}" if i["caption"] else "")
        # Leave out an image that does not fit, such as one with a long tracking URL; a shorter one may still fit.
        if weight(line) < room:
            listed.append(line)
            room -= weight(line) + 1
    if listed:
        lines += ["Images:", *listed]
    result = "\n".join(lines) + "\n\n" + (tidy(text) or "The page has no readable text.")
    if links:
        result += "\n\nLinks:\n" + "\n".join(f"- {link['label']}: {link['href']}" for link in links)
    return result


def section(text, start):
    if start >= len(text) and start:
        return f"[The result has {len(text)} characters; start={start} is past its end.]"
    end, used = start, 0
    while end < len(text) and used < SECTION:
        used += weight(text[end])
        end += 1
    if end < len(text):
        # Prefer a line break or space so a continuation does not split a word.
        middle = (start + end) // 2
        end = max(text.rfind("\n", middle, end), text.rfind(" ", middle, end)) + 1 or end
    chunk = text[start:end]
    if start:
        chunk = f"[Characters {start}–{end} of {len(text)}.]\n" + chunk
    if end < len(text):
        chunk += f"\n\n[Characters {start}–{end} of {len(text)}. Call fetch_page with the same url and start={end} for more.]"
    return chunk


class Fetcher:
    async def __aenter__(self):
        from playwright.async_api import async_playwright

        port = await (proxy := Proxy()).start()
        self.server = proxy.server
        self.playwright = await async_playwright().start()
        self.browser = await self.playwright.chromium.launch(
            headless=True, proxy={"server": f"http://127.0.0.1:{port}"},
            args=["--disable-blink-features=AutomationControlled",
                  "--force-webrtc-ip-handling-policy=disable_non_proxied_udp"],
        )
        major = self.browser.version.split(".", 1)[0]
        # Many publishers turn away HeadlessChrome; present ordinary desktop Chrome.
        self.session = {
            "user_agent": f"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                          f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36",
            "locale": "en-US", "timezone_id": "America/Los_Angeles", "viewport": {"width": 1280, "height": 900},
            "accept_downloads": True,
        }
        self.slots = asyncio.Semaphore(PAGES)
        self.cache = {}
        return self

    async def __aexit__(self, *exc):
        try:
            await self.browser.close()
            await self.playwright.stop()
        finally:
            self.server.close()

    async def call(self, arguments):
        url, start = arguments.get("url"), arguments.get("start", 0)
        if not isinstance(url, str) or type(start) is not int or start < 0:
            return failure("fetch_page needs a url string and an optional nonnegative integer start.")
        try:
            parts = urlsplit(url.strip())
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError:
            return failure(f"{url} is not a valid URL.")
        if parts.scheme not in ("http", "https") or not parts.hostname:
            return failure("fetch_page reads only http and https URLs.")
        url = parts.geturl()
        text = self.cache.get(url)
        if text is None:
            try:
                await resolve(parts.hostname, port)
                async with self.slots:
                    status, text = await asyncio.wait_for(self.load(url), CALL_SECONDS)
            except Refused:
                return failure(f"Refused {url}: it is not a public internet address.")
            except OSError:
                return failure(f"{parts.hostname} could not be resolved.")
            except asyncio.TimeoutError:
                return failure(f"{url} did not finish loading within {CALL_SECONDS} seconds.")
            except Exception as exc:  # Browser errors are reported to the model, not raised.
                return failure(f"{url} did not load: {str(exc).splitlines()[0][:300]}")
            # Bot blocks are intermittent, so a page that returned an HTTP error loads again in a fresh session.
            if not isinstance(status, int) or status < 400:
                self.cache[url] = text
        return {"content": [{"type": "text", "text": section(text, start)}], "isError": False}

    async def load(self, url):
        from playwright.async_api import Error

        # Bot checks block a session after its first page, so every page starts a fresh one.
        context = await self.browser.new_context(**self.session)
        page = await context.new_page()
        downloads, documents = [], []
        page.on("download", lambda download: downloads.append(download))
        page.on("response", lambda r: documents.append(r) if r.request.is_navigation_request() and r.frame == page.main_frame else None)
        try:
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=NAVIGATION_MS)
            except Error:
                for _ in range(20):
                    if downloads:
                        return "download", await self.download(downloads[0])
                    await asyncio.sleep(.1)
                raise
            kind = (response.headers.get("content-type", "") if response else "").split(";", 1)[0].strip().lower()
            if kind == "application/pdf":
                return response.status, self.pdf(url, response.status, await response.body())
            if kind in TEXT_TYPES or kind.endswith("+json") or kind.endswith("+xml"):
                return response.status, document(page.url, response.status, "", await response.text())
            await self.settle(page)
            for attempt in range(2):
                try:
                    data = await page.evaluate(EXTRACT)
                    break
                except Error:
                    # A late client-side navigation replaced the document; read its successor.
                    if attempt:
                        raise
                    await page.wait_for_load_state("domcontentloaded", timeout=NAVIGATION_MS)
            status = documents[-1].status if documents else response.status if response else "unknown"
            return status, document(page.url, status, data["title"], data["text"], data["images"], data["links"])
        finally:
            await context.close()

    async def settle(self, page):
        from playwright.async_api import Error

        try:
            await page.wait_for_load_state("load", timeout=5_000)
        except Error:
            pass
        # Bot checks usually clear themselves within a few seconds in a real browser.
        for _ in range(15):
            try:
                if not CHALLENGE.search(await page.title()):
                    break
            except Error:
                pass
            await page.wait_for_timeout(1000)
        await page.wait_for_timeout(1000)

    async def download(self, download):
        path = Path(await download.path())
        if path.stat().st_size > PDF_LIMIT:
            raise RuntimeError("the file is larger than 50 MB")
        return self.pdf(download.url, "download", path.read_bytes())

    def pdf(self, url, status, data):
        if not data.startswith(b"%PDF"):
            raise RuntimeError("the URL downloads a file that is not a web page or PDF")
        if len(data) > PDF_LIMIT:
            raise RuntimeError("the file is larger than 50 MB")
        with tempfile.NamedTemporaryFile(suffix=".pdf") as file:
            file.write(data)
            file.flush()
            text = pdf_text(file.name)
        return document(url, status, "PDF", text or "The PDF has no text layer; it may contain only scanned images.")


def failure(message):
    return {"content": [{"type": "text", "text": message}], "isError": True}


async def respond(fetcher, message, write):
    if not isinstance(message, dict) or "id" not in message:
        return
    method, params = message.get("method"), message.get("params")
    params = params if isinstance(params, dict) else {}
    if method == "initialize":
        result = {"protocolVersion": params.get("protocolVersion", "2025-06-18"), "capabilities": {"tools": {}},
                  "serverInfo": {"name": "news-fetch", "version": "1"}}
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [TOOL]}
    elif method == "tools/call" and params.get("name") == TOOL["name"]:
        arguments = params.get("arguments")
        result = await fetcher.call(arguments if isinstance(arguments, dict) else {})
    else:
        write({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32601, "message": "Method not found"}})
        return
    write({"jsonrpc": "2.0", "id": message["id"], "result": result})


async def serve():
    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader(limit=1024 * 1024)
    await loop.connect_read_pipe(lambda: asyncio.StreamReaderProtocol(reader), sys.stdin)

    def write(message):
        sys.stdout.write(json.dumps(message) + "\n")
        sys.stdout.flush()

    # Start the browser before answering, so a broken install fails the connection.
    async with Fetcher() as fetcher:
        tasks = set()
        while line := await reader.readline():
            try:
                message = json.loads(line)
            except ValueError:
                write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
                continue
            task = asyncio.create_task(respond(fetcher, message, write))
            tasks.add(task)
            task.add_done_callback(tasks.discard)
        # Answer requests already read before stdin closed.
        await asyncio.gather(*tasks, return_exceptions=True)


async def check():
    async with Fetcher():
        pass


if __name__ == "__main__":
    try:
        asyncio.run(check() if sys.argv[1:] == ["--check"] else serve())
    except Exception as exc:
        print(f"News page browser failed: {exc}", file=sys.stderr)
        sys.exit(1)
