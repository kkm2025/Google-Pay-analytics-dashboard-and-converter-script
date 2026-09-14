#!/usr/bin/env python3
"""
Google Pay / Google Takeout Activity HTML to CSV Converter

Converts 'My_Activity.html' into a structured CSV file with details in separate columns:
- ID, Title, Action, Amount, Currency, Recipient_or_Sender, Payment_Method,
  Status, Parsed_Timestamp, Date_Time_Raw, Transaction_ID, Products, Raw_Description, Location, Links
"""

import os
import sys
import re
import csv
from datetime import datetime
from pathlib import Path

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


VALID_STATUSES = {"completed", "failed", "pending", "cancelled", "refunded", "declined", "success", "successful"}


def clean_status(candidate):
    if not candidate:
        return ""
    cleaned = candidate.strip()
    if not cleaned:
        return ""
    if cleaned.lower() in VALID_STATUSES:
        return cleaned.capitalize()
    elif len(cleaned.split()) == 1 and cleaned.isalpha():
        return cleaned.capitalize()
    return ""


def extract_id_and_status(d_lines):
    """
    Extracts clean transaction_id and status from details lines.
    Handles combined strings like 'GLRBbWB2Q6OYkYPc Completed'.
    """
    transaction_id = ""
    status = ""
    
    if not d_lines:
        return "", ""

    first_line = d_lines[0].strip()
    # Check if first line contains status suffix (e.g. 'GLRBbWB2Q6OYkYPc Completed')
    st_match = re.search(r'\s+(Completed|Failed|Pending|Cancelled|Refunded|Declined|Success)$', first_line, re.IGNORECASE)
    if st_match:
        status = st_match.group(1).capitalize()
        transaction_id = first_line[:st_match.start()].strip()
    else:
        transaction_id = first_line

    if not status and len(d_lines) >= 2:
        status = clean_status(d_lines[1])

    return transaction_id, status


def parse_action_details(text):
    action, amount, currency, recipient_or_sender, payment_method = "", "", "", "", ""

    pm_match = re.search(r'\busing\s+(.+)$', text, re.IGNORECASE)
    if pm_match:
        payment_method = pm_match.group(1).strip()
        main_text = text[:pm_match.start()].strip()
    else:
        main_text = text.strip()

    action_match = re.match(r'^(Paid|Sent|Received|Requested|Used|Added|Bought)\b', main_text, re.IGNORECASE)
    if action_match:
        action = action_match.group(1).capitalize()
    
    amount_match = re.search(r'([₹$€£]|Rs\.?|INR)?\s*([\d,]+(?:\.\d{1,2})?)', main_text)
    if amount_match:
        curr_symbol = amount_match.group(1)
        currency = "INR (₹)" if (curr_symbol == "₹" or "₹" in main_text) else (curr_symbol or "")
        raw_amt = amount_match.group(2).replace(',', '')
        try:
            amount = f"{float(raw_amt):.2f}"
        except ValueError:
            amount = amount_match.group(2)

    to_match = re.search(r'\bto\s+(.+)$', main_text, re.IGNORECASE)
    from_match = re.search(r'\bfrom\s+(.+)$', main_text, re.IGNORECASE)

    if to_match:
        recipient_or_sender = to_match.group(1).strip()
    elif from_match:
        recipient_or_sender = from_match.group(1).strip()

    return {
        "action": action,
        "amount": amount,
        "currency": currency,
        "recipient_or_sender": recipient_or_sender,
        "payment_method": payment_method
    }


