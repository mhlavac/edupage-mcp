"""Tests for edupage_mcp.serializers module."""

import json
from datetime import date, datetime, time
from enum import Enum
from types import SimpleNamespace

from edupage_mcp.serializers import (
    extract_assignment_fields,
    extract_homework_fields,
    lean_class,
    lean_classroom,
    lean_grade,
    lean_json,
    lean_lesson,
    lean_student,
    lean_subject,
    lean_teacher,
    lean_timeline_event,
    lean_timetable,
    serialize,
    to_json,
)

# ---------------------------------------------------------------------------
# serialize()
# ---------------------------------------------------------------------------


class TestSerialize:
    def test_none(self):
        assert serialize(None) is None

    def test_string(self):
        assert serialize("hello") == "hello"

    def test_int(self):
        assert serialize(42) == 42

    def test_float(self):
        assert serialize(3.14) == 3.14

    def test_bool_true(self):
        assert serialize(True) is True

    def test_bool_false(self):
        assert serialize(False) is False

    def test_date(self):
        d = date(2025, 6, 15)
        assert serialize(d) == "2025-06-15"

    def test_datetime(self):
        dt = datetime(2025, 6, 15, 10, 30, 0)
        assert serialize(dt) == "2025-06-15T10:30:00"

    def test_time(self):
        t = time(8, 30)
        assert serialize(t) == "08:30"

    def test_list(self):
        assert serialize([1, "two", None]) == [1, "two", None]

    def test_tuple(self):
        assert serialize((1, 2)) == [1, 2]

    def test_nested_list(self):
        assert serialize([[1, 2], [3]]) == [[1, 2], [3]]

    def test_dict(self):
        assert serialize({"a": 1, "b": "two"}) == {"a": 1, "b": "two"}

    def test_dict_with_non_string_keys(self):
        result = serialize({1: "one", 2: "two"})
        assert result == {"1": "one", "2": "two"}

    def test_nested_dict(self):
        result = serialize({"a": {"b": 1}})
        assert result == {"a": {"b": 1}}

    def test_object_with_dict(self):
        obj = SimpleNamespace(name="Alice", age=10)
        result = serialize(obj)
        assert result == {"name": "Alice", "age": 10}

    def test_object_with_dict_skips_private(self):
        obj = SimpleNamespace(name="Alice", _secret="hidden")
        result = serialize(obj)
        assert "name" in result
        assert "_secret" not in result

    def test_enum_hits_dict_branch(self):
        """Python enums have __dict__, so serialize() takes that branch.

        All enum attributes start with '_', so the result is an empty dict.
        This matches the actual code path order: __dict__ is checked before .value.
        """

        class Color(Enum):
            RED = "red"
            BLUE = "blue"

        # Enum __dict__ attributes are all private (_name_, _value_, etc.)
        assert serialize(Color.RED) == {}

    def test_value_attribute_without_dict(self):
        """Objects with .value but no __dict__ go through the .value branch."""

        class Token:
            __slots__ = ("value",)

            def __init__(self, val):
                self.value = val

        assert serialize(Token("abc")) == "abc"

    def test_fallback_to_str(self):
        """Objects with no __dict__ and no .value get str()."""

        class Weird:
            __slots__ = ()

            def __str__(self):
                return "weird_thing"

        assert serialize(Weird()) == "weird_thing"

    def test_list_of_objects(self):
        objs = [SimpleNamespace(x=1), SimpleNamespace(x=2)]
        result = serialize(objs)
        assert result == [{"x": 1}, {"x": 2}]

    def test_date_inside_dict(self):
        result = serialize({"d": date(2025, 1, 1)})
        assert result == {"d": "2025-01-01"}


# ---------------------------------------------------------------------------
# to_json()
# ---------------------------------------------------------------------------


