from types import TracebackType
from typing_extensions import Self

from .scope_manager import ScopeManager
from .span import Span

class Scope:
    def __init__(self, manager: ScopeManager, span: Span) -> None: ...
    @property
    def span(self) -> Span: ...
    @property
    def manager(self) -> ScopeManager: ...
    def close(self) -> None: ...
    def __enter__(self) -> Self: ...
    def __exit__(
        self, exc_type: type[BaseException] | None, exc_val: BaseException | None, exc_tb: TracebackType | None
    ) -> None: ...