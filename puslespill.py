import requests 
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from fastapi import FastAPI
from pydantic import BaseModel
import os 

app = FastAPI(
    title="Puslespill Barcode Scanner API",
    description="Receives barcode scans from mobile app and adds puzzles to Google Sheets",
    version="1.0.0"
)

class ScanData(BaseModel):
    ean: str

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    os.environ["GOOGLE_CREDS_PATH"], scope)
client = gspread.authorize(creds)
sheet = client.open("Puslespill").sheet1

existing_barcodes = set(sheet.col_values(1)[1:])
UPCITEMDB_API_URL = "https://api.upcitemdb.com/prod/trial/lookup"

@app.post("/scan")
async def receive_scan(data: ScanData):
    barcode_number = data.ean.strip()
    if not barcode_number.isdigit() or len(barcode_number) < 13:
        return {"status": "error", "message": "Invalid barcode format"}
    
    if barcode_number in existing_barcodes:
        return {"status": "already_exists", "ean": barcode_number}

    # Get product info from UPCITEMDB API
    try:
        response = requests.get(UPCITEMDB_API_URL, params={"upc": barcode_number}, timeout=5)
        response.raise_for_status()

    except requests.RequestException:
        sheet.append_row([barcode_number, "N/A", "N/A", "N/A", "N/A", "", "", ""], 
                         value_input_option="USER_ENTERED")
        existing_barcodes.add(barcode_number)
        return {"status": "added", "info": "barcode_only (API unreachable)"}
    
    # Read the JSON data
    data_json = response.json()
    items = data_json.get("items", [])

    if not items:
        sheet.append_row([barcode_number, "N/A", "N/A", "N/A", "N/A", "", "", ""],
                        value_input_option="USER_ENTERED")
        existing_barcodes.add(barcode_number)
        return {"status": "added", "info": "barcode_only (not found in UPCitemdb)"}

    product = items[0]

    title = product.get("title") or "N/A"
    brand = product.get("brand") or "N/A"
    manufacturer = product.get("manufacturer") or "N/A"
    description = product.get("description") or "N/A"
    images = product.get("images", [])[:3]

    # Add a row with the data to the Google Sheet
    sheet.append_row([barcode_number, title, brand, manufacturer, description] + images,
                        value_input_option="USER_ENTERED")
    existing_barcodes.add(barcode_number)

    return {"status": "success", "ean": barcode_number, "title": title, "brand": brand}

@app.get("/product/{ean}")
async def get_product(ean: str):
    ean = ean.strip()

    cell = sheet.find(ean)
    if cell is None:
        return {"status": "not_found", "message": f"EAN {ean} finnes ikke i databasen"}
    
    row_values = sheet.row_values(cell.row)

    product_info = {
        "ean": row_values[0] if len(row_values) > 0 else "N/A",
        "title": row_values[1] if len(row_values) > 1 else "N/A",
        "brand": row_values[2] if len(row_values) > 2 else "N/A",
        "manufacturer": row_values[3] if len(row_values) > 3 else "N/A",
        "description": row_values[4] if len(row_values) > 4 else "N/A",
        "images": row_values[5:8] if len(row_values) > 5 else [],
    }

    return {"status": "success", "product": product_info}
    
@app.get("/")
def health():
    return {"status": "ok"}