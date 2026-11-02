import asyncio
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


def event_time() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass
class RunState:
    id: str
    conversation_id: str
    user_id: str
    status: str = "running"
    events: list[dict[str, Any]] = field(default_factory=list)
    condition: asyncio.Condition = field(default_factory=asyncio.Condition)

    @property
    def last_event_id(self) -> int:
        return len(self.events)


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, RunState] = {}
        self._expiry_tasks: set[asyncio.Task[None]] = set()

    async def create(self, conversation_id: str, user_id: str) -> RunState:
        run = RunState(
            id=str(uuid4()),
            conversation_id=conversation_id,
            user_id=user_id,
        )
        self._runs[run.id] = run
        return run

    def get(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    async def publish(self, run: RunState, event_type: str, **payload: Any) -> None:
        async with run.condition:
            event = {
                "id": run.last_event_id + 1,
                "type": event_type,
                "at": event_time(),
                **payload,
            }
            run.events.append(event)
            run.condition.notify_all()

    async def finish(self, run: RunState, status: str = "complete") -> None:
        async with run.condition:
            run.status = status
            run.condition.notify_all()
        task = asyncio.create_task(self._expire(run.id))
        self._expiry_tasks.add(task)
        task.add_done_callback(self._expiry_tasks.discard)

    async def events_after(
        self,
        run: RunState,
        event_id: int,
    ) -> list[dict[str, Any]]:
        async with run.condition:
            return [event for event in run.events if event["id"] > event_id]

    async def wait_for_change(
        self,
        run: RunState,
        event_id: int,
        timeout: float = 15,
    ) -> bool:
        async with run.condition:
            if run.last_event_id > event_id or run.status != "running":
                return True
            try:
                await asyncio.wait_for(run.condition.wait(), timeout=timeout)
                return True
            except TimeoutError:
                return False

    async def _expire(self, run_id: str) -> None:
        await asyncio.sleep(15 * 60)
        run = self._runs.get(run_id)
        if run and run.status != "running":
            self._runs.pop(run_id, None)

    async def shutdown(self) -> None:
        tasks = list(self._expiry_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

