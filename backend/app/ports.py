"""
Protocol definitions for cross-boundary contracts — formalizes patterns
that already existed informally in the codebase:

- QueuePort: what worker/queue_runner.py already exposes as free functions,
  now typed as an interface so services can depend on the contract instead
  of importing the module directly (and can be given a fake in tests).
- RunnerPort: the shape of `run_application` — what main.py's lifespan()
  already wires into queue_runner via `set_run_fn`, now typed instead of a
  bare untyped callable stored in a mutable global.
- ResumeStoragePort: local filesystem today (see services/resume/storage.py),
  swappable for S3/GDrive later without touching resume_service.py or the
  route — this is where "scalable" has a concrete payoff.
"""

from dataclasses import dataclass
from typing import Protocol


class QueuePort(Protocol):
    async def enqueue_application(self, application_id: str) -> None: ...
    async def signal_resume(self, application_id: str) -> None: ...
    async def signal_cancel(self, application_id: str) -> None: ...
    def is_cancelled(self, application_id: str) -> bool: ...
    def cleanup(self, application_id: str) -> None: ...


class RunnerPort(Protocol):
    async def __call__(self, application_id: str) -> None: ...


@dataclass(frozen=True)
class SavedFile:
    file_path: str
    resume_url: str


class ResumeStoragePort(Protocol):
    async def save(
        self, profile_id: int, filename: str, contents: bytes
    ) -> SavedFile: ...
    async def delete(self, file_path: str) -> None: ...
