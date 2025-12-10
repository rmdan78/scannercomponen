import streamlit as st
import pandas as pd
from PIL import Image
import numpy as np
import os
from datetime import datetime
import re
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import requests
import io

# --- CONFIGURATION & SETUP ---
st.set_page_config(page_title="Scanner Komponen", page_icon="📷")

# Initialize Session State
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_name' not in st.session_state:
    st.session_state['user_name'] = ""
if 'user_nik' not in st.session_state:
    st.session_state['user_nik'] = ""
if 'current_scan' not in st.session_state:
    st.session_state['current_scan'] = None # Stores {'number': '...', 'image_name': '...'}

# Helper: Check Login
def check_login(nik, password):
    try:
        if not os.path.exists("users.csv"):
            st.error("Database user (users.csv) tidak ditemukan.")
            return False
            
        users = pd.read_csv("users.csv", dtype=str)
        # Find user
        user = users[(users['nik'] == nik) & (users['password'] == password)]
        
        if not user.empty:
            st.session_state['logged_in'] = True
            st.session_state['user_name'] = user.iloc[0]['name']
            st.session_state['user_nik'] = user.iloc[0]['nik']
            return True
        else:
            return False
    except Exception as e:
        st.error(f"Error login: {e}")
        return False

# Helper: Google Sheets Client
def get_gspread_client():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    # Check for credentials file
    creds_file = 'Credentials.json'
    if not os.path.exists(creds_file):
        creds_file = 'credentials.json'

    # Try Local File first (prioritized based on previous context) or Secrets
    if os.path.exists(creds_file):
        try:
            creds = ServiceAccountCredentials.from_json_keyfile_name(creds_file, scope)
            return gspread.authorize(creds)
        except Exception as e:
            # st.error(f"Local Auth Error: {e}")
            return None
    elif "gcp_service_account" in st.secrets:
        try:
            creds_dict = st.secrets["gcp_service_account"]
            creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
            return gspread.authorize(creds)
        except Exception:
            return None
    
    return None