def parse_timestamp(ts_str):
    if not ts_str:
        return ""
    clean_ts = ts_str.replace('\u202f', ' ').replace('\xa0', ' ').strip()
    ts_no_tz = re.sub(r'\s+[A-Z]{3,4}$', '', clean_ts)
    
    formats = [
        "%b %d, %Y, %I:%M:%S %p",
        "%b %d, %Y, %H:%M:%S",
        "%d %b %Y, %I:%M:%S %p",
        "%Y-%m-%d %H:%M:%S"
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(ts_no_tz, fmt)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue

    return ""


def parse_with_bs4(html_content):
    soup = BeautifulSoup(html_content, 'html.parser')
    cards = soup.find_all('div', class_=lambda c: c and ('outer-cell' in c or 'mdl-card' in c))
    if not cards:
        cards = soup.find_all('div', class_=lambda c: c and 'mdl-grid' in c)

    rows = []
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    for idx, card in enumerate(cards, 1):
        header_el = card.find('div', class_=lambda c: c and 'header-cell' in c)
        title = header_el.get_text(strip=True) if header_el else "Google Pay"

        content_cells = card.find_all('div', class_=lambda c: c and 'content-cell' in c)

        raw_description, date_time_raw, products, transaction_id, status, location = "", "", "", "", "", ""
        links = [a['href'] for a in card.find_all('a', href=True)]
        links_str = " | ".join(links)

        for cell in content_cells:
            cell_text = cell.get_text(separator='\n', strip=True)
            lines = [line.strip() for line in cell_text.split('\n') if line.strip()]

            if len(lines) >= 2 and any(m in lines[-1] for m in months):
                date_time_raw = lines[-1]
                raw_description = " ".join(lines[:-1])
            elif len(lines) == 1 and any(m in lines[0] for m in months):
                date_time_raw = lines[0]
            elif lines and not raw_description and not cell_text.startswith("Products:") and not cell_text.startswith("Details:"):
                raw_description = " ".join(lines)

            if "Products:" in cell_text or "Details:" in cell_text or "Locations:" in cell_text:
                prod_match = re.search(r'Products:\s*(.*?)(?=(Details:|Locations:|$))', cell_text, re.DOTALL)
                if prod_match:
                    products = prod_match.group(1).replace('\u2003', '').strip()

                det_match = re.search(r'Details:\s*(.*?)(?=(Locations:|$))', cell_text, re.DOTALL)
                if det_match:
                    det_text = det_match.group(1).replace('\u2003', '').strip()
                    det_lines = [d.strip() for d in det_text.split('\n') if d.strip()]
                    transaction_id, status = extract_id_and_status(det_lines)

                loc_match = re.search(r'Locations:\s*(.*)', cell_text, re.DOTALL)
                if loc_match:
                    location = loc_match.group(1).replace('\u2003', '').strip()

        parsed_info = parse_action_details(raw_description)
        parsed_dt = parse_timestamp(date_time_raw)

        rows.append({
            "ID": idx,
            "Title": title,
            "Raw_Description": raw_description,
            "Action": parsed_info["action"],
            "Amount": parsed_info["amount"],
            "Currency": parsed_info["currency"],
            "Recipient_or_Sender": parsed_info["recipient_or_sender"],
            "Payment_Method": parsed_info["payment_method"],
            "Date_Time_Raw": date_time_raw,
            "Parsed_Timestamp": parsed_dt,
            "Transaction_ID": transaction_id,
            "Status": status,
            "Products": products,
            "Location": location,
            "Links": links_str
        })
    return rows


def parse_with_regex_fallback(html_content):
    blocks = re.split(r'<div class="outer-cell[^">]*">', html_content)
    if len(blocks) <= 1:
        blocks = re.split(r'<div class="mdl-grid">', html_content)

    card_blocks = blocks[1:]

    rows = []
    months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

    def strip_tags(text):
        return re.sub(r'<[^>]+>', ' ', text).strip()

    for idx, block in enumerate(card_blocks, 1):
        title_match = re.search(r'class="mdl-typography--title">(.*?)</p>', block, re.DOTALL)
        title = strip_tags(title_match.group(1)) if title_match else "Google Pay"

        content_cells = re.findall(r'<div class="content-cell[^">]*">(.*?)</div>', block, re.DOTALL)

        raw_description, date_time_raw, products, transaction_id, status, location = "", "", "", "", "", ""
        links = [m for m in re.findall(r'href=["\'](.*?)["\']', block)]
        links_str = " | ".join(links)

        for cell in content_cells:
            cell_lines_raw = re.sub(r'<br\s*/?>', '\n', cell)
            text_lines = [strip_tags(line) for line in cell_lines_raw.split('\n') if strip_tags(line)]

            if len(text_lines) >= 2 and any(m in text_lines[-1] for m in months):
                date_time_raw = text_lines[-1]
                raw_description = " ".join(text_lines[:-1])
            elif len(text_lines) == 1 and any(m in text_lines[0] for m in months):
                date_time_raw = text_lines[0]
            elif text_lines and not raw_description and not cell.startswith("<b>Products:") and not cell.startswith("<b>Details:"):
                raw_description = " ".join(text_lines)

            if "Products:" in cell:
                p_m = re.search(r'<b>Products:</b>(.*?)(?:<b>|$)', cell_lines_raw, re.DOTALL)
                if p_m:
                    products = strip_tags(p_m.group(1)).replace('&emsp;', '').strip()

            if "Details:" in cell:
                d_m = re.search(r'<b>Details:</b>(.*?)(?:<b>|$)', cell_lines_raw, re.DOTALL)
                if d_m:
                    d_text = d_m.group(1).replace('&emsp;', '').strip()
                    d_lines = [strip_tags(l) for l in d_text.split('\n') if strip_tags(l)]
                    transaction_id, status = extract_id_and_status(d_lines)

            if "Locations:" in cell:
                l_m = re.search(r'<b>Locations:</b>(.*?)(?:<b>|$)', cell_lines_raw, re.DOTALL)
                if l_m:
                    location = strip_tags(l_m.group(1)).replace('&emsp;', '').strip()

        parsed_info = parse_action_details(raw_description)
        parsed_dt = parse_timestamp(date_time_raw)

        rows.append({
            "ID": idx,
            "Title": title,
            "Raw_Description": raw_description,
            "Action": parsed_info["action"],
            "Amount": parsed_info["amount"],
            "Currency": parsed_info["currency"],
            "Recipient_or_Sender": parsed_info["recipient_or_sender"],
            "Payment_Method": parsed_info["payment_method"],
            "Date_Time_Raw": date_time_raw,
            "Parsed_Timestamp": parsed_dt,
            "Transaction_ID": transaction_id,
            "Status": status,
            "Products": products,
            "Location": location,
            "Links": links_str
        })
    return rows


def find_default_html():
    candidates = [
        "My_Activity/My_Activity.html",
        "My Activity/My Activity.html",
        "My_Activity.html",
        "My Activity.html"
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return None


def convert_html_to_csv(html_path, csv_path):
    print(f"Reading HTML file: {html_path}")
    with open(html_path, 'r', encoding='utf-8') as f:
        html_content = f.read()

    if HAS_BS4:
        print("Parsing using BeautifulSoup4...")
        rows = parse_with_bs4(html_content)
    else:
        print("BeautifulSoup4 not found, parsing using regex fallback...")
        rows = parse_with_regex_fallback(html_content)

    print(f"Extracted {len(rows)} activity records.")

    fieldnames = [
        "ID",
        "Title",
        "Action",
        "Amount",
        "Currency",
        "Recipient_or_Sender",
        "Payment_Method",
        "Status",
        "Parsed_Timestamp",
        "Date_Time_Raw",
        "Transaction_ID",
        "Products",
        "Raw_Description",
        "Location",
        "Links"
    ]

    print(f"Saving to CSV: {csv_path}")
    with open(csv_path, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\n✅ Conversion complete! Saved {len(rows)} rows to '{csv_path}'.")
    return len(rows)


if __name__ == "__main__":
    import argparse
    default_input = find_default_html() or "My_Activity/My_Activity.html"
    
    parser = argparse.ArgumentParser(description="Convert Google Pay My Activity HTML to CSV")
    parser.add_argument("html_file", nargs="?", default=default_input, help="Path to input HTML file")
    parser.add_argument("csv_file", nargs="?", default="My_Activity.csv", help="Path to output CSV file")

    args = parser.parse_args()

    input_path = Path(args.html_file)
    if not input_path.exists():
        fallback = find_default_html()
        if fallback:
            input_path = Path(fallback)
        else:
            print(f"❌ Error: HTML file '{args.html_file}' not found.")
            sys.exit(1)

    convert_html_to_csv(str(input_path), args.csv_file)
