import pytest
import tracemalloc

@pytest.fixture(scope="session", autouse=True)
def track_memory_for_all_tests():
    """Start tracemalloc for the whole test session."""
    tracemalloc.start()
    yield
    tracemalloc.stop()
