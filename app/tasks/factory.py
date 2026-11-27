from collections.abc import Callable

from app.tasks.base import MLTask


class TaskFactory:
    """Explicit registry: task input can never import arbitrary Python code."""

    def __init__(self):
        self._builders: dict[str, Callable[[], MLTask]] = {}

    def register(self, name: str, builder: Callable[[], MLTask]) -> None:
        if not isinstance(name, str) or not name or name in self._builders:
            raise ValueError(f"Invalid or duplicate task registration: {name}")
        self._builders[name] = builder

    def create(self, name: str) -> MLTask:
        if not isinstance(name, str) or name not in self._builders:
            raise ValueError(f"Unsupported task. Choose one of: {', '.join(self.names)}")
        return self._builders[name]()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._builders))


def default_factory() -> TaskFactory:
    from app.tasks.tabular import AutoTabularTask, ClassificationTask, RegressionTask

    factory = TaskFactory()
    factory.register("tabular", AutoTabularTask)
    factory.register("classification", ClassificationTask)
    factory.register("regression", RegressionTask)
    return factory
