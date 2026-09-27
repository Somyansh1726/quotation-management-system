from flask import Flask, render_template, request, jsonify, redirect, url_for, session, send_file, send_from_directory
import sqlite3
import os
import json
import shutil
import subprocess
import tempfile
from datetime import datetime, date
from io import BytesIO
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

try:
    from PIL import Image, ImageChops
    PILLOW_AVAILABLE = True
except ImportError:
    PILLOW_AVAILABLE = False

UPLOAD_FOLDER = "uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

LOGO_FOLDER = os.path.join("static", "logos")
os.makedirs(LOGO_FOLDER, exist_ok=True)

app = Flask(__name__)
# Needed by Flask to securely sign the session cookie
# Set FLASK_SECRET_KEY to a long random value for persistent sessions.
# The random fallback is suitable only for local portfolio/demo use.
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or os.urandom(32)


def _pdf_token_serializer():
    return URLSafeTimedSerializer(app.secret_key, salt="quotation-pdf-preview")


def _quotation_access_allowed(quotation_id, quotation):
    """Allow the owning company session, or a short-lived PDF render token."""
    session_company_id = session.get("company_id")
    quotation_company_id = int(quotation.get("company_id") or 0)
    if session_company_id is not None:
        return int(session_company_id) == quotation_company_id

    token = request.args.get("pdf_token")
    if not token:
        return False
    try:
        payload = _pdf_token_serializer().loads(token, max_age=120)
    except (BadSignature, SignatureExpired, TypeError, ValueError):
        return False
    return (
        int(payload.get("quotation_id", -1)) == int(quotation_id)
        and int(payload.get("company_id", -1)) == quotation_company_id
    )


# ---------------------------------------------------
# DATABASE SETUP
# Runs once at startup and creates the table if it does not exist yet
# ---------------------------------------------------
def init_db():
    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotationDate TEXT,
            quotationExpiry TEXT,
            quotationNumber TEXT,
            states TEXT,
            paymentMethod TEXT,
            salespersonName TEXT,
            totalAmount TEXT,
            customerName TEXT,
            billingAddress TEXT,
            shippingAddress TEXT,
            companyName TEXT,
            companyAddress TEXT,
            statesCustomer TEXT,
            customerGst TEXT,
            email TEXT,
            phoneNo TEXT,
            paymentTerms TEXT,
            warrantyTerm TEXT,
            termsData TEXT,
            uploadedFiles TEXT,
            company_id INTEGER,
            FOREIGN KEY (company_id) REFERENCES companies (id)
        )
    """)

    # Migration safety-net: if an older database.db already exists without
    # the customerGst column, add it here instead of failing silently
    try:
        cursor.execute("ALTER TABLE quotations ADD COLUMN customerGst TEXT")
    except sqlite3.OperationalError:
        pass  # column already exists

    # Each quotation can now have multiple line items, so each item is
    # its own row here, linked back to its quotation via quotation_id
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quotation_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            quotation_id INTEGER,
            itemName TEXT,
            modelNo TEXT,
            specifications TEXT,
            itemQuantity TEXT,
            unitPrice TEXT,
            lineTotal TEXT,
            FOREIGN KEY (quotation_id) REFERENCES quotations (id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS companies (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            company_name TEXT,
            company_code TEXT,
            gst_number TEXT,
            branch_address TEXT,
            email TEXT,
            mobile_number TEXT,
            password_hash TEXT,
            account_name TEXT,
            account_number TEXT,
            ifsc_code TEXT,
            upi_id TEXT,
            logo_path TEXT
        )
    """)

    conn.commit()
    conn.close()