# Helper: Save Data
def save_data(component_number, name, quantity, image_name="N/A", nik=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Data structure
    new_row = {
        "Timestamp": timestamp,
        "Nama Pengambil": name,
        "Component Number": component_number,
        "Quantity": quantity,
        "Image Name": image_name
    }
    
    # 1. Google Sheets (Global / Centralized)
    client = get_gspread_client()
    if client:
        try:
            try:
                sheet = client.open("Data Scan").sheet1
            except gspread.SpreadsheetNotFound:
                st.warning("Spreadsheet 'Data Scan' tidak ditemukan/belum dishare.")
                sheet = None
            
            if sheet:
                sheet.append_row([timestamp, name, component_number, quantity, image_name])
                st.toast(f"✅ Saved to Google Sheets")
        except Exception as e:
            st.error(f"❌ GSheets Error: {e}")
    else:
        st.warning("⚠️ Google Sheets offline.")

    # 2. Local Excel (Per User/NIK)
    try:
        # Construct filename based on NIK
        # If NIK is empty for some reason, fallback to 'unknown'
        safe_nik = nik if nik else "unknown"
        file_path_xlsx = f"data_{safe_nik}.xlsx"
        
        df_new = pd.DataFrame([new_row])
        
        if os.path.exists(file_path_xlsx):
            df_existing = pd.read_excel(file_path_xlsx)
            df_final = pd.concat([df_existing, df_new], ignore_index=True)
        else:
            df_final = df_new
        df_final.to_excel(file_path_xlsx, index=False)
        st.toast(f"✅ Saved to Excel ({safe_nik})")
    except Exception as e:
        st.error(f"❌ Excel Error: {e}")
        
        # 3. CSV Fallback
        try:
            safe_nik = nik if nik else "unknown"
            file_path_csv = f"data_{safe_nik}.csv"
            mode = 'a' if os.path.exists(file_path_csv) else 'w'
            header = not os.path.exists(file_path_csv)
            df_new.to_csv(file_path_csv, mode=mode, header=header, index=False)
            st.toast(f"✅ Saved to CSV ({safe_nik})")
        except Exception:
            pass

# --- OCR ENGINE SETUP ---
try:
    import cv2
except ImportError:
    cv2 = None

@st.cache_resource
def load_reader():
    try:
        import easyocr
        with st.spinner("Loading OCR Engine..."):
            return easyocr.Reader(['en'])
    except ImportError:
        return None

reader = load_reader()

def ocr_space_api(image_bytes, api_key='helloworld', language='eng'):
    try:
        payload = {'isOverlayRequired': False, 'apikey': api_key, 'language': language, 'OCREngine': 2}
        r = requests.post(
            'https://api.ocr.space/parse/image',
            files={'filename': ('image.jpg', image_bytes, 'image/jpeg')},
            data=payload,
        )
        return r.json()
    except Exception as e:
        return {"IsErroredOnProcessing": True, "ErrorMessage": [str(e)]}


# --- MAIN UI LOGIC ---

if not st.session_state['logged_in']:
    # === LOGIN PAGE ===
    st.title("🔐 Login Scanner")
    
    with st.form("login_form"):
        nik = st.text_input("NIK")
        password = st.text_input("Password", type="password")
        submit = st.form_submit_button("Login")
        
        if submit:
            if check_login(nik, password):
                st.success("Login Berhasil!")
                st.rerun()
            else:
                st.error("NIK atau Password salah!")
                
else:
    # === APP PAGE ===
    st.sidebar.title(f"👤 {st.session_state['user_name']}")
    if st.sidebar.button("Logout"):
        st.session_state['logged_in'] = False
        st.session_state['current_scan'] = None
        st.session_state['user_nik'] = ""
        st.rerun()
        
    st.title("📷 Scanner Komponen")
    st.markdown(f"User: **{st.session_state['user_name']}**")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("1. Scan / Upload")
        input_method = st.radio("Metode:", ["Kamera", "Upload"], horizontal=True, label_visibility="collapsed")
        
        img_file_buffer = None
        if input_method == "Kamera":
            img_file_buffer = st.camera_input("Ambil Foto")
        else:
            img_file_buffer = st.file_uploader("Upload Foto", type=['jpg', 'png'])

        # Reset current scan if raw input changes (simple heuristic)
        # Note: In Streamlit, camera_input triggers rerun on every snap.
        
    with col2:
        st.subheader("2. Verifikasi & Simpan")
        
        if img_file_buffer is not None:
            # Simple heuristic: If image buffer changes (not perfect in Streamlit but works for basic flows)
            # We rely on session state 'current_scan' to persist validity.
            
            image = Image.open(img_file_buffer)
            st.image(image, caption="Uploaded Image", width=200)
            
            # --- OCR PROCESS ---
            # Run OCR only if we haven't already captured a valid number OR if we want to support rescan
            # Ideally, we run OCR if current_scan is None.
            
            if st.session_state['current_scan'] is None:
                with st.spinner("Membaca Teks..."):
                    detected_text = ""
                    image_np = np.array(image)
                    
                    # 1. Local OCR
                    if reader:
                        res = reader.readtext(image_np, detail=0)
                        if res: detected_text = " ".join(res)
                    
                    # 2. Cloud OCR Fallback
                    if not detected_text:
                        img_byte_arr = io.BytesIO()
                        image.save(img_byte_arr, format='JPEG')
                        api_res = ocr_space_api(img_byte_arr.getvalue())
                        if not api_res.get("IsErroredOnProcessing"):
                            parsed = api_res.get("ParsedResults")
                            if parsed: detected_text = parsed[0].get("ParsedText").replace("\r\n", " ")

                    # Regex Extraction (First 7 digits only)
                    matches = re.findall(r'\d{7}', detected_text)
                    if matches:
                        found_number = matches[0]
                        st.session_state['current_scan'] = {
                            'number': found_number,
                            'image_name': getattr(img_file_buffer, 'name', 'camera_capture.jpg')
                        }
                        st.rerun() # Force rerun to show the form
                    else:
                        st.warning("⚠️ Tidak ditemukan angka 7 digit.")
                        st.caption(f"Teks terbaca: {detected_text}")
            
            # --- CONFIRMATION FORM ---
            if st.session_state['current_scan']:
                scan_data = st.session_state['current_scan']
                
                st.success(f"✅ Terdeteksi: **{scan_data['number']}**")
                
                with st.form("save_form"):
                    qty = st.number_input("Jumlah (Pcs)", min_value=1, value=1)
                    
                    c1, c2 = st.columns(2)
                    with c1:
                        if st.form_submit_button("💾 SIMPAN DATA"):
                            save_data(
                                scan_data['number'], 
                                st.session_state['user_name'], 
                                qty, 
                                scan_data['image_name'],
                                st.session_state['user_nik'] # Pass Session NIK
                            )
                            st.session_state['current_scan'] = None # Reset
                            st.rerun()
                            
                    with c2:
                        if st.form_submit_button("❌ BATAL / SCAN ULANG"):
                            st.session_state['current_scan'] = None
                            st.rerun()

    st.divider()
    # Dynamic Data View based on NIK
    nik_str = st.session_state['user_nik']
    st.subheader(f"Data Hari Ini (NIK: {nik_str})")
    
    user_file_xlsx = f"data_{nik_str}.xlsx"
    user_file_csv = f"data_{nik_str}.csv"
    
    data_found = False
    
    if os.path.exists(user_file_xlsx):
        try:
            df = pd.read_excel(user_file_xlsx)
            st.dataframe(df.sort_values(by="Timestamp", ascending=False).head(5))
            data_found = True
        except Exception:
            pass
            
    if not data_found and os.path.exists(user_file_csv):
         try:
             df = pd.read_csv(user_file_csv)
             st.dataframe(df.sort_values(by="Timestamp", ascending=False).head(5))
             data_found = True
         except Exception:
             pass
             
    if not data_found:
        st.info(f"Belum ada data tersimpan untuk NIK {nik_str}.")

    with st.expander("Opsi Data"):
        if st.button("Hapus Data Saya"):
            try:
                if os.path.exists(user_file_xlsx):
                    os.remove(user_file_xlsx)
                if os.path.exists(user_file_csv):
                    os.remove(user_file_csv)
                st.rerun()
            except Exception as e:
                st.error(f"Gagal menghapus: {e}")
