from dataclasses import dataclass


@dataclass(frozen=True)
class VKPublishResult:
    post_id: int
    owner_id: int