# ---------------------------------------------------
# Auto-trims empty margins around an uploaded company logo, whether
# the source file has a transparent background (PNG with alpha) or
# a plain white/solid background baked in. This keeps the logo box
# in the quotation looking consistent and tight regardless of how
# much whitespace the original logo file happened to contain -
# whether a company uploads a large logo or a small one.
# ---------------------------------------------------
# ---------------------------------------------------
# Makes the background of an uploaded logo transparent, so it blends
# cleanly onto the navy banner regardless of the file format (JPG
# logos, for example, can never have real transparency baked in).
#
# Instead of removing every pixel that matches the background color
# (which could accidentally punch holes through white areas that are
# actually part of the logo artwork - like a white collar or text),
# this flood-fills starting only from the image's outer edges. So it
# only clears background that is connected to the border, leaving
# any enclosed light-colored details inside the logo untouched.
#
# Returns the path of the resulting PNG (JPGs are converted to PNG,
# since PNG is what supports transparency).
# ---------------------------------------------------
def make_logo_background_transparent(image_path):
    if not PILLOW_AVAILABLE:
        return image_path

    try:
        from collections import deque

        img = Image.open(image_path).convert("RGBA")
        width, height = img.size
        pixels = img.load()

        # Estimate the background color by averaging the four corners
        corners = [pixels[0, 0], pixels[width - 1, 0], pixels[0, height - 1], pixels[width - 1, height - 1]]
        bg_r = sum(c[0] for c in corners) / 4
        bg_g = sum(c[1] for c in corners) / 4
        bg_b = sum(c[2] for c in corners) / 4

        # Two thresholds instead of one hard cutoff: pixels within
        # min_thresh of the background color become fully transparent,
        # pixels beyond max_thresh stay fully opaque, and anything in
        # between (the anti-aliased blend at the circle's edge) gets a
        # smooth partial alpha. A single hard threshold left a jagged,
        # speckled ring around curved edges - this feathering avoids that.
        min_thresh = 15
        max_thresh = 55

        def color_distance(px):
            return max(abs(px[0] - bg_r), abs(px[1] - bg_g), abs(px[2] - bg_b))

        visited = bytearray(width * height)
        queue = deque()

        # Seed the flood-fill with every border pixel within the outer threshold
        for x in range(width):
            for y in (0, height - 1):
                idx = y * width + x
                if not visited[idx] and color_distance(pixels[x, y]) <= max_thresh:
                    visited[idx] = 1
                    queue.append((x, y))
        for y in range(height):
            for x in (0, width - 1):
                idx = y * width + x
                if not visited[idx] and color_distance(pixels[x, y]) <= max_thresh:
                    visited[idx] = 1
                    queue.append((x, y))

        region = []
        while queue:
            x, y = queue.popleft()
            region.append((x, y))
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and 0 <= ny < height:
                    nidx = ny * width + nx
                    if not visited[nidx] and color_distance(pixels[nx, ny]) <= max_thresh:
                        visited[nidx] = 1
                        queue.append((nx, ny))

        # Apply a smooth alpha ramp across the flood-filled region instead
        # of a hard 0/255 cutoff
        for (x, y) in region:
            r, g, b, _a = pixels[x, y]
            d = color_distance((r, g, b))
            if d <= min_thresh:
                alpha = 0
            else:
                frac = (d - min_thresh) / (max_thresh - min_thresh)
                alpha = int(255 * min(max(frac, 0), 1))
            pixels[x, y] = (r, g, b, alpha)

        # Always save as PNG, since that's what preserves the new transparency
        new_path = os.path.splitext(image_path)[0] + ".png"
        img.save(new_path)
        if new_path != image_path and os.path.exists(image_path):
            os.remove(image_path)
        return new_path
    except Exception:
        # If background removal fails for any reason, keep the original file
        return image_path


def trim_logo_whitespace(image_path):
    if not PILLOW_AVAILABLE:
        return

    try:
        img = Image.open(image_path).convert("RGBA")
        alpha = img.split()[-1]

        if alpha.getextrema() != (255, 255):
            # Image actually has transparent pixels - use the alpha
            # channel to find where the real content is
            bbox = alpha.getbbox()
        else:
            # Fully opaque image - assume the top-left corner pixel
            # is the background color, and trim anything matching it.
            # A plain exact-equality diff leaves JPEG compression noise
            # (background pixels that are off by only a few values from
            # the corner sample) counted as "content", so the crop box
            # ends up covering almost the whole image and the white
            # margin around the logo never actually gets trimmed -
            # this is what shows up as an unwanted white box behind the
            # logo. Binarizing the diff against a small tolerance fixes
            # that while still leaving real, higher-contrast logo
            # artwork untouched.
            bg_color = img.getpixel((0, 0))
            background = Image.new("RGBA", img.size, bg_color)
            diff = ImageChops.difference(img, background).convert("L")
            tolerance = 24
            diff = diff.point(lambda p: 255 if p > tolerance else 0)
            bbox = diff.getbbox()

        if bbox:
            # Keep a small breathing-room padding around the trimmed logo
            padding = 6
            left = max(bbox[0] - padding, 0)
            top = max(bbox[1] - padding, 0)
            right = min(bbox[2] + padding, img.width)
            bottom = min(bbox[3] + padding, img.height)
            img = img.crop((left, top, right, bottom))
            img.save(image_path)
    except Exception:
        # If trimming fails for any reason (corrupt file, unusual
        # format, etc.), just keep the original logo as-is
        pass


