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

api_key = os.environ["BARCODELOOKUP_API_KEY"]

# Google Sheets setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds = ServiceAccountCredentials.from_json_keyfile_name(
    os.environ["GOOGLE_CREDS_PATH"], scope)
client = gspread.authorize(creds)
sheet = client.open("Puslespill").sheet1

# Existing barcodes
existing_barcodes = set(sheet.col_values(1)[1:])

@app.post("/scan")
async def receive_scan(data: ScanData):
    barcode_number = data.ean.strip()
    if not barcode_number.isdigit() or len(barcode_number) < 13:
        return {"status": "error", "message": "Invalid barcode format"}
    
    if barcode_number in existing_barcodes:
        return {"status": "already_exists", "ean": barcode_number}

    # Get product info from Barcodelookup API
    api_url = f"https://api.barcodelookup.com/v3/products?barcode={barcode_number}&formatted=y&key={api_key}"
    try:
        response = requests.get(api_url)
    except requests.RequestException as e:
        sheet.append_row([barcode_number, "N/A", "N/A", "N/A", "N/A", "", "", ""], 
                         value_input_option="USER_ENTERED")
        existing_barcodes.add(barcode_number)
        return {"status": "added", "info": "barcode_only (API unreachable)"}
    
    # Read the JSON data
    product = response.json()["products"][0]

    title = product.get("title") or "N/A"
    brand = product.get("brand") or "N/A"
    manufacturer = product.get("manufacturer") or "N/A"
    description = product.get("description") or "N/A"
    images = product.get("images", [])[:3]

    # Make image formulas for Google Sheets
    image_formulas = [f'=IMAGE("{img}")' for img in images]
    image_formulas  += [""] * (3 - len(image_formulas))

    # Add a row with the data to the Google Sheet
    sheet.append_row([barcode_number, title, brand, manufacturer, description] + image_formulas,
                        value_input_option="USER_ENTERED")
    existing_barcodes.add(barcode_number)

    return {"status": "success", "ean": barcode_number, "title": title, "brand": brand}

@app.get("/")
def health():
    return {"status": "ok"}