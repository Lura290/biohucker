import pytest

from biohucker.journal.repo import JournalRepo, create_db_engine


@pytest.fixture
def db_url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'test.db'}"


@pytest.fixture
def repo(db_url) -> JournalRepo:
    return JournalRepo(create_db_engine(db_url))
