"""Tests for edupage_mcp.resolvers module."""

from types import SimpleNamespace

from edupage_mcp.resolvers import (
    resolve_class_for_student,
    resolve_class_for_student_across_sessions,
    resolve_student,
    resolve_student_across_sessions,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_student(name: str, class_id: int | None = 1) -> SimpleNamespace:
    return SimpleNamespace(name=name, class_id=class_id)


def _make_class(class_id: int, name: str = "1.A") -> SimpleNamespace:
    return SimpleNamespace(class_id=class_id, name=name)


def _make_edu(students: list | None = None, classes: list | None = None) -> SimpleNamespace:
    """Create a mock edu object with get_students() and get_classes() methods."""
    return SimpleNamespace(
        get_students=lambda: students or [],
        get_classes=lambda: classes or [],
    )


class _MockSessionManager:
    """Minimal mock of SessionManager that supports get_all()."""

    def __init__(self, sessions: dict):
        self._sessions = sessions

    def get_all(self) -> dict:
        if not self._sessions:
            raise RuntimeError("Not logged in.")
        return self._sessions


# ---------------------------------------------------------------------------
# resolve_student()
# ---------------------------------------------------------------------------


class TestResolveStudent:
    def test_exact_match_case_insensitive(self):
        edu = _make_edu(students=[_make_student("Jan Novak"), _make_student("Peter Kovac")])
        student, err = resolve_student(edu, "jan novak")
        assert student is not None
        assert student.name == "Jan Novak"
        assert err == ""

    def test_exact_match_case_sensitive_style(self):
        edu = _make_edu(students=[_make_student("Jan Novak")])
        student, err = resolve_student(edu, "Jan Novak")
        assert student is not None
        assert student.name == "Jan Novak"
        assert err == ""

    def test_substring_match_single(self):
        edu = _make_edu(students=[_make_student("Jan Novak"), _make_student("Peter Kovac")])
        student, err = resolve_student(edu, "Novak")
        assert student is not None
        assert student.name == "Jan Novak"
        assert err == ""

    def test_substring_match_case_insensitive(self):
        edu = _make_edu(students=[_make_student("Jan Novak")])
        student, err = resolve_student(edu, "novak")
        assert student is not None
        assert err == ""

    def test_ambiguous_match(self):
        edu = _make_edu(students=[_make_student("Jan Novak"), _make_student("Jana Novakova")])
        student, err = resolve_student(edu, "Nova")
        assert student is None
        assert "Ambiguous" in err
        assert "Jan Novak" in err
        assert "Jana Novakova" in err

    def test_not_found(self):
        edu = _make_edu(students=[_make_student("Jan Novak")])
        student, err = resolve_student(edu, "Maria Schmidt")
        assert student is None
        assert "not found" in err
        assert "Jan Novak" in err

    def test_no_students(self):
        edu = _make_edu(students=[])
        student, err = resolve_student(edu, "Anyone")
        assert student is None
        assert "No students found" in err

    def test_exact_match_preferred_over_substring(self):
        """Exact match should be returned even if substring also matches others."""
        edu = _make_edu(students=[_make_student("Jan"), _make_student("Jana")])
        student, err = resolve_student(edu, "Jan")
        assert student is not None
        assert student.name == "Jan"
        assert err == ""


# ---------------------------------------------------------------------------
# resolve_class_for_student()
# ---------------------------------------------------------------------------


class TestResolveClassForStudent:
    def test_success(self):
        students = [_make_student("Jan Novak", class_id=10)]
        classes = [_make_class(10, "2.B")]
        edu = _make_edu(students=students, classes=classes)
        student, cls, err = resolve_class_for_student(edu, "Jan Novak")
        assert student is not None
        assert cls is not None
        assert cls.name == "2.B"
        assert err == ""

    def test_student_not_found(self):
        edu = _make_edu(students=[_make_student("Jan Novak")])
        student, cls, err = resolve_class_for_student(edu, "Nobody")
        assert student is None
        assert cls is None
        assert "not found" in err

    def test_no_class_id(self):
        students = [_make_student("Jan Novak", class_id=None)]
        edu = _make_edu(students=students)
        student, cls, err = resolve_class_for_student(edu, "Jan Novak")
        assert student is not None
        assert cls is None
        assert "no class_id" in err

    def test_class_not_found(self):
        students = [_make_student("Jan Novak", class_id=99)]
        classes = [_make_class(10, "1.A")]
        edu = _make_edu(students=students, classes=classes)
        student, cls, err = resolve_class_for_student(edu, "Jan Novak")
        assert student is not None
        assert cls is None
        assert "not found" in err

    def test_class_id_negative_match(self):
        """The resolver checks both class_id and abs(class_id)."""
        students = [_make_student("Jan Novak", class_id=-10)]
        classes = [_make_class(-10, "3.C")]
        edu = _make_edu(students=students, classes=classes)
        student, cls, err = resolve_class_for_student(edu, "Jan Novak")
        assert student is not None
        assert cls is not None
        assert cls.name == "3.C"
        assert err == ""


# ---------------------------------------------------------------------------
# resolve_student_across_sessions()
# ---------------------------------------------------------------------------


class TestResolveStudentAcrossSessions:
    def test_single_match(self):
        edu1 = _make_edu(students=[_make_student("Jan Novak")])
        edu2 = _make_edu(students=[_make_student("Peter Kovac")])
        sessions = _MockSessionManager({"school1": edu1, "school2": edu2})
        edu, student, err = resolve_student_across_sessions(sessions, "Jan Novak")
        assert edu is edu1
        assert student.name == "Jan Novak"
        assert err == ""

    def test_multi_school_match_errors(self):
        """Student found in multiple schools without specifying school param."""
        edu1 = _make_edu(students=[_make_student("Jan Novak")])
        edu2 = _make_edu(students=[_make_student("Jan Novak")])
        sessions = _MockSessionManager({"school1": edu1, "school2": edu2})
        edu, student, err = resolve_student_across_sessions(sessions, "Jan Novak")
        assert edu is None
        assert student is None
        assert "multiple schools" in err
        assert "school" in err.lower()

    def test_school_param_narrows_search(self):
        edu1 = _make_edu(students=[_make_student("Jan Novak")])
        edu2 = _make_edu(students=[_make_student("Jan Novak")])
        sessions = _MockSessionManager({"school1": edu1, "school2": edu2})
        edu, student, err = resolve_student_across_sessions(sessions, "Jan Novak", school="school1")
        assert edu is edu1
        assert student.name == "Jan Novak"
        assert err == ""

    def test_not_found_anywhere(self):
        edu1 = _make_edu(students=[_make_student("Jan Novak")])
        edu2 = _make_edu(students=[_make_student("Peter Kovac")])
        sessions = _MockSessionManager({"school1": edu1, "school2": edu2})
        edu, student, err = resolve_student_across_sessions(sessions, "Maria Schmidt")
        assert edu is None
        assert student is None
        assert "not found" in err

    def test_not_found_lists_available(self):
        edu1 = _make_edu(students=[_make_student("Jan Novak")])
        sessions = _MockSessionManager({"school1": edu1})
        _, _, err = resolve_student_across_sessions(sessions, "Nobody")
        assert "Jan Novak" in err
        assert "school1" in err

    def test_school_not_in_sessions(self):
        edu1 = _make_edu(students=[_make_student("Jan Novak")])
        sessions = _MockSessionManager({"school1": edu1})
        _, _, err = resolve_student_across_sessions(sessions, "Jan", school="other")
        assert "not found" in err.lower()
        assert "school1" in err

    def test_single_school_single_student(self):
        edu = _make_edu(students=[_make_student("Only Child")])
        sessions = _MockSessionManager({"myschool": edu})
        result_edu, student, err = resolve_student_across_sessions(sessions, "Only Child")
        assert result_edu is edu
        assert student.name == "Only Child"
        assert err == ""


# ---------------------------------------------------------------------------
# resolve_class_for_student_across_sessions()
# ---------------------------------------------------------------------------


class TestResolveClassForStudentAcrossSessions:
    def test_success(self):
        students = [_make_student("Jan Novak", class_id=10)]
        classes = [_make_class(10, "2.B")]
        edu = _make_edu(students=students, classes=classes)
        sessions = _MockSessionManager({"school1": edu})
        result_edu, student, cls, err = resolve_class_for_student_across_sessions(sessions, "Jan Novak")
        assert result_edu is edu
        assert student.name == "Jan Novak"
        assert cls.name == "2.B"
        assert err == ""

    def test_student_not_found(self):
        edu = _make_edu(students=[_make_student("Jan Novak")])
        sessions = _MockSessionManager({"school1": edu})
        _, _, _, err = resolve_class_for_student_across_sessions(sessions, "Nobody")
        assert "not found" in err

    def test_class_not_found_for_student(self):
        students = [_make_student("Jan Novak", class_id=99)]
        classes = [_make_class(10, "1.A")]
        edu = _make_edu(students=students, classes=classes)
        sessions = _MockSessionManager({"school1": edu})
        result_edu, student, cls, err = resolve_class_for_student_across_sessions(sessions, "Jan Novak")
        assert result_edu is edu
        assert student is not None
        assert cls is None
        assert "not found" in err

    def test_with_school_param(self):
        students = [_make_student("Jan Novak", class_id=5)]
        classes = [_make_class(5, "3.A")]
        edu = _make_edu(students=students, classes=classes)
        sessions = _MockSessionManager({"school1": edu, "school2": _make_edu()})
        result_edu, student, cls, err = resolve_class_for_student_across_sessions(
            sessions, "Jan Novak", school="school1"
        )
        assert result_edu is edu
        assert cls.name == "3.A"
        assert err == ""
