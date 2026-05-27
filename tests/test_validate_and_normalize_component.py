"""
Tests for Searcher._validate_and_normalize_component()

This method normalizes and validates calendar components before processing.
It should:
1. Accept Calendar, Component, or wrapped objects
2. Return a list of components (excluding Timezone components)
3. Validate that components are non-empty
4. Validate recurrence sets follow proper structure
"""

from datetime import datetime

import pytest
from icalendar import Calendar, Event, Timezone, Todo
from icalendar.prop import vRecur

from icalendar_searcher import Searcher


def test_validate_single_event_in_calendar() -> None:
    """Single event in a calendar should return a list with one event."""
    cal = Calendar()
    event = Event()
    event.add("uid", "event123")
    event.add("summary", "Test Event")
    event.add("dtstart", datetime(2025, 1, 15, 10, 0))
    cal.add_component(event)

    searcher = Searcher()
    result = searcher._validate_and_normalize_component(cal)

    assert isinstance(result, list), "Should return a list"
    assert len(result) == 1, "Should contain one component"
    assert result[0].name == "VEVENT", "Should be an event"
    assert result[0]["uid"] == "event123", "Should preserve UID"


def test_validate_single_todo_in_calendar() -> None:
    """Single todo in a calendar should return a list with one todo."""
    cal = Calendar()
    todo = Todo()
    todo.add("uid", "todo123")
    todo.add("summary", "Test Task")
    cal.add_component(todo)

    searcher = Searcher()
    result = searcher._validate_and_normalize_component(cal)

    assert isinstance(result, list), "Should return a list"
    assert len(result) == 1, "Should contain one component"
    assert result[0].name == "VTODO", "Should be a todo"
    assert result[0]["uid"] == "todo123", "Should preserve UID"


def test_validate_removes_timezone_components() -> None:
    """Timezone components should be filtered out from the result."""
    cal = Calendar()

    # Add timezone component
    tz = Timezone()
    tz.add("tzid", "America/New_York")
    cal.add_component(tz)

    # Add event
    event = Event()
    event.add("uid", "event123")
    event.add("summary", "Event with timezone")
    event.add("dtstart", datetime(2025, 1, 15, 10, 0))
    cal.add_component(event)

    searcher = Searcher()
    result = searcher._validate_and_normalize_component(cal)

    assert len(result) == 1, "Should contain only the event, not the timezone"
    assert result[0].name == "VEVENT", "Should be the event"
    assert all(not isinstance(c, Timezone) for c in result), (
        "No timezone components should be in result"
    )


def test_validate_empty_calendar_raises_error() -> None:
    """Empty calendar with no components should raise ValueError."""
    cal = Calendar()

    searcher = Searcher()

    with pytest.raises(ValueError, match="Empty component"):
        searcher._validate_and_normalize_component(cal)


def test_validate_calendar_with_only_timezone_raises_error() -> None:
    """Calendar with only timezone component should raise ValueError."""
    cal = Calendar()
    tz = Timezone()
    tz.add("tzid", "America/New_York")
    cal.add_component(tz)

    searcher = Searcher()

    with pytest.raises(ValueError, match="Empty component"):
        searcher._validate_and_normalize_component(cal)


def test_validate_valid_recurrence_set() -> None:
    """Valid recurrence set should return list with master and exceptions."""
    cal = Calendar()

    # Master event with RRULE
    master = Event()
    master.add("uid", "recurring-meeting")
    master.add("summary", "Weekly Meeting")
    master.add("dtstart", datetime(2025, 1, 6, 10, 0))
    master.add("dtend", datetime(2025, 1, 6, 11, 0))
    master.add("rrule", vRecur(FREQ="WEEKLY", COUNT=4))
    cal.add_component(master)

    # Exception event with RECURRENCE-ID
    exception = Event()
    exception.add("uid", "recurring-meeting")
    exception.add("summary", "Special Meeting")
    exception.add("dtstart", datetime(2025, 1, 13, 14, 0))
    exception.add("dtend", datetime(2025, 1, 13, 15, 0))
    exception.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    cal.add_component(exception)

    searcher = Searcher()
    result = searcher._validate_and_normalize_component(cal)

    assert len(result) == 2, "Should contain master and exception"
    assert result[0]["uid"] == "recurring-meeting", "Master should have correct UID"
    assert result[1]["uid"] == "recurring-meeting", "Exception should have same UID"
    assert "rrule" in result[0], "Master should have RRULE"
    assert "recurrence-id" in result[1], "Exception should have RECURRENCE-ID"