class TestToJson:
    def test_returns_valid_json_string(self):
        result = to_json({"key": "value"})
        parsed = json.loads(result)
        assert parsed == {"key": "value"}

    def test_handles_none(self):
        result = to_json(None)
        assert json.loads(result) is None

    def test_handles_list(self):
        result = to_json([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]

    def test_handles_objects(self):
        obj = SimpleNamespace(a=1)
        result = to_json(obj)
        assert json.loads(result) == {"a": 1}

    def test_unicode_preserved(self):
        result = to_json({"name": "Jozef Mrkvicka"})
        assert "Jozef Mrkvicka" in result


# ---------------------------------------------------------------------------
# lean_json()
# ---------------------------------------------------------------------------


class TestLeanJson:
    def test_returns_valid_json(self):
        result = lean_json({"a": 1})
        assert json.loads(result) == {"a": 1}

    def test_handles_list(self):
        result = lean_json([1, 2, 3])
        assert json.loads(result) == [1, 2, 3]

    def test_unicode_preserved(self):
        result = lean_json({"name": "Erika Müller"})
        assert "Erika Müller" in result


# ---------------------------------------------------------------------------
# lean_lesson()
# ---------------------------------------------------------------------------


class TestLeanLesson:
    def _make_lesson(self, **overrides):
        defaults = {
            "period": 1,
            "start_time": time(8, 0),
            "end_time": time(8, 45),
            "duration": 45,
            "subject": SimpleNamespace(short="MAT", name="Matematika"),
            "teachers": [SimpleNamespace(name="Mgr. Novak")],
            "classrooms": [SimpleNamespace(short="101", name="Room 101")],
            "groups": [],
            "is_cancelled": False,
            "is_event": False,
            "curriculum": None,
            "online_lesson_link": None,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_basic_lesson(self):
        lesson = self._make_lesson()
        result = lean_lesson(lesson)
        assert result["period"] == 1
        assert result["start"] == "08:00"
        assert result["end"] == "08:45"
        assert result["duration"] == 45
        assert result["subject"] == "MAT"
        assert result["subject_name"] == "Matematika"
        assert result["teachers"] == ["Mgr. Novak"]
        assert result["classrooms"] == ["101"]
        assert result["groups"] == []
        assert result["cancelled"] is False
        assert result["is_event"] is False
        assert result["curriculum"] is None
        assert result["online_lesson_link"] is None

    def test_no_start_time(self):
        lesson = self._make_lesson(start_time=None)
        result = lean_lesson(lesson)
        assert result["start"] is None

    def test_no_end_time(self):
        lesson = self._make_lesson(end_time=None)
        result = lean_lesson(lesson)
        assert result["end"] is None

    def test_no_subject(self):
        lesson = self._make_lesson(subject=None)
        result = lean_lesson(lesson)
        assert result["subject"] is None
        assert result["subject_name"] is None

    def test_multiple_teachers(self):
        teachers = [SimpleNamespace(name="A"), SimpleNamespace(name="B")]
        lesson = self._make_lesson(teachers=teachers)
        result = lean_lesson(lesson)
        assert result["teachers"] == ["A", "B"]

    def test_no_teachers(self):
        lesson = self._make_lesson(teachers=[])
        result = lean_lesson(lesson)
        assert result["teachers"] == []

    def test_classroom_uses_short(self):
        rooms = [SimpleNamespace(short="A1", name="Room A1")]
        lesson = self._make_lesson(classrooms=rooms)
        assert lean_lesson(lesson)["classrooms"] == ["A1"]

    def test_cancelled_lesson(self):
        lesson = self._make_lesson(is_cancelled=True)
        assert lean_lesson(lesson)["cancelled"] is True

    def test_event_lesson(self):
        lesson = self._make_lesson(is_event=True)
        assert lean_lesson(lesson)["is_event"] is True


# ---------------------------------------------------------------------------
# lean_timetable()
# ---------------------------------------------------------------------------


class TestLeanTimetable:
    def _make_lesson(self):
        return SimpleNamespace(
            period=1,
            start_time=time(8, 0),
            end_time=time(8, 45),
            duration=45,
            subject=SimpleNamespace(short="SJL", name="Slovensky jazyk"),
            teachers=[SimpleNamespace(name="Mgr. A")],
            classrooms=[SimpleNamespace(short="201", name="Room 201")],
            groups=[],
            is_cancelled=False,
            is_event=False,
            curriculum=None,
            online_lesson_link=None,
        )

    def test_list_of_lessons(self):
        lessons = [self._make_lesson(), self._make_lesson()]
        result = lean_timetable(lessons)
        assert len(result) == 2
        assert all(isinstance(r, dict) for r in result)

    def test_timetable_object_with_lessons_attr(self):
        tt = SimpleNamespace(lessons=[self._make_lesson()])
        result = lean_timetable(tt)
        assert len(result) == 1

    def test_empty_list(self):
        assert lean_timetable([]) == []

    def test_none_lessons(self):
        assert lean_timetable(None) == []


# ---------------------------------------------------------------------------
# lean_grade()
# ---------------------------------------------------------------------------


class TestLeanGrade:
    def _make_grade(self, **overrides):
        defaults = {
            "event_id": "g123",
            "title": "Test 1",
            "grade_n": "1",
            "comment": "Good",
            "date": date(2025, 3, 15),
            "subject_name": "Math",
            "subject_id": "s1",
            "teacher": SimpleNamespace(name="Mgr. B"),
            "max_points": 20,
            "importance": 3,
            "verbal": None,
            "percent": 95.0,
            "class_grade_avg": 85.0,
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_basic_grade(self):
        grade = self._make_grade()
        result = lean_grade(grade)
        assert result["event_id"] == "g123"
        assert result["title"] == "Test 1"
        assert result["grade"] == "1"
        assert result["comment"] == "Good"
        assert result["date"] == "2025-03-15"
        assert result["subject"] == "Math"
        assert result["subject_id"] == "s1"
        assert result["teacher"] == "Mgr. B"
        assert result["max_points"] == 20
        assert result["importance"] == 3
        assert result["verbal"] is None
        assert result["percent"] == 95.0
        assert result["class_avg"] == 85.0

    def test_no_date(self):
        grade = self._make_grade(date=None)
        assert lean_grade(grade)["date"] is None

    def test_no_teacher(self):
        grade = self._make_grade(teacher=None)
        assert lean_grade(grade)["teacher"] is None


# ---------------------------------------------------------------------------
# lean_student()
# ---------------------------------------------------------------------------


class TestLeanStudent:
    def test_basic_student(self):
        student = SimpleNamespace(person_id="p1", name="Jan Novak", class_id="c1", number_in_class=5)
        result = lean_student(student)
        assert result["person_id"] == "p1"
        assert result["name"] == "Jan Novak"
        assert result["class_id"] == "c1"
        assert result["number"] == 5

    def test_missing_attributes(self):
        student = SimpleNamespace()
        result = lean_student(student)
        assert result["person_id"] is None
        assert result["name"] is None
        assert result["class_id"] is None
        assert result["number"] is None


# ---------------------------------------------------------------------------
# lean_teacher()
# ---------------------------------------------------------------------------


class TestLeanTeacher:
    def test_basic_teacher(self):
        teacher = SimpleNamespace(person_id="t1", name="Mgr. Kovac", classroom_name="A1")
        result = lean_teacher(teacher)
        assert result["person_id"] == "t1"
        assert result["name"] == "Mgr. Kovac"
        assert result["classroom"] == "A1"

    def test_missing_attributes(self):
        teacher = SimpleNamespace()
        result = lean_teacher(teacher)
        assert result["person_id"] is None
        assert result["name"] is None
        assert result["classroom"] is None


# ---------------------------------------------------------------------------
# lean_class()
# ---------------------------------------------------------------------------


class TestLeanClass:
    def test_basic_class(self):
        cls = SimpleNamespace(
            class_id="c1",
            name="1.A",
            short="1A",
            grade=1,
            homeroom_teachers=[SimpleNamespace(name="Mgr. Sova")],
        )
        result = lean_class(cls)
        assert result["class_id"] == "c1"
        assert result["name"] == "1.A"
        assert result["short"] == "1A"
        assert result["grade"] == 1
        assert result["homeroom_teachers"] == ["Mgr. Sova"]

    def test_no_homeroom_teachers(self):
        cls = SimpleNamespace(class_id="c1", name="1.A", short="1A", grade=1, homeroom_teachers=None)
        result = lean_class(cls)
        assert result["homeroom_teachers"] == []

    def test_empty_homeroom_teachers(self):
        cls = SimpleNamespace(class_id="c1", name="1.A", short="1A", grade=1, homeroom_teachers=[])
        result = lean_class(cls)
        assert result["homeroom_teachers"] == []

    def test_multiple_homeroom_teachers(self):
        teachers = [SimpleNamespace(name="A"), SimpleNamespace(name="B")]
        cls = SimpleNamespace(class_id="c1", name="1.A", short="1A", grade=1, homeroom_teachers=teachers)
        result = lean_class(cls)
        assert result["homeroom_teachers"] == ["A", "B"]


# ---------------------------------------------------------------------------
# lean_classroom()
# ---------------------------------------------------------------------------


class TestLeanClassroom:
    def test_basic_classroom(self):
        room = SimpleNamespace(classroom_id="r1", name="Physics Lab", short="FYZ")
        result = lean_classroom(room)
        assert result["classroom_id"] == "r1"
        assert result["name"] == "Physics Lab"
        assert result["short"] == "FYZ"

    def test_missing_attributes(self):
        room = SimpleNamespace()
        result = lean_classroom(room)
        assert result["classroom_id"] is None
        assert result["name"] is None
        assert result["short"] is None


# ---------------------------------------------------------------------------
# lean_subject()
# ---------------------------------------------------------------------------


class TestLeanSubject:
    def test_basic_subject(self):
        subj = SimpleNamespace(subject_id="s1", name="Matematika", short="MAT")
        result = lean_subject(subj)
        assert result["subject_id"] == "s1"
        assert result["name"] == "Matematika"
        assert result["short"] == "MAT"

    def test_missing_attributes(self):
        subj = SimpleNamespace()
        result = lean_subject(subj)
        assert result["subject_id"] is None
        assert result["name"] is None
        assert result["short"] is None


# ---------------------------------------------------------------------------
# lean_timeline_event()
# ---------------------------------------------------------------------------


class TestLeanTimelineEvent:
    def _make_event(self, **overrides):
        class MockEventType:
            def __init__(self, val):
                self.value = val

        defaults = {
            "event_id": "e1",
            "event_type": MockEventType("homework"),
            "timestamp": datetime(2025, 6, 15, 10, 0),
            "text": "Do page 42",
            "author": SimpleNamespace(name="Mgr. Novak"),
            "is_done": False,
            "is_starred": True,
            "created_at": datetime(2025, 6, 14, 8, 0),
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_basic_event(self):
        event = self._make_event()
        result = lean_timeline_event(event)
        assert result["event_id"] == "e1"
        assert result["type"] == "homework"
        assert result["timestamp"] == "2025-06-15T10:00:00"
        assert result["text"] == "Do page 42"
        assert result["author"] == "Mgr. Novak"
        assert result["is_done"] is False
        assert result["is_starred"] is True
        assert result["created_at"] == "2025-06-14T08:00:00"

    def test_no_event_type(self):
        event = self._make_event(event_type=None)
        result = lean_timeline_event(event)
        assert result["type"] is None

    def test_event_type_without_value(self):
        """event_type is a string, not an enum-like object."""
        event = self._make_event(event_type="sprava")
        result = lean_timeline_event(event)
        assert result["type"] == "sprava"

    def test_no_timestamp(self):
        event = self._make_event(timestamp=None)
        result = lean_timeline_event(event)
        assert result["timestamp"] is None

    def test_no_author(self):
        event = self._make_event(author=None)
        result = lean_timeline_event(event)
        assert result["author"] is None

    def test_author_without_name(self):
        """Author is a plain string instead of object with .name."""
        event = self._make_event(author="System")
        result = lean_timeline_event(event)
        assert result["author"] == "System"

    def test_no_created_at(self):
        event = self._make_event(created_at=None)
        result = lean_timeline_event(event)
        assert result["created_at"] is None

    def test_event_date_absent_when_unparseable(self):
        """Plain text with no date yields no event_date key."""
        event = self._make_event(text="Do page 42")
        result = lean_timeline_event(event)
        assert "event_date" not in result

    def test_event_date_surfaced_from_title(self):
        event = self._make_event(
            event_type="event",
            text="Udalosť: Sommerfest -  15.06.2026",
        )
        result = lean_timeline_event(event)
        assert result["event_date"] == "2026-06-15"


# ---------------------------------------------------------------------------
# extract_homework_fields()
# ---------------------------------------------------------------------------


class TestExtractHomeworkFields:
    def _make_hw_event(self, additional_data=None, **overrides):
        class MockEventType:
            def __init__(self, val):
                self.value = val

        defaults = {
            "event_id": "hw1",
            "event_type": MockEventType("homework"),
            "timestamp": datetime(2025, 6, 15, 10, 0),
            "text": "Default text",
            "author": SimpleNamespace(name="Teacher"),
            "is_done": False,
            "is_starred": False,
            "created_at": datetime(2025, 6, 14, 8, 0),
            "additional_data": additional_data or {},
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_basic_homework(self):
        event = self._make_hw_event({"nazov": "Homework 1", "predmetNazov": "Math", "dateto": "2025-06-20"})
        result = extract_homework_fields(event)
        assert result["title"] == "Homework 1"
        assert result["subject"] == "Math"
        assert result["due_date"] == "2025-06-20"

    def test_fallback_title_from_text(self):
        event = self._make_hw_event({})
        result = extract_homework_fields(event)
        assert result["title"] == "Default text"

    def test_title_priority_nazov(self):
        event = self._make_hw_event({"nazov": "A", "title": "B", "name": "C"})
        result = extract_homework_fields(event)
        assert result["title"] == "A"

    def test_title_priority_title(self):
        event = self._make_hw_event({"title": "B", "name": "C"})
        result = extract_homework_fields(event)
        assert result["title"] == "B"

    def test_title_priority_name(self):
        event = self._make_hw_event({"name": "C"})
        result = extract_homework_fields(event)
        assert result["title"] == "C"

    def test_subject_fallback_chain(self):
        event = self._make_hw_event({"nazov_predmetu": "Slovak"})
        result = extract_homework_fields(event)
        assert result["subject"] == "Slovak"

    def test_subject_empty_fallback(self):
        event = self._make_hw_event({})
        result = extract_homework_fields(event)
        assert result["subject"] == ""

    def test_due_date_fallback_chain(self):
        event = self._make_hw_event({"date_to": "2025-07-01"})
        result = extract_homework_fields(event)
        assert result["due_date"] == "2025-07-01"

    def test_due_date_empty(self):
        event = self._make_hw_event({})
        result = extract_homework_fields(event)
        assert result["due_date"] == ""

    def test_includes_timeline_fields(self):
        event = self._make_hw_event({})
        result = extract_homework_fields(event)
        assert "event_id" in result
        assert "type" in result
        assert "timestamp" in result
        assert "is_done" in result

    def test_none_additional_data(self):
        event = self._make_hw_event(additional_data=None)
        result = extract_homework_fields(event)
        assert result["title"] == "Default text"
        assert result["subject"] == ""
        assert result["due_date"] == ""

    def test_list_additional_data(self):
        # Edupage sometimes returns a list here; it must not raise.
        event = self._make_hw_event(additional_data=["unexpected"])
        result = extract_homework_fields(event)
        assert result["title"] == "Default text"
        assert result["subject"] == ""
        assert result["due_date"] == ""


# ---------------------------------------------------------------------------
# extract_assignment_fields()
# ---------------------------------------------------------------------------


class TestExtractAssignmentFields:
    def _make_event(self, additional_data=None, **overrides):
        class MockEventType:
            def __init__(self, val):
                self.value = val

        defaults = {
            "event_id": "a1",
            "event_type": MockEventType("etesthw"),
            "timestamp": datetime(2025, 6, 15, 10, 0),
            "text": "Assignment text",
            "author": SimpleNamespace(name="Teacher"),
            "is_done": False,
            "is_starred": False,
            "created_at": datetime(2025, 6, 14, 8, 0),
            "additional_data": additional_data or {},
        }
        defaults.update(overrides)
        return SimpleNamespace(**defaults)

    def test_includes_homework_fields(self):
        event = self._make_event({"nazov": "Project 1", "predmetNazov": "Biology", "dateto": "2025-07-01"})
        result = extract_assignment_fields(event)
        assert result["title"] == "Project 1"
        assert result["subject"] == "Biology"
        assert result["due_date"] == "2025-07-01"

    def test_max_points(self):
        event = self._make_event({"maxPoints": 100})
        result = extract_assignment_fields(event)
        assert result["max_points"] == 100

    def test_max_points_fallback(self):
        event = self._make_event({"max_points": 50})
        result = extract_assignment_fields(event)
        assert result["max_points"] == 50

    def test_description_popis(self):
        event = self._make_event({"popis": "Detailed instructions"})
        result = extract_assignment_fields(event)
        assert result["description"] == "Detailed instructions"

    def test_description_fallback(self):
        event = self._make_event({"description": "English description"})
        result = extract_assignment_fields(event)
        assert result["description"] == "English description"

    def test_description_empty(self):
        event = self._make_event({})
        result = extract_assignment_fields(event)
        assert result["description"] == ""

    def test_max_points_none(self):
        event = self._make_event({})
        result = extract_assignment_fields(event)
        assert result["max_points"] is None
