from pathlib import Path

import pytest

from vidrensic.core.case import Case
from vidrensic.core.review import ReviewStore


def test_review_database_symlink_is_rejected(tmp_path: Path) -> None:
    case = Case.create(tmp_path, "case-review-symlink")
    target = case.root / "state" / "real-review.sqlite3"
    link = case.root / "state" / "review.sqlite3"
    target.touch()
    link.symlink_to(target)

    with pytest.raises(ValueError, match="may not be a symlink"):
        ReviewStore(link, case_root=case.root)