def test_validate_recurrence_set_with_multiple_exceptions() -> None:
    """Recurrence set with multiple exceptions should be valid."""
    cal = Calendar()

    # Master event
    master = Event()
    master.add("uid", "meeting")
    master.add("summary", "Daily Standup")
    master.add("dtstart", datetime(2025, 1, 6, 9, 0))
    master.add("dtend", datetime(2025, 1, 6, 9, 15))
    master.add("rrule", vRecur(FREQ="DAILY", COUNT=5))
    cal.add_component(master)

    # First exception
    exception1 = Event()
    exception1.add("uid", "meeting")
    exception1.add("summary", "Standup - Moved")
    exception1.add("dtstart", datetime(2025, 1, 7, 10, 0))
    exception1.add("dtend", datetime(2025, 1, 7, 10, 15))
    exception1.add("recurrence-id", datetime(2025, 1, 7, 9, 0))
    cal.add_component(exception1)

    # Second exception
    exception2 = Event()
    exception2.add("uid", "meeting")
    exception2.add("summary", "Standup - Cancelled")
    exception2.add("dtstart", datetime(2025, 1, 8, 9, 0))
    exception2.add("dtend", datetime(2025, 1, 8, 9, 0))
    exception2.add("recurrence-id", datetime(2025, 1, 8, 9, 0))
    cal.add_component(exception2)

    searcher = Searcher()
    result = searcher._validate_and_normalize_component(cal)

    assert len(result) == 3, "Should contain master and two exceptions"
    assert all(c["uid"] == "meeting" for c in result), "All should have same UID"
    assert "rrule" in result[0], "Master should have RRULE"
    assert "recurrence-id" in result[1], "First exception should have RECURRENCE-ID"
    assert "recurrence-id" in result[2], "Second exception should have RECURRENCE-ID"


def test_validate_multiple_different_uids_raises_error_first() -> None:
    """Calendar with multiple components having different UIDs raises ValueError.

    Note: The implementation checks for valid recurrence set structure before checking UIDs,
    so ValueError for invalid recurrence set is raised first.
    """
    cal = Calendar()

    event1 = Event()
    event1.add("uid", "event1")
    event1.add("summary", "First Event")
    event1.add("dtstart", datetime(2025, 1, 15, 10, 0))
    cal.add_component(event1)

    event2 = Event()
    event2.add("uid", "event2")  # Different UID
    event2.add("summary", "Second Event")
    event2.add("dtstart", datetime(2025, 1, 16, 10, 0))
    cal.add_component(event2)

    searcher = Searcher()

    # ValueError is raised because first component lacks RRULE
    # (before the UID check happens)
    with pytest.raises(ValueError, match="valid recurrence set"):
        searcher._validate_and_normalize_component(cal)


def test_validate_multiple_uids_with_rrule_raises_valueerror() -> None:
    """When first component has RRULE but components have different UIDs, ValueError is raised."""
    cal = Calendar()

    # First event with RRULE
    event1 = Event()
    event1.add("uid", "event1")
    event1.add("summary", "First Event")
    event1.add("dtstart", datetime(2025, 1, 15, 10, 0))
    event1.add("rrule", vRecur(FREQ="WEEKLY", COUNT=2))
    cal.add_component(event1)

    # Second event with different UID
    event2 = Event()
    event2.add("uid", "event2")  # Different UID
    event2.add("summary", "Second Event")
    event2.add("dtstart", datetime(2025, 1, 16, 10, 0))
    event2.add("recurrence-id", datetime(2025, 1, 16, 10, 0))
    cal.add_component(event2)

    searcher = Searcher()

    # Now ValueError is raised for multiple UIDs (after RRULE check passes)
    with pytest.raises(ValueError, match="multiple UIDs found"):
        searcher._validate_and_normalize_component(cal)


def test_validate_recurrence_set_master_without_rrule_raises_error() -> None:
    """Recurrence set where master lacks RRULE should raise ValueError."""
    cal = Calendar()

    # Master event WITHOUT RRULE (invalid)
    master = Event()
    master.add("uid", "meeting")
    master.add("summary", "Meeting")
    master.add("dtstart", datetime(2025, 1, 6, 10, 0))
    master.add("dtend", datetime(2025, 1, 6, 11, 0))
    # No RRULE added!
    cal.add_component(master)

    # Exception event
    exception = Event()
    exception.add("uid", "meeting")
    exception.add("summary", "Special Meeting")
    exception.add("dtstart", datetime(2025, 1, 13, 10, 0))
    exception.add("dtend", datetime(2025, 1, 13, 11, 0))
    exception.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    cal.add_component(exception)

    searcher = Searcher()

    with pytest.raises(ValueError, match="valid recurrence set"):
        searcher._validate_and_normalize_component(cal)


