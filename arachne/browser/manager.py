import asyncio
from arachne.browser.task import Task

from playwright.async_api import async_playwright, Page

from arachne.browser.state import BrowserState, BrowserContextFactory, VideoArtifact

import structlog
from typing import Self

from arachne.exceptions import MissingBrowserState

log = structlog.get_logger()


class BrowserManager:
    pages = None
    instance = None
    state: BrowserState = None
    page = None

    def __new__(self):
        if self.instance is None:
            self.instance = super().__new__(self)
        return self.instance

    async def open_url(self, url: str) -> Page:
        browser_state = await self.state.goto_page(url)
        return

    async def _init(
            self,
            url: str | None = None,
    ) -> Self:
        pw = await async_playwright().start()
        (
            browser_context,
            browser_artifacts,
            browser_cleanup,
        ) = await BrowserContextFactory.create_browser_context(
            pw,
            url=url,
        )
        self.browser_context = browser_context
        self.state = BrowserState(
            pw=pw,
            browser_context=browser_context,
            page=None,
            browser_artifacts=browser_artifacts,
            browser_cleanup=browser_cleanup,
        )

    async def get_for_workflow_run(self, workflow_run_id: str) -> BrowserState | None:
        if workflow_run_id in self.pages:
            return self.pages[workflow_run_id]
        return None

    def set_video_artifact_for_task(self, task: Task, artifacts: list[VideoArtifact]) -> None:
        if task.workflow_run_id and task.workflow_run_id in self.pages:
            self.pages[task.workflow_run_id].browser_artifacts.video_artifacts = artifacts
            return
        if task.task_id in self.pages:
            self.pages[task.task_id].browser_artifacts.video_artifacts = artifacts
            return

        raise MissingBrowserState(task_id=task.task_id)

    async def get_video_artifacts(
            self,
            browser_state: BrowserState,
            task_id: str = "",
            workflow_id: str = "",
            workflow_run_id: str = "",
    ) -> list[VideoArtifact]:
        if len(browser_state.browser_artifacts.video_artifacts) == 0:
            log.warning(
                "Video data not found for task",
                task_id=task_id,
                workflow_id=workflow_id,
                workflow_run_id=workflow_run_id,
            )
            return []

        for i, video_artifact in enumerate(browser_state.browser_artifacts.video_artifacts):
            path = video_artifact.video_path
            if path:
                try:
                    with open(path, "rb") as f:
                        browser_state.browser_artifacts.video_artifacts[i].video_data = f.read()

                except FileNotFoundError:
                    pass
        return browser_state.browser_artifacts.video_artifacts

    async def get_har_data(
            self,
            browser_state: BrowserState,
            task_id: str = "",
            workflow_id: str = "",
            workflow_run_id: str = "",
    ) -> bytes:
        if browser_state:
            path = browser_state.browser_artifacts.har_path
            if path:
                with open(path, "rb") as f:
                    return f.read()
        log.warning(
            "HAR data not found for task",
            task_id=task_id,
            workflow_id=workflow_id,
            workflow_run_id=workflow_run_id,
        )
        return b""

    @classmethod
    async def close(self) -> None:
        log.info("Closing BrowserManager")
        for browser_state in self.pages.values():
            await browser_state.close()
        self.pages = dict()
        log.info("BrowserManger is closed")

    async def cleanup_for_task(self, task_id: str, close_browser_on_completion: bool = True) -> BrowserState | None:
        log.info("Cleaning up for task")
        browser_state_to_close = self.pages.pop(task_id, None)
        try:
            if browser_state_to_close:
                async with asyncio.timeout(180):
                    # Stop tracing before closing the browser if tracing is enabled
                    if browser_state_to_close.browser_context and browser_state_to_close.browser_artifacts.traces_dir:
                        trace_path = f"{browser_state_to_close.browser_artifacts.traces_dir}/{task_id}.zip"
                        await browser_state_to_close.browser_context.tracing.stop(path=trace_path)
                        log.info("Stopped tracing", trace_path=trace_path)
                    await browser_state_to_close.close(close_browser_on_completion=close_browser_on_completion)
            log.info("Task is cleaned up")
        except TimeoutError:
            log.warning("Timeout on task cleanup")

        return browser_state_to_close

    async def cleanup_for_workflow_run(
            self,
            workflow_run_id: str,
            task_ids: list[str],
            close_browser_on_completion: bool = True,
    ) -> BrowserState | None:
        log.info("Cleaning up for workflow run")
        browser_state_to_close = self.pages.pop(workflow_run_id, None)
        if browser_state_to_close:
            # Stop tracing before closing the browser if tracing is enabled
            if browser_state_to_close.browser_context and browser_state_to_close.browser_artifacts.traces_dir:
                trace_path = f"{browser_state_to_close.browser_artifacts.traces_dir}/{workflow_run_id}.zip"
                await browser_state_to_close.browser_context.tracing.stop(path=trace_path)
                log.info("Stopped tracing", trace_path=trace_path)

            await browser_state_to_close.close(close_browser_on_completion=close_browser_on_completion)
        for task_id in task_ids:
            self.pages.pop(task_id, None)
        log.info("Workflow run is cleaned up")

        return browser_state_to_close


async def createBrowserManager(url: str | None = None) -> BrowserManager:
    bm = BrowserManager()
    await bm._init(url)
    print("Browser state created")
    return bm
