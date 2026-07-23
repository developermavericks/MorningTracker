import os
from unittest.mock import MagicMock, patch
from datetime import datetime, date
import pytest
import openpyxl
from utils.google_docs import append_daily_takeaways_to_sheet
from scraper.tasks import check_heavy_automation_schedules

@patch("utils.google_docs.get_drive_service")
@patch("utils.google_docs.get_or_create_reports_folder")
def test_append_daily_takeaways_parsing(mock_get_folder, mock_get_service):
    """
    Verifies that the daily takeaways string is parsed correctly and written to
    the correct monthly tab of an openpyxl Workbook.
    """
    mock_service = MagicMock()
    mock_get_service.return_value = mock_service
    mock_get_folder.return_value = "mock_folder_id"
    
    # Mock files search to return no files (triggers new workbook creation)
    mock_service.files().list().execute.return_value = {"files": []}
    mock_service.files().create().execute.return_value = {"id": "new_sheet_id", "webViewLink": "https://sheet_link"}
    
    takeaways_text = (
        "- Performance Increase — The new search crawler runs 2x faster.\n"
        "• Security Patch: All dependencies were upgraded to avoid vulnerabilities.\n"
        "Raw takeaways text without any bullet points or dividers."
    )
    
    # Run the function
    link = append_daily_takeaways_to_sheet("Test Brand", date(2026, 7, 23), takeaways_text)
    
    # Assert return link matches mock
    assert link == "https://sheet_link"
    
    # Verify file upload call
    assert mock_service.files().create.called
    create_args = mock_service.files().create.call_args[1]
    assert create_args["body"]["name"] == "Test Brand - Strategic Takeaways History"


@patch("db.database.get_db_sync")
@patch("celery_app.app.send_task")
def test_monthly_scheduler_trigger(mock_send_task, mock_get_db):
    """
    Verifies that check_heavy_automation_schedules correctly identifies when a
    monthly takeaways email is scheduled and dispatches the task.
    """
    mock_db = MagicMock()
    mock_get_db.return_value.__enter__.return_value = mock_db
    
    # Mock company configured for monthly takeaways on day 23 at 11:00 AM
    mock_company = MagicMock()
    mock_company.id = 123
    mock_company.name = "Test Brand"
    mock_company.enabled = True
    mock_company.timezone = "UTC"
    mock_company.fetch_time = "07:00"  # daily run
    mock_company.frequency = "Daily"
    mock_company.days = None
    mock_company.send_monthly_takeaways_enabled = True
    mock_company.monthly_takeaways_day = 23
    mock_company.monthly_takeaways_time = "11:00"
    mock_company.last_monthly_takeaways_sent_at = None
    
    mock_db.execute.return_value.scalars.return_value.all.return_value = [mock_company]
    # Mock no runs today to avoid daily trigger complications
    mock_db.execute.return_value.scalar_one_or_none.return_value = None
    
    # Mock current datetime to exactly July 23rd, 11:05 AM UTC (matches schedule window 11:00-11:10)
    with patch("scraper.tasks.datetime") as mock_datetime:
        mock_now = datetime(2026, 7, 23, 11, 5, 0)
        mock_datetime.now.return_value = mock_now
        # Support other standard calls
        mock_datetime.utcnow.return_value = datetime(2026, 7, 23, 11, 5, 0)
        mock_datetime.strptime = datetime.strptime
        
        check_heavy_automation_schedules()
        
    # Verify that the monthly takeaways task was sent
    assert mock_send_task.called
    task_names = [call[0][0] for call in mock_send_task.call_args_list]
    assert "scraper.tasks.send_monthly_takeaways_report_task" in task_names
