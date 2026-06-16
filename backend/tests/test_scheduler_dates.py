import pytest
from datetime import date, timedelta

def calculate_search_dates(run_date: date) -> list:
    """Helper representing the logic we implemented in tasks.py"""
    search_dates = [run_date]
    if run_date.weekday() == 0:  # Monday
        search_dates.extend([
            run_date - timedelta(days=1),  # Sunday
            run_date - timedelta(days=2),  # Saturday
            run_date - timedelta(days=3)   # Friday
        ])
    else:
        search_dates.append(run_date - timedelta(days=1))
    return search_dates

def test_monday_consolidation():
    # Mocking a Monday (e.g., June 15, 2026 is a Monday)
    monday = date(2026, 6, 15)
    assert monday.weekday() == 0
    
    dates = calculate_search_dates(monday)
    assert len(dates) == 4
    assert dates[0] == date(2026, 6, 15)  # Monday
    assert dates[1] == date(2026, 6, 14)  # Sunday
    assert dates[2] == date(2026, 6, 13)  # Saturday
    assert dates[3] == date(2026, 6, 12)  # Friday

def test_regular_weekday_fallback():
    # Mocking a Tuesday (e.g., June 16, 2026 is a Tuesday)
    tuesday = date(2026, 6, 16)
    assert tuesday.weekday() == 1
    
    dates = calculate_search_dates(tuesday)
    assert len(dates) == 2
    assert dates[0] == date(2026, 6, 16)  # Tuesday
    assert dates[1] == date(2026, 6, 15)  # Monday
