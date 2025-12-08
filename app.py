import streamlit as st
import pandas as pd
from PIL import Image
import numpy as np
import os
from datetime import datetime

try:
    import cv2
except ImportError:
    cv2 = None
    st.error("OpenCV (cv2) not installed. Logic using it will fail.")

# Initialize EasyOCR reader with error handling
@st.cache_resource
def load_reader():
    try:
        import easyocr
    except ImportError:
        # st.error("EasyOCR not installed. Please run `pip install easyocr`.")
        return None
        
    with st.spinner("Downloading/Loading OCR Model (this may take a while first time)..."):
        return easyocr.Reader(['en'])

# Try to load reader but don't crash if it fails
reader = load_reader()

import requests
import io

def ocr_space_api(image_bytes, api_key='helloworld', overlay=False, language='eng'):
    """ OCR.space API request with local file.
        :param image_bytes: byte content of the image
        :param api_key: OCR.space API key. Defaults to 'helloworld'.
        :param language: Language code to be used in OCR.
        :return: Result in JSON format.
    """
    try:
        payload = {
            'isOverlayRequired': overlay,
            'apikey': api_key,
            'language': language,
            'OCREngine': 2
        }
        r = requests.post(
            'https://api.ocr.space/parse/image',
            files={'filename': ('image.jpg', image_bytes, 'image/jpeg')},
            data=payload,
        )
        return r.json()
    except Exception as e:
        return {"IsErroredOnProcessing": True, "ErrorMessage": [str(e)]}

if reader is None:
    st.warning("Local OCR (EasyOCR) not available. Switching to Cloud OCR (requires internet).")


import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# Google Sheets Setup
def get_gspread_client():
    if os.path.exists('credentials.json'):
        try:
            scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
            creds = ServiceAccountCredentials.from_json_keyfile_name('credentials.json', scope)
            client = gspread.authorize(creds)
            return client
        except Exception as e:
            st.error(f"GSheets Auth Error: {e}")
            return None
    return None

def save_data(component_number, image_name="N/A"):
    # Try Excel, fallback to CSV, AND Google Sheets
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    data = {
        "Timestamp": [timestamp],
        "Component Number": [component_number],
        "Image Name": [image_name]
    }
    df_new = pd.DataFrame(data)
    
    # 1. Google Sheets (Priority if enabled)
    client = get_gspread_client()
    if client:
        try:
            # Assumes spreadsheet name is 'Data Scan'. User must create/share it.
            # Or we can use open_by_key if user provides it. 
            # For simplicity, let's look for a sheet named "Data Scan"
            try:
                sheet = client.open("Data Scan").sheet1
            except gspread.SpreadsheetNotFound:
                # Try to create it? No, service accounts can't easily own files visible to user without sharing.
                # Just warn.
                st.warning("Spreadsheet 'Data Scan' tidak ditemukan di akun service account. Pastikan sudah dibagikan ke email service account.")
                sheet = None
            
            if sheet:
                sheet.append_row([timestamp, component_number, image_name])
                st.success(f"✅ Saved to Google Sheets: {component_number}")
        except Exception as e:
            st.error(f"❌ Error saving to Google Sheets: {e}")
            
    # 2. Local Excel
    try:
        file_path_xlsx = "data.xlsx"
        if os.path.exists(file_path_xlsx):
            df_existing = pd.read_excel(file_path_xlsx)
            df_final = pd.concat([df_existing, df_new], ignore_index=True)
        else:
            df_final = df_new
        df_final.to_excel(file_path_xlsx, index=False)
        st.success(f"✅ Saved to Excel: {component_number}")
    except Exception:
        # 3. Fallback CSV
        try:
            file_path_csv = "data.csv"
            mode = 'a' if os.path.exists(file_path_csv) and os.path.getsize(file_path_csv) > 0 else 'w'
            header = mode == 'w'
            df_new.to_csv(file_path_csv, mode=mode, header=header, index=False)
            st.success(f"✅ Saved to CSV: {component_number}")
        except Exception as e_csv:
            st.error(f"❌ Save Failed: {e_csv}")

st.set_page_config(page_title="Scanner Komponen", page_icon="📷")

st.title("📷 Admin Scanner Komponen")
st.markdown("Scan nomor komponen dan simpan otomatis ke **Excel/CSV** & **Google Sheets**.")

