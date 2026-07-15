"""Shared helper for running coroutines from synchronous unittest.TestCase
methods. runtests.py's run_tests() is itself a coroutine, so a plain
asyncio.run() inside a test method fails with "cannot be called from a
running event loop" — run the coroutine on its own thread/loop instead.
"""
import asyncio
import concurrent.futures


def run_async(coro):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()
