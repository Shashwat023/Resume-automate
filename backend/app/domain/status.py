"""
Application status vocabulary. Must match frontend/src/api/queue.ts
mapBackendStatusToJobStatus exactly, plus the one addition (NEEDS_INPUT)
that the frontend's mapping function is also updated to recognize.
Emitting anything outside this vocabulary silently falls into "waiting"
on the frontend and hides the moment a human needs to act.

Moved here (from core/status.py) as part of the clean-architecture
restructure: status vocabulary is a pure business concept, not
infrastructure — it belongs in the domain layer.
"""

QUEUED = "queued"
CHECKING_URL = "checking_url"
RUNNING = "running"
NEEDS_INPUT = "needs_input"  # Day 4 scope correction: 2FA only — everything else is automated
PAUSED = "paused"  # Day 4 Part H: user-initiated pause, distinct from needs_input (2FA)
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"

TERMINAL = {COMPLETED, FAILED, CANCELLED}
