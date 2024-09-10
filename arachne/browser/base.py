from abc import ABC, abstractmethod
from typing import Any, TypedDict, Union

from playwright.async_api import Page as PageAsync
from playwright.sync_api import Page as PageSync

AnyDriver = Union[PageSync, PageAsync]





class BrowserAdapter(ABC):
    @abstractmethod
    async def run_js(self, js: str) -> Any:
        pass

    @abstractmethod
    async def take_screenshot(self) -> bytes:
        pass

    @abstractmethod
    async def set_viewport_size(self, width: int, height: int) -> None:
        pass

    @abstractmethod
    async def get_viewport_size(self) -> ViewPortSize:
        pass
