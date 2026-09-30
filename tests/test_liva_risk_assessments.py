import liva_risk_assessments


def test_risk_features_use_only_verified_officer_report_fields():
    grievances = [
        {
            "status": "PROBLEM_VERIFIED",
            "type": "ownership",
            "officerReport": {
                "ownershipIssueConfirmed": False,
                "surveyPending": True,
                "compensationPending": False,
                "workStatus": "IN_PROGRESS",
                "overdueDays": 12,
            },
        },
        {
            "status": "PROBLEM_VERIFIED",
            "type": "land-dispute",
            "officerReport": {
                "ownershipIssueConfirmed": True,
                "surveyPending": False,
                "compensationPending": True,
                "workStatus": "ON_HOLD",
                "overdueDays": 4,
            },
        },
        {
            "status": "SUBMITTED",
            "type": "compensation",
            "officerReport": {
                "surveyPending": True,
                "compensationPending": True,
                "workStatus": "IN_PROGRESS",
                "overdueDays": 90,
            },
        },
    ]

    features, availability = liva_risk_assessments.extract_verified_grievance_features(
        {"projectId": "LIVA-PRJ-017", "projectName": "Belsar Project"},
        grievances,
    )

    assert features.ownership_disputes == 1
    assert features.survey_pending == 1
    assert features.compensation_pending == 1
    assert features.open_actions == 2
    assert features.overdue_actions == 2
    assert features.max_overdue_days == 12
    assert availability["survey_pending"] is True
    assert availability["compensation_pending"] is True
    assert availability["open_actions"] is True
    assert availability["max_overdue_days"] is True
    assert availability["total_parcels"] is False
