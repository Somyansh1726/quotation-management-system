# Quotation Management System

A Flask-based quotation management web application built as a portfolio demonstration of backend development, relational data storage, and dynamic document workflows.

## Features

- Company registration and business details
- Customer and product data entry
- Dynamic quotation creation with multiple line items
- GST calculations (intra-state CGST/SGST and inter-state IGST)
- Live quotation preview
- PDF export using an installed Google Chrome browser
- Quotation retrieval and revision workflow
- Company-scoped quotation data and uploaded-file access
- Password hashing for newly registered demo accounts

## Technology

- Python 3.10+
- Flask
- SQLite
- HTML, CSS, and JavaScript
- Pillow for optional logo processing

## Run locally

1. Install Python 3.10 or newer.
2. Open a terminal in the project folder.
3. Create and activate a virtual environment.
4. Install dependencies with `pip install -r requirements.txt`.
5. Set a persistent Flask secret key in the environment (recommended):
   - PowerShell: `$env:FLASK_SECRET_KEY = [guid]::NewGuid().ToString() + [guid]::NewGuid().ToString()`
   - Command Prompt: `set FLASK_SECRET_KEY=replace-with-a-long-random-value`
6. Run `python app.py`. The application initializes a local SQLite database on startup.
7. Open the local URL printed by Flask.

PDF generation expects Google Chrome at `C:\Program Files\Google\Chrome\Application\chrome.exe`. If Chrome is installed elsewhere, update `chrome_path` in `app.py`.

## Repository safety

This public portfolio copy excludes databases, uploaded client documents, and client-branded image assets. It uses a fresh local database and is intended for demonstration and code review, not as a production deployment. Before production use, add a complete authentication flow, CSRF protection, stricter upload validation, production configuration, and deployment-specific security review.

## Project context

The application demonstrates a business quotation workflow: collecting company and customer details, managing line items, calculating taxes, previewing quotations, and exporting PDFs. Real client records and confidential attachments are not included in this repository.
