import pytest


@pytest.fixture
def anyio_backend() -> str:
    """Pin every ``@pytest.mark.anyio`` test to the asyncio backend.

    Parts of the suite (Atlas browser agent, background tasks) call asyncio
    primitives such as ``asyncio.wait_for`` directly, so the tests must run on
    asyncio rather than being parametrized across asyncio + trio.
    """
    return "asyncio"