# ---------------------------------------------------
# Converts a rupee amount into its written-out English words
# (Indian numbering system), e.g. 73597 -> "Rupees Seventy Three
# Thousand Five Hundred and Ninety Seven Only"
# ---------------------------------------------------
def amount_to_words(amount):
    amount = round(float(amount or 0), 2)
    rupees = int(amount)
    paise = int(round((amount - rupees) * 100))

    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def two_digit(n):
        if n < 20:
            return ones[n]
        return tens[n // 10] + (" " + ones[n % 10] if n % 10 else "")

    def three_digit(n):
        if n >= 100:
            return ones[n // 100] + " Hundred" + (" and " + two_digit(n % 100) if n % 100 else "")
        return two_digit(n)

    def whole_number_to_words(n):
        if n == 0:
            return "Zero"
        parts = []
        crore, n = divmod(n, 10000000)
        lakh, n = divmod(n, 100000)
        thousand, n = divmod(n, 1000)
        hundred = n

        if crore:
            parts.append(three_digit(crore) + " Crore")
        if lakh:
            parts.append(three_digit(lakh) + " Lakh")
        if thousand:
            parts.append(three_digit(thousand) + " Thousand")
        if hundred:
            parts.append(three_digit(hundred))

        return " ".join(parts)

    words = "Rupees " + whole_number_to_words(rupees)
    if paise:
        words += " and " + whole_number_to_words(paise) + " Paise"
    words += " Only"
    return words



def generate_quotation_number(company_id):
    """
    Generates the next NEW quotation number globally.

    New quotations use a single global sequence:
        QT000001
        QT000002
        QT000003
        ...

    Revision quotations such as QT000001A, QT000001B, etc.
    are ignored when calculating the next NEW quotation number.

    The company_id parameter is kept so the existing function calls
    in the application do not need to change.
    """

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT quotationNumber
        FROM quotations
        WHERE quotationNumber IS NOT NULL
    """)

    rows = cursor.fetchall()
    conn.close()

    highest_number = 0

    for row in rows:
        quotation_number = str(row[0]).strip()

        # A normal quotation must look exactly like:
        # QT000001
        # QT000002
        # QT000123
        #
        # Revision numbers such as QT000001A are ignored.
        if (
            quotation_number.startswith("QT")
            and len(quotation_number) == 8
            and quotation_number[2:].isdigit()
        ):
            try:
                number = int(quotation_number[2:])

                if number > highest_number:
                    highest_number = number

            except ValueError:
                continue

    next_number = highest_number + 1

    return f"QT{next_number:06d}"

def generate_revision_number(company_id, base_quotation_number):
    """
    Generates the next revision number for an existing quotation.

    Example:
        QT000001
        QT000001A
        QT000001B
        QT000001C
    """

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT quotationNumber
        FROM quotations
        WHERE company_id = ?
          AND quotationNumber LIKE ?
    """, (
        company_id,
        f"{base_quotation_number}%"
    ))

    existing_numbers = [row[0] for row in cursor.fetchall()]
    conn.close()

    revision_letters = []

    for number in existing_numbers:
        if number.startswith(base_quotation_number):
            suffix = number[len(base_quotation_number):]

            # Only accept single-letter revisions: A, B, C...
            if len(suffix) == 1 and suffix.isalpha():
                revision_letters.append(suffix.upper())

    if not revision_letters:
        next_letter = "A"
    else:
        highest = max(ord(letter) for letter in revision_letters)

        if highest >= ord("Z"):
            raise ValueError("Maximum quotation revisions (A-Z) reached.")

        next_letter = chr(highest + 1)

    return f"{base_quotation_number}{next_letter}"




# ---------------------------------------------------
# ROUTE: SIGNUP / COMPANY REGISTRATION (signup.html)
# This is the entry point of the app. Saves the company + bank
# details, then redirects to the quotation form once the account
# is created
# ---------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        company_name = request.form.get("company_name")
        company_code = request.form.get("company_code")
        gst_number = request.form.get("gst_number")
        branch_address = request.form.get("branch_address")
        email = request.form.get("email")
        mobile_number = request.form.get("mobile_number")
        password = request.form.get("password", "")
        password_hash = generate_password_hash(password) if password else ""

        account_name = request.form.get("account_name")
        account_number = request.form.get("account_number")
        ifsc_code = request.form.get("ifsc_code")
        upi_id = request.form.get("upi_id")

        # Save the company logo (if one was uploaded) to the static/logos
        # folder, so it can be displayed later via a normal image URL
        logo_path = None
        logo_file = request.files.get("company_logo")
        if logo_file and logo_file.filename:
            safe_name = secure_filename(logo_file.filename)
            # Prefix with company_code so logos from different companies
            # don't overwrite each other
            unique_name = f"{company_code}_{safe_name}"
            saved_path = os.path.join(LOGO_FOLDER, unique_name)
            logo_file.save(saved_path)

            # Remove the logo's background (works even for JPGs, which
            # can never have real transparency) and trim leftover
            # whitespace, so it blends cleanly onto the navy banner
            final_path = make_logo_background_transparent(saved_path)
            trim_logo_whitespace(final_path)
            logo_path = f"logos/{os.path.basename(final_path)}"

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO companies (
                company_name, company_code, gst_number, branch_address,
                email, mobile_number, password_hash, account_name,
                account_number, ifsc_code, upi_id, logo_path
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            company_name, company_code, gst_number, branch_address,
            email, mobile_number, password_hash, account_name,
            account_number, ifsc_code, upi_id, logo_path
        ))
        conn.commit()

        # Remember which company this browser session belongs to,
        # so quotations created next can be linked back to it
        new_company_id = cursor.lastrowid
        session["company_id"] = new_company_id
        session["company_name"] = company_name

        conn.close()

        # Account created -> send the user to the quotation form
        return redirect(url_for("quotation_form"))

    return render_template("signup.html")


