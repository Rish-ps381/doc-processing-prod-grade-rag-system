"""Local worker entrypoint. The API currently owns the in-process queue; this entrypoint documents the future worker seam."""

from app.main import app


if __name__ == "__main__":
    raise SystemExit("Sprint 1 uses the API's in-process async worker. Replace JobQueue with a durable queue for a separate worker process.")
