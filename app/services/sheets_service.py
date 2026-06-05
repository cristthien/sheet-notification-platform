"""
Google Sheets service — list spreadsheets, worksheets, and read row data.
"""

from typing import Optional
import gspread

from app.models.user import User
from app.services.google_service import get_gspread_client


async def list_spreadsheets(user: User) -> list[dict]:
    """List all Google Spreadsheets the user has access to."""
    gc = await get_gspread_client(user)
    files = gc.list_spreadsheet_files()
    return [
        {"id": f["id"], "name": f["name"]}
        for f in files
    ]


async def list_worksheets(user: User, spreadsheet_id: str) -> list[str]:
    """List all worksheet (tab) names in a spreadsheet."""
    gc = await get_gspread_client(user)
    spreadsheet = gc.open_by_key(spreadsheet_id)
    return [ws.title for ws in spreadsheet.worksheets()]


async def get_spreadsheet_name(user: User, spreadsheet_id: str) -> str:
    """Get the display name of a spreadsheet."""
    gc = await get_gspread_client(user)
    spreadsheet = gc.open_by_key(spreadsheet_id)
    return spreadsheet.title


async def get_all_records(
    user: User,
    spreadsheet_id: str,
    sheet_name: str,
) -> list[dict]:
    """
    Get all records from a worksheet.
    Assumes first row is the header row.
    Returns list of dicts: [{"Column A": "val", "Column B": "val"}, ...]
    """
    gc = await get_gspread_client(user)
    worksheet = gc.open_by_key(spreadsheet_id).worksheet(sheet_name)
    return worksheet.get_all_records()


async def get_current_row_count(
    user: User,
    spreadsheet_id: str,
    sheet_name: str,
) -> int:
    """Return the number of data rows (excluding header)."""
    records = await get_all_records(user, spreadsheet_id, sheet_name)
    return len(records)