def test_validate_recurrence_exception_without_recurrence_id_raises_error() -> None:
    """Recurrence exception without RECURRENCE-ID should raise ValueError."""
    cal = Calendar()

    # Master event with RRULE
    master = Event()
    master.add("uid", "meeting")
    master.add("summary", "Weekly Meeting")
    master.add("dtstart", datetime(2025, 1, 6, 10, 0))
    master.add("dtend", datetime(2025, 1, 6, 11, 0))
    master.add("rrule", vRecur(FREQ="WEEKLY", COUNT=4))
    cal.add_component(master)

    # Exception event WITHOUT RECURRENCE-ID (invalid)
    exception = Event()
    exception.add("uid", "meeting")
    exception.add("summary", "Special Meeting")
    exception.add("dtstart", datetime(2025, 1, 13, 10, 0))
    exception.add("dtend", datetime(2025, 1, 13, 11, 0))
    # No RECURRENCE-ID added!
    cal.add_component(exception)

    searcher = Searcher()

    with pytest.raises(ValueError, match="valid recurrence set"):
        searcher._validate_and_normalize_component(cal)


def test_validate_recurrence_exception_with_rrule_raises_error() -> None:
    """Recurrence exception should not have RRULE, should raise ValueError."""
    cal = Calendar()

    # Master event with RRULE
    master = Event()
    master.add("uid", "meeting")
    master.add("summary", "Weekly Meeting")
    master.add("dtstart", datetime(2025, 1, 6, 10, 0))
    master.add("dtend", datetime(2025, 1, 6, 11, 0))
    master.add("rrule", vRecur(FREQ="WEEKLY", COUNT=4))
    cal.add_component(master)

    # Exception event WITH RRULE (invalid - exceptions shouldn't have RRULE)
    exception = Event()
    exception.add("uid", "meeting")
    exception.add("summary", "Special Meeting")
    exception.add("dtstart", datetime(2025, 1, 13, 10, 0))
    exception.add("dtend", datetime(2025, 1, 13, 11, 0))
    exception.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    exception.add("rrule", vRecur(FREQ="WEEKLY", COUNT=2))  # Invalid!
    cal.add_component(exception)

    searcher = Searcher()

    with pytest.raises(ValueError, match="valid recurrence set"):
        searcher._validate_and_normalize_component(cal)


def test_validate_preserves_component_properties() -> None:
    """All component properties should be preserved in the result."""
    cal = Calendar()
    event = Event()
    event.add("uid", "event123")
    event.add("summary", "Important Meeting")
    event.add("location", "Conference Room A")
    event.add("description", "Quarterly planning meeting")
    event.add("dtstart", datetime(2025, 1, 15, 10, 0))
    event.add("dtend", datetime(2025, 1, 15, 12, 0))
    event.add("status", "CONFIRMED")
    cal.add_component(event)

    searcher = Searcher()
    result = searcher._validate_and_normalize_component(cal)

    assert result[0]["summary"] == "Important Meeting"
    assert result[0]["location"] == "Conference Room A"
    assert result[0]["description"] == "Quarterly planning meeting"
    assert result[0]["status"] == "CONFIRMED"


def test_validate_component_instead_of_calendar() -> None:
    """Direct component (not wrapped in Calendar) should be normalized to list."""
    event = Event()
    event.add("uid", "event123")
    event.add("summary", "Direct Event")
    event.add("dtstart", datetime(2025, 1, 15, 10, 0))

    searcher = Searcher()
    # _unwrap will convert Component to Calendar
    result = searcher._validate_and_normalize_component(event)

    assert isinstance(result, list), "Should return a list"
    assert len(result) == 1, "Should contain one component"
    assert result[0]["uid"] == "event123"


def test_validate_mixed_component_types_different_uids_raises_error() -> None:
    """Calendar with event and todo having different UIDs raises ValueError.

    Note: Similar to previous test, ValueError is raised before UID check.
    """
    cal = Calendar()

    event = Event()
    event.add("uid", "event1")
    event.add("summary", "Meeting")
    event.add("dtstart", datetime(2025, 1, 15, 10, 0))
    cal.add_component(event)

    todo = Todo()
    todo.add("uid", "todo1")  # Different UID
    todo.add("summary", "Task")
    cal.add_component(todo)

    searcher = Searcher()

    # ValueError is raised because first component lacks RRULE
    with pytest.raises(ValueError, match="valid recurrence set"):
        searcher._validate_and_normalize_component(cal)


def test_validate_all_same_component_type_same_uid_without_recurrence() -> None:
    """Multiple events with same UID but no RRULE should be treated as recurrence set (validation fails)."""
    cal = Calendar()

    # First event (no RRULE, so it's not a valid master)
    event1 = Event()
    event1.add("uid", "shared-uid")
    event1.add("summary", "Event 1")
    event1.add("dtstart", datetime(2025, 1, 15, 10, 0))
    cal.add_component(event1)

    # Second event with same UID
    event2 = Event()
    event2.add("uid", "shared-uid")
    event2.add("summary", "Event 2")
    event2.add("dtstart", datetime(2025, 1, 16, 10, 0))
    event2.add("recurrence-id", datetime(2025, 1, 16, 10, 0))
    cal.add_component(event2)

    searcher = Searcher()

    # This should raise ValueError because first component lacks RRULE
    with pytest.raises(ValueError, match="valid recurrence set"):
        searcher._validate_and_normalize_component(cal)


