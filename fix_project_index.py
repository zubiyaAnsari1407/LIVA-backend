from database import client, db

OLD_INDEX = "organization_id_1_source_key_1_reference_date_1"
NEW_INDEX = "unique_project_source_when_present"

try:
    # Create replacement first. If this fails, the old index stays intact.
    db.projects.create_index(
        [
            ("organization_id", 1),
            ("source_key", 1),
            ("reference_date", 1),
        ],
        name=NEW_INDEX,
        unique=True,
        partialFilterExpression={
            "organization_id": {"$exists": True},
            "source_key": {"$exists": True},
            "reference_date": {"$exists": True},
        },
    )

    if OLD_INDEX in db.projects.index_information():
        db.projects.drop_index(OLD_INDEX)

    print("Project index fixed successfully. Existing records preserved.")

finally:
    client.close()