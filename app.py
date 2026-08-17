from flask import Flask, render_template, request, send_file
import pdfplumber
import pandas as pd
import re
import io
import xml.etree.ElementTree as ET

app = Flask(__name__)


def extract_transactions(pdf_file):
    transactions = []

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()

            if not text:
                continue

            lines = text.split("\n")

            for line in lines:
                line = line.strip()

                # Try to identify rows containing dates and amounts
                date_match = re.search(
                    r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\b",
                    line
                )

                amounts = re.findall(
                    r"\b\d+(?:,\d{3})*(?:\.\d{2})?\b",
                    line
                )

                if date_match and amounts:
                    date = date_match.group(1)

                    try:
                        amount = float(
                            amounts[-1].replace(",", "")
                        )
                    except ValueError:
                        continue

                    transactions.append({
                        "date": date,
                        "description": line,
                        "amount": amount
                    })

    return transactions


def create_tally_xml(transactions):
    envelope = ET.Element("ENVELOPE")

    header = ET.SubElement(envelope, "HEADER")
    ET.SubElement(header, "TALLYREQUEST").text = "Import Data"

    body = ET.SubElement(envelope, "BODY")
    import_data = ET.SubElement(body, "IMPORTDATA")

    request_desc = ET.SubElement(import_data, "REQUESTDESC")
    ET.SubElement(request_desc, "REPORTNAME").text = "Vouchers"

    request_data = ET.SubElement(import_data, "REQUESTDATA")

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
        ).text = transaction["date"].replace("/", "")

        ET.SubElement(
            voucher,
            "VOUCHERTYPENAME"
        ).text = "Receipt"

        ET.SubElement(
            voucher,
            "NARRATION"
        ).text = transaction["description"]

        ET.SubElement(
            voucher,
            "AMOUNT"
        ).text = str(transaction["amount"])

    xml_data = ET.tostring(
        envelope,
        encoding="utf-8",
        xml_declaration=True
    )

    return xml_data


@app.route("/", methods=["GET", "POST"])
def index():

    if request.method == "POST":

        if "pdf_file" not in request.files:
            return "No PDF file uploaded."

        pdf_file = request.files["pdf_file"]

        if pdf_file.filename == "":
            return "Please select a PDF file."

        if not pdf_file.filename.lower().endswith(".pdf"):
            return "Only PDF files are allowed."

        try:
            transactions = extract_transactions(pdf_file)

            if not transactions:
                return (
                    "No transactions could be detected from this PDF. "
                    "The bank statement format may need to be configured."
                )

            xml_data = create_tally_xml(transactions)

            return send_file(
                io.BytesIO(xml_data),
                mimetype="application/xml",
                as_attachment=True,
                download_name="tally_import.xml"
            )

        except Exception as e:
            return f"Error processing PDF: {str(e)}"

    return render_template("index.html")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
