"""Isolated demo through real owner and worker interfaces; no production bypass."""

from contextlib import contextmanager
from pathlib import Path
import sys
import threading

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent / "app"))
from support import ServerFixture
from werkzeug.serving import make_server, WSGIRequestHandler


class QuietHandler(WSGIRequestHandler):
    def log_request(self, code, size=None):
        pass


@contextmanager
def preview(port=0):
    ServerFixture.setUpClass()
    fixture = ServerFixture()
    fixture.setUp()
    try:
        fixture.app.config["SESSION_COOKIE_SECURE"] = False
        reporter, run = fixture.due()
        fixture.edit(
            reporter,
            prompt="Follow research since your last report. Explain the findings, uncertainty, and useful sources.",
        )
        articles = [
            fixture.article(
                title="A little curiosity goes a long way",
                summary="A demonstration edition: thoughtful reporting, useful context, and room to follow your own interests.",
                body_markdown="## The weekend desk\n\nThis is **sample content** for testing the News server. It is not a researched recommendation.\n\nA good roundup starts with what matters to your family: the weather, the time you have, and the things you love to explore.\n\n### Make room for discovery\n\n- Something hands-on\n- Something close to home\n- Something you have never tried\n\n| Plan | Time |\n| --- | --- |\n| Museum visit | Two hours |\n| Neighborhood discovery | An afternoon |\n\nSee the [example source](https://example.com/research).",
            ),
            fixture.article(
                title="The questions behind the findings",
                summary="A sample research report for testing article lists, sources, and reporter history.",
            ),
        ]
        fixture.result(run, fixture.envelope(fixture.claim(run), articles=articles))
        response = fixture.form(
            "/newsroom/reporters",
            name="The weekend desk",
            prompt="Find five nearby family outings for the upcoming weekend. Favor variety, current official sources, and shorter travel from West Seattle.",
            cadence="weekly",
            weekdays=["thu"],
        )
        assert response.status_code == 303
        server = make_server(
            "127.0.0.1", port, fixture.app, threaded=True, request_handler=QuietHandler
        )
        fixture.base_url = f"http://127.0.0.1:{server.server_port}"
        fixture.app.config["BASE_URL"] = fixture.base_url
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield fixture
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
    finally:
        fixture.doCleanups()


if __name__ == "__main__":
    import json
    import time

    with preview(3071) as fixture:
        directory = Path(__file__).resolve().parents[1] / "var"
        directory.mkdir(exist_ok=True)
        (directory / "preview-headers.json").write_text(json.dumps(fixture.owner))
        print(
            f"Disposable preview: {fixture.base_url}\nOwner headers: var/preview-headers.json",
            flush=True,
        )
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            pass
