from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import StreamingResponse
from fastapi.templating import Jinja2Templates
import fitz
import re
import io
import xml.etree.ElementTree as ET

app = FastAPI()

templates = Jinja2Templates(directory="templates")


def extract_transactions(pdf_bytes):
    transactions = []

    pdf = fitz.open(stream=pdf_bytes, filetype="pdf")

    for page in pdf:
        text = page.get_text()

        if not text:
            continue

        lines = text.split("\n")

        for line in lines:
            line = line.strip()

            date_match = re.search(
                r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
                line
            )

            if not date_match:
                continue

            amounts = re.findall(
                r"\b\d+(?:,\d{3})*(?:\.\d{1,2})?\b",
                line
            )

            if not amounts:
                continue

            try:
                amount = float(
                    amounts[-1].replace(",", "")
                )
            except ValueError:
                continue

            transactions.append({
                "date": date_match.group(1),
                "description": line,
                "amount": amount
            })

    pdf.close()

    return transactions


def format_date(date_string):
    numbers = re.findall(r"\d+", date_string)

    if len(numbers) != 3:
        return ""

    day = numbers[0].zfill(2)
    month = numbers[1].zfill(2)
    year = numbers[2]

    if len(year) == 2:
        year = "20" + year

    return year + month + day


def create_tally_xml(transactions):

    envelope = ET.Element("ENVELOPE")

    header = ET.SubElement(envelope, "HEADER")

    ET.SubElement(
        header,
        "TALLYREQUEST"
    ).text = "Import Data"

    body = ET.SubElement(envelope, "BODY")

    import_data = ET.SubElement(
        body,
        "IMPORTDATA"
    )

    request_desc = ET.SubElement(
        import_data,
        "REQUESTDESC"
    )

    ET.SubElement(
        request_desc,
        "REPORTNAME"
    ).text = "Vouchers"

    request_data = ET.SubElement(
        import_data,
        "REQUESTDATA"
    )

    for transaction in transactions:

        tally_message = ET.SubElement(
            request_data,
            "TALLYMESSAGE"
        )

        voucher = ET.SubElement(
            tally_message,
            "VOUCHER",
            {
                "VCHTYPE": "Receipt",
                "ACTION": "Create"
            }
        )

        ET.SubElement(
            voucher,
            "DATE"
        ).text = format_date(transaction["date"])

        ET.SubElement(
            voucher,
            "VOUCHERTYPENAME"
        ).text = "Receipt"

        ET.SubElement(
            voucher,
            "NARRATION"
        ).text = transaction["description"]

        ledger_entries = ET.SubElement(
            voucher,
            "ALLLEDGERENTRIES.LIST"
        )

        ET.SubElement(
            ledger_entries,
            "LEDGERNAME"
        ).text = "Bank"

        ET.SubElement(
            ledger_entries,
            "ISDEEMEDPOSITIVE"
        ).text = "No"

        ET.SubElement(
            ledger_entries,
            "AMOUNT"
        ).text = str(transaction["amount"])

    xml_data = ET.tostring(
        envelope,
        encoding="utf-8",
        xml_declaration=True
    )

    return xml_data


@app.get("/")
async def home(request: Request):

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request
        }
    )


@app.post("/")
async def convert_pdf(
    pdf_file: UploadFile = File(...)
):

    if not pdf_file.filename.lower().endswith(".pdf"):
        return {
            "error": "Please upload a PDF file only."
        }

    try:

        pdf_bytes = await pdf_file.read()

        transactions = extract_transactions(pdf_bytes)

        if not transactions:
            return {
                "error": "No transactions found in this PDF."
            }

        xml_data = create_tally_xml(transactions)

        return StreamingResponse(
            io.BytesIO(xml_data),
            media_type="application/xml",
            headers={
                "Content-Disposition":
                "attachment; filename=tally_import.xml"
            }
        )

    except Exception as e:

        return {
            "error": str(e)
        }
