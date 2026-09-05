from datetime import date
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel


class ReportSummary(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    sales_amount: Decimal
    sales_documents: int
    payments_amount: Decimal
    current_debt: Decimal
    warehouse_retail_value: Decimal
    representative_stock_retail_value: Decimal


class RepresentativeReportLine(BaseModel):
    representative_id: UUID
    representative_code: str
    representative_name: str
    sales_amount: Decimal
    sales_documents: int
    payments_amount: Decimal
    current_debt: Decimal
    stock_positions: int
    stock_retail_value: Decimal