# ---------------------------------------------------
# ROUTE: QUOTATION FORM (index.html)
# Opens after a successful signup. Handles form submission and
# saves the data into the database
# ---------------------------------------------------
@app.route("/quotation-form", methods=["GET", "POST"])
def quotation_form():
    # Only a logged-in / just-signed-up company can access this page
    if "company_id" not in session:
        return redirect(url_for("signup"))

    company_id = session["company_id"]

    if request.method == "POST":
        quotationDate = request.form.get("quotationDate")
        quotationExpiry = request.form.get("quotationExpiry")
        quotationNumber = request.form.get("quotationNumber")
        states = request.form.get("states")
        paymentMethod = request.form.get("paymentMethod")
        salespersonName = request.form.get("salespersonName")

        customerName = request.form.get("customerName")
        billingAddress = request.form.get("billingAddress")
        shippingAddress = request.form.get("shippingAddress")
        companyName = request.form.get("companyName")
        companyAddress = request.form.get("companyAddress")
        statesCustomer = request.form.get("statesCustomer")
        customerGst = request.form.get("customerGst")
        email = request.form.get("email")
        phoneNo = request.form.get("phoneNo")

        paymentTerms = request.form.get("payment-terms")
        warrantyTerm = request.form.get("warranty-term")
        termsData = request.form.get("termsData")

        # ---- Collect multiple items (array-style fields from the form) ----
        item_names = request.form.getlist("itemName[]")
        item_models = request.form.getlist("modelNo[]")
        item_specs = request.form.getlist("specifications[]")
        item_quantities = request.form.getlist("itemQuantity[]")
        item_prices = request.form.getlist("unitPrice[]")

        items_to_save = []
        total_count = max(
            len(item_names), len(item_models), len(item_specs),
            len(item_quantities), len(item_prices)
        )

        for i in range(total_count):
            name = item_names[i].strip() if i < len(item_names) else ""
            model = item_models[i].strip() if i < len(item_models) else ""
            specs = item_specs[i].strip() if i < len(item_specs) else ""
            qty_raw = item_quantities[i].strip() if i < len(item_quantities) else ""
            price_raw = item_prices[i].strip() if i < len(item_prices) else ""

            # Skip rows the user left completely empty
            if not name and not model and not specs and not qty_raw and not price_raw:
                continue

            try:
                qty = float(qty_raw) if qty_raw else 0.0
            except ValueError:
                qty = 0.0
            try:
                price = float(price_raw) if price_raw else 0.0
            except ValueError:
                price = 0.0

            line_total = round(qty * price, 2)

            items_to_save.append({
                "itemName": name,
                "modelNo": model,
                "specifications": specs,
                "itemQuantity": qty_raw,
                "unitPrice": price_raw,
                "lineTotal": line_total,
            })

        totalAmount = f"{sum(item['lineTotal'] for item in items_to_save):.2f}"

        # Save the uploaded files to disk and collect their names
        saved_file_names = []
        uploaded_files = request.files.getlist("uploadedFiles")
        for file in uploaded_files:
            if file and file.filename:
                safe_name = secure_filename(file.filename)
                # Prefix with the quotation number so files from different
                # bills don't overwrite each other
                unique_name = f"{quotationNumber}_{safe_name}"
                file.save(os.path.join(UPLOAD_FOLDER, unique_name))
                saved_file_names.append(unique_name)

        uploadedFiles = ", ".join(saved_file_names)

        print("Quotation Number:", quotationNumber)
        print("Customer Name:", customerName)
        print("Items:", items_to_save)
        print("Total Amount:", totalAmount)
        print("Uploaded Files:", uploadedFiles)

        conn = sqlite3.connect("database.db")
        cursor = conn.cursor()

        # Step 1: save the main quotation record first, so we get its id
        cursor.execute("""
            INSERT INTO quotations (
                quotationDate, quotationExpiry, quotationNumber, states,
                paymentMethod, salespersonName, totalAmount,
                customerName, billingAddress, shippingAddress, companyName,
                companyAddress, statesCustomer, customerGst, email, phoneNo,
                paymentTerms, warrantyTerm, termsData, uploadedFiles, company_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            quotationDate, quotationExpiry, quotationNumber, states,
            paymentMethod, salespersonName, totalAmount,
            customerName, billingAddress, shippingAddress, companyName,
            companyAddress, statesCustomer, customerGst, email, phoneNo,
            paymentTerms, warrantyTerm, termsData, uploadedFiles, company_id
        ))

        new_quotation_id = cursor.lastrowid

        # Step 2: save each item, linked to that quotation's id
        for item in items_to_save:
            cursor.execute("""
                INSERT INTO quotation_items (
                    quotation_id, itemName, modelNo, specifications,
                    itemQuantity, unitPrice, lineTotal
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                new_quotation_id, item["itemName"], item["modelNo"],
                item["specifications"], item["itemQuantity"],
                item["unitPrice"], item["lineTotal"]
            ))

        conn.commit()
        conn.close()

        # Send the user straight to the bill/quotation preview page
        # instead of reloading the empty form
        return redirect(url_for("quotation_preview", quotation_id=new_quotation_id))

    # GET request: generate a fresh quotation number for THIS company only,
    # so every company's numbering starts at QT000001 independently
    quotation_number = generate_quotation_number(company_id)
    return render_template("index.html", quotation_number=quotation_number)