def test_validate_recurrence_set_master_after_exception() -> None:
    """Master may appear after the exception in the VCALENDAR.

    RFC 5545 does not mandate any particular ordering of VEVENT components
    inside a VCALENDAR.  Some CalDAV servers (notably ``calendar.mail.ru``)
    return overrides before the master in the .ics they hand out, which used
    to make ``_validate_and_normalize_component`` raise.  The normalized list
    must put the master first so that the downstream expansion code can rely
    on ``components[0]`` being the master.
    """
    cal = Calendar()

    # Exception event first (mail.ru-style ordering)
    exception = Event()
    exception.add("uid", "recurring-meeting")
    exception.add("summary", "Special Meeting")
    exception.add("dtstart", datetime(2025, 1, 13, 14, 0))
    exception.add("dtend", datetime(2025, 1, 13, 15, 0))
    exception.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    cal.add_component(exception)

    # Master event with RRULE last
    master = Event()
    master.add("uid", "recurring-meeting")
    master.add("summary", "Weekly Meeting")
    master.add("dtstart", datetime(2025, 1, 6, 10, 0))
    master.add("dtend", datetime(2025, 1, 6, 11, 0))
    master.add("rrule", vRecur(FREQ="WEEKLY", COUNT=4))
    cal.add_component(master)

    searcher = Searcher()
    result = searcher._validate_and_normalize_component(cal)

    assert len(result) == 2, "Should contain master and exception"
    assert "rrule" in result[0], "Master must be reordered to position 0"
    assert "recurrence-id" not in result[0], "Master must not carry RECURRENCE-ID"
    assert "recurrence-id" in result[1], "Exception must follow the master"
    assert "rrule" not in result[1], "Exception must not carry RRULE"


def test_validate_recurrence_set_master_in_middle() -> None:
    """Master may appear between exceptions in arbitrary order."""
    cal = Calendar()

    exception1 = Event()
    exception1.add("uid", "meeting")
    exception1.add("summary", "First override")
    exception1.add("dtstart", datetime(2025, 1, 13, 14, 0))
    exception1.add("dtend", datetime(2025, 1, 13, 15, 0))
    exception1.add("recurrence-id", datetime(2025, 1, 13, 10, 0))
    cal.add_component(exception1)

    master = Event()
    master.add("uid", "meeting")
    master.add("summary", "Weekly Meeting")
    master.add("dtstart", datetime(2025, 1, 6, 10, 0))
    master.add("dtend", datetime(2025, 1, 6, 11, 0))
    master.add("rrule", vRecur(FREQ="WEEKLY", COUNT=10))
    cal.add_component(master)

    exception2 = Event()
    exception2.add("uid", "meeting")
    exception2.add("summary", "Second override")
    exception2.add("dtstart", datetime(2025, 1, 20, 14, 0))
    exception2.add("dtend", datetime(2025, 1, 20, 15, 0))
    exception2.add("recurrence-id", datetime(2025, 1, 20, 10, 0))
    cal.add_component(exception2)

    searcher = Searcher()
    result = searcher._validate_and_normalize_component(cal)

    assert len(result) == 3, "Should contain master and both exceptions"
    assert "rrule" in result[0], "Master must be reordered to position 0"
    assert all("recurrence-id" in c for c in result[1:]), (
        "All non-master components must carry RECURRENCE-ID"
    )


def test_validate_recurrence_set_two_masters_rejected() -> None:
    """Two VEVENTs both carrying RRULE must be rejected as invalid."""
    cal = Calendar()

    master1 = Event()
    master1.add("uid", "meeting")
    master1.add("summary", "Weekly Meeting A")
    master1.add("dtstart", datetime(2025, 1, 6, 10, 0))
    master1.add("dtend", datetime(2025, 1, 6, 11, 0))
    master1.add("rrule", vRecur(FREQ="WEEKLY", COUNT=4))
    cal.add_component(master1)

    master2 = Event()
    master2.add("uid", "meeting")
    master2.add("summary", "Weekly Meeting B")
    master2.add("dtstart", datetime(2025, 1, 7, 10, 0))
    master2.add("dtend", datetime(2025, 1, 7, 11, 0))
    master2.add("rrule", vRecur(FREQ="DAILY", COUNT=4))
    cal.add_component(master2)

    searcher = Searcher()
    with pytest.raises(ValueError, match="valid recurrence set"):
        searcher._validate_and_normalize_component(cal)
