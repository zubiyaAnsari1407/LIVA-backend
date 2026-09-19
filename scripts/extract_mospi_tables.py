from pathlib import Path

import pandas as pd
import pdfplumber


BASE_DIR = Path(__file__).resolve().parents[1]

PDF_FILE = (
    BASE_DIR
    / "data"
    / "raw"
    / "mospi_flash_report_march_2026.pdf"
)

OUTPUT_FILE = (
    BASE_DIR
    / "data"
    / "processed"
    / "mospi_march_2026_extracted_tables.csv"
)


def clean_cell(value):
    if value is None:
        return ""

    return (
        str(value)
        .replace("\n", " ")
        .strip()
    )


def extract_tables():
    if not PDF_FILE.exists():
        raise FileNotFoundError(
            f"MoSPI PDF not found:\n{PDF_FILE}"
        )

    all_rows = []

    total_tables = 0

    print("\n==============================")
    print("LIVA MOSPI TABLE EXTRACTOR")
    print("==============================")

    with pdfplumber.open(
        PDF_FILE
    ) as pdf:

        print(
            "\nPDF pages:",
            len(pdf.pages),
        )

        for page_number, page in enumerate(
            pdf.pages,
            start=1,
        ):
            tables = page.extract_tables()

            if not tables:
                continue

            for table_number, table in enumerate(
                tables,
                start=1,
            ):
                total_tables += 1

                for row_number, row in enumerate(
                    table,
                    start=1,
                ):
                    if not row:
                        continue

                    cleaned = [
                        clean_cell(value)
                        for value in row
                    ]

                    if not any(cleaned):
                        continue

                    record = {
                        "page_number":
                            page_number,

                        "table_number":
                            table_number,

                        "row_number":
                            row_number,
                    }

                    for index, value in enumerate(
                        cleaned
                    ):
                        record[
                            f"column_{index}"
                        ] = value

                    all_rows.append(
                        record
                    )

    if not all_rows:
        raise ValueError(
            "No tables could be extracted "
            "from the official MoSPI PDF."
        )

    df = pd.DataFrame(
        all_rows
    )

    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    df.to_csv(
        OUTPUT_FILE,
        index=False,
    )

    print(
        "\nTables detected:",
        total_tables,
    )

    print(
        "Extracted table rows:",
        len(df),
    )

    print(
        "\nSaved:",
        OUTPUT_FILE,
    )

    print(
        "\nFirst 25 extracted rows:\n"
    )

    pd.set_option(
        "display.max_columns",
        None,
    )

    pd.set_option(
        "display.width",
        250,
    )

    print(
        df.head(25).to_string(
            index=False
        )
    )


if __name__ == "__main__":
    extract_tables()