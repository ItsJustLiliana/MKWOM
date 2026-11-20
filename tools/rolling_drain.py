"""Pure transition policy for a future MKWOM blue/green, race-safe drain.

IMPORTANT: This does not route traffic, run two lobby servers, or claim
score persistence. The authoritative game server must report completed
results *after durable acknowledgement* before calling result_persisted.
The live systemd deploy path must not use this until dual-version routing,
UDP isolation and durable score storage are implemented and tested.
"""
from dataclasses import dataclass, field

DRAIN_SECONDS = 60 * 60


@dataclass
class Drain:
    """One old server generation once new matchmaking has been redirected."""

    started_at: float
    active_races: set[str] = field(default_factory=set)
    persisted_results: set[str] = field(default_factory=set)
    stopped: bool = False

    def __post_init__(self) -> None:
        if not self.started_at >= 0:
            raise ValueError("invalid drain start")

    @property
    def deadline(self) -> float:
        return self.started_at + DRAIN_SECONDS

    def new_race_allowed(self) -> bool:
        """Old generation accepts no new race; new generation owns matchmaking."""
        return False

    def result_persisted(self, race_id: str) -> None:
        """Called only after server has durably saved the race's results."""
        if not race_id or race_id not in self.active_races:
            raise ValueError("unknown race; cannot acknowledge persistence")
        self.persisted_results.add(race_id)

    def decision(self, now: float) -> str:
        """wait, retire, or force-retire at the absolute one-hour deadline."""
        if self.stopped:
            return "retired"
        if now < self.started_at:
            raise ValueError("clock moved before drain start")
        if now >= self.deadline:
            return "force-retire"
        if self.active_races <= self.persisted_results:
            return "retire"
        return "wait"