col1, col2 = st.columns([1, 1])

with col1:
    st.subheader("Input Gambar")
    input_method = st.radio("Pilih Metode:", ["Kamera Langsung", "Upload Foto"], horizontal=True)
    
    img_file_buffer = None
    if input_method == "Kamera Langsung":
        img_file_buffer = st.camera_input("Ambil Foto Komponen")
        if img_file_buffer is None:
             st.caption("Jika kamera tidak muncul di HP via Network URL, gunakan opsi 'Upload Foto' atau setting browser untuk ijinkan insecure origin.")
    else:
        img_file_buffer = st.file_uploader("Upload Foto Komponen", type=['jpg', 'jpeg', 'png'])

with col2:
    st.subheader("Hasil / Log")
    if img_file_buffer is not None:
        # Load image with PIL
        image = Image.open(img_file_buffer)
        image_np = np.array(image)
        
        with st.status('Sedang memproses OCR (Cloud/Local)...', expanded=True) as status:
            try:
                detected_text = None
                
                # Check if we can use local OCR
                if reader is not None:
                    status.write("Menganalisa gambar (Offline)...")
                    result = reader.readtext(image_np, detail=0)
                    if result:
                        detected_text = " ".join(result)
                else:
                    # Fallback to API
                    status.write("Menganalisa gambar (Cloud API)...")
                    # Convert image to bytes
                    img_byte_arr = io.BytesIO()
                    image.save(img_byte_arr, format='JPEG')
                    img_byte_arr = img_byte_arr.getvalue()
                    
                    api_result = ocr_space_api(img_byte_arr)
                    
                    if api_result.get("IsErroredOnProcessing"):
                         st.error(f"API Error: {api_result.get('ErrorMessage')}")
                    else:
                        parsed_results = api_result.get("ParsedResults")
                        if parsed_results:
                            detected_text = parsed_results[0].get("ParsedText")
                            # Sanitize newline characters
                            detected_text = detected_text.replace("\r\n", " ").strip()

                if detected_text:
                    # Regex Validation: Find 7 digit number
                    matches = re.findall(r'\b\d{7}\b', detected_text)
                    
                    final_number = None
                    if matches:
                        if len(matches) > 1:
                            st.warning(f"Ditemukan beberapa angka 7-digit: {matches}. Mengambil yang pertama.")
                            final_number = matches[0]
                        else:
                            final_number = matches[0]
                    else:
                        st.warning(f"Teks terdeteksi: '{detected_text}', tapi TIDAK ADA angka 7 digit.")

                    if final_number:
                        status.write(f"Valid Validasi (7 Digit): {final_number}")
                        save_data(final_number, "Camera Input")
                        status.update(label="Selesai!", state="complete", expanded=True)
                        st.toast(f"Tersimpan: {final_number}")
                    else:
                         status.update(label="Gagal Validasi", state="error", expanded=True)
                else:
                    status.update(label="Gagal: Tidak ada teks", state="error", expanded=True)
                    st.warning("⚠️ Tidak ada teks yang terdeteksi.")
                    
            except Exception as e:
                status.update(label="Error", state="error")
                st.error(f"Error processing image: {e}")


st.divider()

st.subheader("📋 Data Tersimpan")
try:
    if os.path.exists("data.xlsx"):
        df = pd.read_excel("data.xlsx")
        st.dataframe(df.sort_values(by="Timestamp", ascending=False), height=300)
    elif os.path.exists("data.csv"):
        # Read CSV with headers if it was created with headers
        try:
            df = pd.read_csv("data.csv")
            st.dataframe(df.sort_values(by="Timestamp", ascending=False), height=300)
        except Exception:
             st.write("Data CSV raw:")
             st.write(pd.read_csv("data.csv"))
    else:
        st.info("Belum ada data tersimpan.")
except Exception as e:
    st.error(f"Error loading data: {e}")

with st.expander("Opsi Data"):
    if st.button("Hapus Semua Data"):
        try:
            if os.path.exists("data.xlsx"):
                os.remove("data.xlsx")
            if os.path.exists("data.csv"):
                os.remove("data.csv")
            st.rerun()
        except Exception as e:
            st.error(f"Gagal menghapus: {e}")