# ---------------------------------------------------
# ROUTE: REVISE EXISTING QUOTATION
# Opens an existing quotation for editing and gives it a
# revision number such as QT000001A, QT000001B, etc.
# ---------------------------------------------------
@app.route("/quotation/<int:quotation_id>/revise", methods=["GET", "POST"])
def revise_quotation(quotation_id):

    if "company_id" not in session:
        return redirect(url_for("signup"))

    company_id = session["company_id"]

    # Get the original quotation
    bundle = get_quotation_bundle(quotation_id)

    if not bundle:
        return "Quotation not found", 404

    original = bundle["quotation"]

    # Make sure the quotation belongs to the current company
    if int(original.get("company_id") or 0) != int(company_id):
        return "Unauthorized", 403

    original_number = original.get("quotationNumber", "")

    # If the quotation is already a revision, remove the final letter
    # so QT000001B -> QT000001 before generating the next revision.
    if (
        len(original_number) > 2
        and original_number[-1].isalpha()
    ):
        base_number = original_number[:-1]
    else:
        base_number = original_number

    try:
        revision_number = generate_revision_number(
            company_id,
            base_number
        )
    except ValueError as exc:
        return str(exc), 400

    # ---------------------------------------------------
    # GET = show the quotation form with existing data
    # ---------------------------------------------------
    if request.method == "GET":
        return render_template(
            "index.html",
            quotation_number=revision_number,
            revision_mode=True,
            revision_source_id=quotation_id,
            revision_quotation=original,
            revision_items=bundle["items"],
        )

    # ---------------------------------------------------
    # POST = save the revised quotation as a NEW record
    # ---------------------------------------------------

    quotationDate = request.form.get("quotationDate")
    quotationExpiry = request.form.get("quotationExpiry")
    states = request.form.get("states")
    paymentMethod = request.form.get("paymentMethod")
    salespersonName = request.form.get("salespersonName")

    customerName = request.form.get("customerName")
    billingAddress = request.form.get("billingAddress")
    shippingAddress = request.form.get("shippingAddress")
    companyName = request.form.get("companyName")
    companyAddress = request.form.get("companyAddress")
    statesCustomer = request.form.get("statesCustomer")
    customerGst = request.form.get("customerGst")
    email = request.form.get("email")
    phoneNo = request.form.get("phoneNo")

    paymentTerms = request.form.get("payment-terms")
    warrantyTerm = request.form.get("warranty-term")
    termsData = request.form.get("termsData")

    item_names = request.form.getlist("itemName[]")
    item_models = request.form.getlist("modelNo[]")
    item_specs = request.form.getlist("specifications[]")
    item_quantities = request.form.getlist("itemQuantity[]")
    item_prices = request.form.getlist("unitPrice[]")

    items_to_save = []

    total_count = max(
        len(item_names),
        len(item_models),
        len(item_specs),
        len(item_quantities),
        len(item_prices)
    )

    for i in range(total_count):

        name = item_names[i].strip() if i < len(item_names) else ""
        model = item_models[i].strip() if i < len(item_models) else ""
        specs = item_specs[i].strip() if i < len(item_specs) else ""

        qty_raw = (
            item_quantities[i].strip()
            if i < len(item_quantities)
            else ""
        )

        price_raw = (
            item_prices[i].strip()
            if i < len(item_prices)
            else ""
        )

        if not name and not model and not specs and not qty_raw and not price_raw:
            continue

        try:
            qty = float(qty_raw) if qty_raw else 0
        except ValueError:
            qty = 0

        try:
            price = float(price_raw) if price_raw else 0
        except ValueError:
            price = 0

        items_to_save.append({
            "itemName": name,
            "modelNo": model,
            "specifications": specs,
            "itemQuantity": qty_raw,
            "unitPrice": price_raw,
            "lineTotal": round(qty * price, 2),
        })

    totalAmount = f"{sum(item['lineTotal'] for item in items_to_save):.2f}"

    # Save uploaded attachments
    saved_file_names = []

    for file in request.files.getlist("uploadedFiles"):
        if file and file.filename:
            safe_name = secure_filename(file.filename)
            unique_name = f"{revision_number}_{safe_name}"

            file.save(
                os.path.join(UPLOAD_FOLDER, unique_name)
            )

            saved_file_names.append(unique_name)

    uploadedFiles = ", ".join(saved_file_names)

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO quotations (
            quotationDate,
            quotationExpiry,
            quotationNumber,
            states,
            paymentMethod,
            salespersonName,
            totalAmount,
            customerName,
            billingAddress,
            shippingAddress,
            companyName,
            companyAddress,
            statesCustomer,
            customerGst,
            email,
            phoneNo,
            paymentTerms,
            warrantyTerm,
            termsData,
            uploadedFiles,
            company_id
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        quotationDate,
        quotationExpiry,
        revision_number,
        states,
        paymentMethod,
        salespersonName,
        totalAmount,
        customerName,
        billingAddress,
        shippingAddress,
        companyName,
        companyAddress,
        statesCustomer,
        customerGst,
        email,
        phoneNo,
        paymentTerms,
        warrantyTerm,
        termsData,
        uploadedFiles,
        company_id
    ))

    new_quotation_id = cursor.lastrowid

    # Save revised quotation items
    for item in items_to_save:
        cursor.execute("""
            INSERT INTO quotation_items (
                quotation_id,
                itemName,
                modelNo,
                specifications,
                itemQuantity,
                unitPrice,
                lineTotal
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            new_quotation_id,
            item["itemName"],
            item["modelNo"],
            item["specifications"],
            item["itemQuantity"],
            item["unitPrice"],
            item["lineTotal"]
        ))

    conn.commit()
    conn.close()

    return redirect(
        url_for(
            "quotation_preview",
            quotation_id=new_quotation_id
        )
    )


# ---------------------------------------------------
# Compares the company's state and the customer's state to decide the
# tax split - same state -> CGST (9%) + SGST (9%), different state ->
# IGST (18%). Returns the tax breakdown dict and the final grand total.
# ---------------------------------------------------
def calculate_tax(subtotal, company_state, customer_state):
    company_state = (company_state or "").strip().lower()
    customer_state = (customer_state or "").strip().lower()

    if company_state and customer_state and company_state == customer_state:
        cgst = round(subtotal * 0.09, 2)
        sgst = round(subtotal * 0.09, 2)
        tax_breakdown = {
            "type": "cgst_sgst",
            "cgst_percent": 9,
            "sgst_percent": 9,
            "cgst_amount": cgst,
            "sgst_amount": sgst,
            "tax_total": round(cgst + sgst, 2),
        }
    else:
        igst = round(subtotal * 0.18, 2)
        tax_breakdown = {
            "type": "igst",
            "igst_percent": 18,
            "igst_amount": igst,
            "tax_total": igst,
        }

    grand_total = round(subtotal + tax_breakdown["tax_total"], 2)
    return tax_breakdown, grand_total


# ---------------------------------------------------
# Fetches a single quotation, its items, and the company that
# created it - all combined into one dictionary, ready to be
# displayed on the bill preview page
# ---------------------------------------------------
def get_quotation_bundle(quotation_id):
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM quotations WHERE id = ?", (quotation_id,))
    quotation_row = cursor.fetchone()
    if not quotation_row:
        conn.close()
        return None

    quotation = dict(quotation_row)

    cursor.execute("""
        SELECT itemName, modelNo, specifications, itemQuantity,
               unitPrice, lineTotal
        FROM quotation_items
        WHERE quotation_id = ?
    """, (quotation_id,))
    items = [dict(row) for row in cursor.fetchall()]

    company = {}
    if quotation.get("company_id"):
        cursor.execute("SELECT * FROM companies WHERE id = ?", (quotation["company_id"],))
        company_row = cursor.fetchone()
        if company_row:
            company = dict(company_row)

    conn.close()

    # ---- Parse the saved Terms & Conditions list (JSON array of strings) ----
    terms_list = []
    if quotation.get("termsData"):
        try:
            parsed = json.loads(quotation["termsData"])
            if isinstance(parsed, list):
                terms_list = [str(t) for t in parsed if str(t).strip()]
        except (ValueError, TypeError):
            terms_list = []

    # ---- Tax calculation, based on comparing the two selected states ----
    subtotal = float(quotation.get("totalAmount") or 0)
    tax_breakdown, grand_total = calculate_tax(
        subtotal, quotation.get("states"), quotation.get("statesCustomer")
    )

    return {
        "quotation": quotation,
        "items": items,
        "company": company,
        "terms_list": terms_list,
        "subtotal": subtotal,
        "tax": tax_breakdown,
        "grand_total": grand_total,
    }


# ---------------------------------------------------
# ROUTE: BILL / QUOTATION PREVIEW
# Shows a clean, printable view of one saved quotation, with a
# button to download it as a PDF
# ---------------------------------------------------
@app.route("/quotation/<int:quotation_id>")
def quotation_preview(quotation_id):
    bundle = get_quotation_bundle(quotation_id)

    if not bundle:
        return "Quotation not found", 404

    quotation = bundle["quotation"]
    if not _quotation_access_allowed(quotation_id, quotation):
        return "Unauthorized", 403

    # ---------------------------------------------------
    # QUOTATION EXPIRY WARNING
    # ---------------------------------------------------
    expiry_warning = False
    expiry_message = ""
    expiry_date_display = ""
    expiry_status = ""

    expiry_value = quotation.get("quotationExpiry")

    if expiry_value:
        try:
            expiry_date = datetime.strptime(
                expiry_value,
                "%Y-%m-%d"
            ).date()

            today = date.today()

            days_remaining = (expiry_date - today).days

            expiry_date_display = expiry_date.strftime(
                "%d %B %Y"
            )

            if days_remaining == 2:
                expiry_warning = True
                expiry_status = "warning"
                expiry_message = "Quotation will expire in 2 days."

            elif days_remaining == 1:
                expiry_warning = True
                expiry_status = "warning"
                expiry_message = "Quotation will expire in 1 day."

            elif days_remaining == 0:
                expiry_warning = True
                expiry_status = "today"
                expiry_message = "Quotation expires today."

            elif days_remaining < 0:
                expiry_warning = True
                expiry_status = "expired"

                days_expired = abs(days_remaining)

                if days_expired == 1:
                    expiry_message = "Quotation expired 1 day ago."
                else:
                    expiry_message = (
                        f"Quotation expired {days_expired} days ago."
                    )

        except (ValueError, TypeError):
            expiry_warning = False
            expiry_message = ""
            expiry_date_display = ""
            expiry_status = ""

    return render_template(
        "quotation_preview.html",
        quotation=quotation,
        items=bundle["items"],
        company=bundle["company"],
        terms_list=bundle["terms_list"],
        subtotal=bundle["subtotal"],
        tax=bundle["tax"],
        grand_total=bundle["grand_total"],
        amount_in_words=amount_to_words(bundle["grand_total"]),

        # Expiry warning information
        expiry_warning=expiry_warning,
        expiry_message=expiry_message,
        expiry_date_display=expiry_date_display,
        expiry_status=expiry_status,
    )


# ---------------------------------------------------
# ROUTE: DOWNLOAD BILL AS PDF
# Renders the same preview page and converts it into a PDF file
# that gets downloaded straight to the user's computer
# ---------------------------------------------------
@app.route("/quotation/<int:quotation_id>/pdf")
def quotation_pdf(quotation_id):
    """Generate a PDF from the same preview used in the browser."""
    if "company_id" not in session:
        return redirect(url_for("signup"))

    bundle = get_quotation_bundle(quotation_id)
    if not bundle:
        return "Quotation not found", 404
    if not _quotation_access_allowed(quotation_id, bundle["quotation"]):
        return "Unauthorized", 403

    # Chrome uses a temporary profile without the user's browser session,
    # so pass a short-lived, quotation-scoped token to the preview route.
    pdf_token = _pdf_token_serializer().dumps({
        "quotation_id": int(quotation_id),
        "company_id": int(session["company_id"]),
    })
    preview_url = url_for(
        "quotation_preview",
        quotation_id=quotation_id,
        pdf_token=pdf_token,
        _external=True,
    )

    # Chrome is installed here on the development machine. Keeping the path
    # explicit also means Chrome does not need to be added to PATH.
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    if not os.path.exists(chrome_path):
        return (
            "Google Chrome was not found at: "
            f"{chrome_path}",
            500,
        )

    temp_dir = tempfile.mkdtemp(prefix="quotation_pdf_")
    pdf_path = os.path.join(
        temp_dir,
        f"{bundle['quotation']['quotationNumber']}.pdf",
    )
    chrome_profile_dir = os.path.join(temp_dir, "chrome_profile")

    try:
        command = [
            chrome_path,
            "--headless",
            "--disable-gpu",
            "--disable-dev-shm-usage",
            "--no-pdf-header-footer",
            f"--user-data-dir={chrome_profile_dir}",
            f"--print-to-pdf={pdf_path}",
            preview_url,
        ]

        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )

        if result.returncode != 0:
            error_message = (
                result.stderr.strip()
                or result.stdout.strip()
                or f"Chrome exited with code {result.returncode}."
            )
            return f"PDF generation failed: {error_message}", 500

        if not os.path.exists(pdf_path):
            return "PDF generation failed: Chrome did not create the PDF file.", 500

        # Read the generated PDF into memory before cleaning up the temporary
        # directory. The browser's temporary files are not needed afterwards.
        with open(pdf_path, "rb") as pdf_file:
            pdf_buffer = BytesIO(pdf_file.read())

        pdf_buffer.seek(0)

        file_name = f"{bundle['quotation']['quotationNumber']}.pdf"

        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=file_name,
        )

    except subprocess.TimeoutExpired:
        return "PDF generation timed out after 60 seconds.", 500

    except Exception as exc:
        return f"PDF generation failed: {exc}", 500

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


# ---------------------------------------------------
# ROUTE: SERVE UPLOADED FILES
# The "uploads" folder is not inside "static", so Flask does not
# serve it automatically. This route lets a saved file (like a
# customer's PO or a spec sheet) be opened/downloaded by its name.
# ---------------------------------------------------
@app.route("/uploads/<path:filename>")
def uploaded_file(filename):
    if "company_id" not in session:
        return redirect(url_for("signup"))

    conn = sqlite3.connect("database.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT uploadedFiles FROM quotations WHERE company_id = ?",
        (session["company_id"],),
    )
    allowed_files = set()
    for (stored_names,) in cursor.fetchall():
        allowed_files.update(name.strip() for name in (stored_names or "").split(",") if name.strip())
    conn.close()

    if filename not in allowed_files:
        return "File not found", 404
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=False)


@app.route("/retrieve-data-page", methods=["GET"])
def retrieve_data_page():
    if "company_id" not in session:
        return redirect(url_for("signup"))
    return render_template("data_retrieval.html")


# ---------------------------------------------------
# ROUTE: DATE RANGE RETRIEVAL (API)
# Receives fromDate/toDate from the frontend, queries the database
# for records within that range, and returns the result as JSON
# ---------------------------------------------------
@app.route("/retrieve-data", methods=["POST"])
def retrieve_data():
    if "company_id" not in session:
        return redirect(url_for("signup"))

    from_date = request.form.get("fromDate")
    to_date = request.form.get("toDate")

    print("From Date:", from_date)
    print("To Date:", to_date)

    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM quotations
        WHERE quotationDate BETWEEN ? AND ? AND company_id = ?
    """, (from_date, to_date, session["company_id"]))
    rows = cursor.fetchall()

    result = []
    for row in rows:
        quotation = dict(row)

        # Fetch this quotation's items and attach them
        cursor.execute("""
            SELECT itemName, modelNo, specifications, itemQuantity,
                   unitPrice, lineTotal
            FROM quotation_items
            WHERE quotation_id = ?
        """, (quotation["id"],))
        items = [dict(item_row) for item_row in cursor.fetchall()]

        # Show a simple readable summary of items in the table
        quotation["items"] = ", ".join(
            f"{item['itemName']} (x{item['itemQuantity']})" for item in items
        )

        # Add the GST-based grand total, using the same tax logic as
        # the bill preview page, so the retrieved table shows the
        # actual payable amount, not just the pre-tax subtotal
        subtotal = float(quotation.get("totalAmount") or 0)
        tax_breakdown, grand_total = calculate_tax(
            subtotal, quotation.get("states"), quotation.get("statesCustomer")
        )
        quotation["subtotal"] = f"{subtotal:.2f}"
        quotation["taxType"] = "CGST+SGST (18%)" if tax_breakdown["type"] == "cgst_sgst" else "IGST (18%)"
        quotation["grandTotal"] = f"{grand_total:.2f}"

        # Drop internal/technical fields that aren't useful to display
        # in this results table
        for field in ("termsData", "totalAmount", "company_id", "companyAddress", "statesCustomer"):
            quotation.pop(field, None)

        result.append(quotation)

    conn.close()

    return jsonify(result)


if __name__ == "__main__":
    init_db()
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")