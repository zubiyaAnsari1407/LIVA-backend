from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    model_validator,
)


class LinkedRecord(BaseModel):
    model_config = ConfigDict(
        str_strip_whitespace=True,
        extra="forbid",
    )

    projectId: str
    parcelId: str | None = None
    isDemo: bool = True

    sourceName: str | None = Field(
        default=None,
        max_length=200,
    )
    sourceUrl: HttpUrl | None = None
    notes: str = Field(default="", max_length=5000)

class CompensationInput(LinkedRecord):
    reference: str = Field(
        min_length=2,
        max_length=120,
    )
    beneficiaryReference: str = Field(
        min_length=2,
        max_length=150,
    )

    approved: Decimal = Field(
        ge=0,
        max_digits=14,
        decimal_places=2,
        allow_inf_nan=False,
    )
    disbursed: Decimal = Field(
        ge=0,
        max_digits=14,
        decimal_places=2,
        allow_inf_nan=False,
    )

    officer: str = Field(default="", max_length=150)
    lastPaymentDate: date | None = None

    @model_validator(mode="after")
    def valid_payment(self):
        if self.disbursed > self.approved:
            raise ValueError(
                "Paid amount cannot exceed the approved amount."
            )

        if self.disbursed > 0 and self.lastPaymentDate is None:
            raise ValueError(
                "Enter the last payment date when paid amount is positive."
            )

        if self.disbursed == 0 and self.lastPaymentDate is not None:
            raise ValueError(
                "Clear the payment date when paid amount is zero."
            )

        return self


class ActionInput(LinkedRecord):
    title: str = Field(min_length=3, max_length=200)
    officer: str = Field(min_length=2, max_length=150)

    status: Literal[
        "Open",
        "In progress",
        "Blocked",
        "Completed",
    ] = "Open"

    priority: Literal[
        "Low",
        "Medium",
        "High",
    ] = "Medium"

    dueDate: date | None = None


class RehabilitationInput(LinkedRecord):
    familyReference: str = Field(
        min_length=2,
        max_length=150,
    )
    milestone: str = Field(
        min_length=3,
        max_length=200,
    )

    status: Literal[
        "Assessment",
        "Under review",
        "Approved",
        "Delivered",
        "Closed",
    ] = "Assessment"

    officer: str = Field(default="", max_length=150)
    targetDate: date | None = None
