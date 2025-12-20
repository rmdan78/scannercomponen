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
st.set_page_config(page_title="Scanner Komponen", page_icon="📷", layout="centered")

# Initialize Session State
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_name' not in st.session_state:
    st.session_state['user_name'] = ""
if 'user_nik' not in st.session_state:
    st.session_state['user_nik'] = ""
if 'current_scan' not in st.session_state:
    st.session_state['current_scan'] = None # Stores {'number': '...', 'image_name': '...'}

# Helper: Check Login (DEPRECATED/BYPASSED)
def check_login(nik, password):
    # Simplified for legacy compatibility if called, but we are bypassing login
    return True

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
def save_data(component_number, operator_nik, operator_name, quantity, item_name="", image_name="N/A", session_nik="", reason=""):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Data structure
    new_row = {
        "Timestamp": timestamp,
        "NIK Operator": operator_nik,
        "Nama Operator": operator_name,
        "Component Number": component_number,
        "Nama Barang": item_name,
        "Quantity": quantity,
        "Nama Barang": item_name,
        "Quantity": quantity,
        "Image Name": image_name,
        "Keterangan": reason
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
                sheet.append_row([timestamp, operator_nik, operator_name, component_number, item_name, quantity, reason])
                st.toast(f"✅ Saved to Google Sheets")
        except Exception as e:
            st.error(f"❌ GSheets Error: {e}")
    else:
        st.warning("⚠️ Google Sheets offline.")

    # 2. Local Excel (Per User/NIK)
    try:
        # Construct filename based on Session NIK (usually 'general' or logged in user)
        # We use session_nik for the filename to keep files organized by the device/session user if needed,
        # or we could use operator_nik. But usually session_nik is safer for file locking if multiple people use same device?
        # Let's stick to session_nik for filename but save operator_nik inside.
        safe_nik = session_nik if session_nik else "unknown"
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
            safe_nik = session_nik if session_nik else "unknown"
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

# --- THEME LOGIC ---
def get_theme_css(theme):
    if theme == "Gelap":
        return """
        <style>
        /* Dark Mode Override */
        [data-testid="stAppViewContainer"] {
            background-color: #0e1117;
            color: #fafafa;
        }
        [data-testid="stSidebar"] {
            background-color: #262730;
            color: #fafafa;
        }
        [data-testid="stHeader"] {
            background-color: rgba(0,0,0,0);
        }
        .stTextInput > div > div > input, .stNumberInput > div > div > input, .stTextArea > div > div > textarea {
            background-color: #262730;
            color: #fafafa;
        }
        </style>
        """
    else:
        return """
        <style>
        /* Light Mode Override (Default-ish but enforced) */
        [data-testid="stAppViewContainer"] {
            background-color: #ffffff;
            color: #31333F;
        }
        [data-testid="stSidebar"] {
            background-color: #f0f2f6;
            color: #31333F;
        }
        [data-testid="stHeader"] {
            background-color: rgba(0,0,0,0);
        }
        </style>
        """


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

# Bypass Login
# st.session_state['logged_in'] = True (Implicitly treated as logged in)
current_user_name = "Operator"
current_user_nik = "general"

# Sync session state if needed (optional but good for consistency)
if st.session_state.get('user_name') != current_user_name:
    st.session_state['user_name'] = current_user_name
    st.session_state['user_nik'] = current_user_nik
    st.session_state['logged_in'] = True

# === APP PAGE ===

# Sidebar Navigation
st.sidebar.title("Menu")

# Theme Toggle
theme_choice = st.sidebar.select_slider("Tampilan", options=["Terang", "Gelap"], value="Terang")
st.markdown(get_theme_css(theme_choice), unsafe_allow_html=True)

page = st.sidebar.radio("Pilih Halaman:", ["Scanner", "Riwayat Pengambilan"])

if page == "Scanner":
    st.title("📷 Scanner Komponen")
    st.markdown(f"User: **{st.session_state['user_name']}**")
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.subheader("1. Input Data")
        # Removed "Upload Foto" option
        input_method = st.radio("Metode:", ["Scan Kamera", "Input Manual / Ketik"], horizontal=True, label_visibility="collapsed")
        
        img_file_buffer = None
        manual_code_input = ""
        
        if input_method == "Scan Kamera":
            img_file_buffer = st.camera_input("Ambil Foto")
        elif input_method == "Input Manual / Ketik":
            manual_code_input = st.text_input("Masukkan Kode (7 Digit):", max_chars=7)
    
        # Reset current scan if raw input changes (simple heuristic)
        # Note: In Streamlit, camera_input triggers rerun on every snap.
        
    with col2:
        st.subheader("2. Verifikasi & Simpan")
        
        # --- DATABASE VALIDATION ---
        valid_part = False
        part_description = ""
        
        # Load Database (Cached)
        @st.cache_data
        def load_spareparts_db():
            db_path = "Data_sparepart.csv"
            if os.path.exists(db_path):
                try:
                    # Read as string to ensure matching works correctly
                    df_db = pd.read_csv(db_path, dtype=str)
                    return df_db
                except Exception:
                    return None
            return None
    
        df_parts = load_spareparts_db()
    
        # --- DATABASE VALIDATION ---
        valid_part = False
        part_description = ""
        
        # Load Spareparts Database (Cached)
        @st.cache_data
        def load_spareparts_db():
            db_path = "Data_sparepart.csv"
            if os.path.exists(db_path):
                try:
                    df_db = pd.read_csv(db_path, dtype=str)
                    return df_db
                except Exception:
                    return None
            return None
    
        # Load Operator Database (Cached)
        @st.cache_data
        def load_operator_db():
            db_path = "operator.csv"
            if os.path.exists(db_path):
                try:
                    # Assuming columns: Personnel Number, Salutation, Name
                    df_op = pd.read_csv(db_path, dtype=str)
                    return df_op
                except Exception:
                    return None
            return None
    
        df_parts = load_spareparts_db()
        df_operators = load_operator_db()
    
        # --- HANDLING MANUAL INPUT ---
        if input_method == "Input Manual / Ketik" and manual_code_input:
            if len(manual_code_input) == 7 and manual_code_input.isdigit():
                 # Validate against DB
                 if df_parts is not None:
                     part_match = df_parts[df_parts['Material'] == manual_code_input]
                     if not part_match.empty:
                         valid_part = True
                         part_description = part_match.iloc[0]['Material Description']
                     else:
                         st.error(f"❌ Komponen {manual_code_input} tidak ditemukan di database!")
                 else:
                     st.error("⚠️ Database Data_sparepart.csv tidak ditemukan.")
    
                 if valid_part:
                     # Create a 'fake' scan state for manual input
                     if st.session_state['current_scan'] is None or st.session_state['current_scan']['number'] != manual_code_input:
                        st.session_state['current_scan'] = {
                            'number': manual_code_input,
                            'image_name': "Manual Input",
                            'description': part_description
                        }
                        st.rerun()
            elif len(manual_code_input) > 0:
                st.warning("⚠️ Masukkan 7 digit angka.")
                
        # --- HANDLING CAMERA ---
        if img_file_buffer is not None:
            image = Image.open(img_file_buffer)
            
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
                        
                        # Validate against DB
                        if df_parts is not None:
                            part_match = df_parts[df_parts['Material'] == found_number]
                            if not part_match.empty:
                                part_description = part_match.iloc[0]['Material Description']
                                st.session_state['current_scan'] = {
                                    'number': found_number,
                                    'image_name': getattr(img_file_buffer, 'name', 'camera_capture.jpg'),
                                    'description': part_description
                                }
                                st.rerun() # Force rerun to show the form
                            else:
                                 st.error(f"❌ Komponen {found_number} terbaca tapi tidak ada di database.")
                        else:
                            st.error("⚠️ Database Data_sparepart.csv tidak ditemukan.")
                            
                    else:
                        st.warning("⚠️ Tidak ditemukan angka 7 digit.")
                        st.caption(f"Teks terbaca: {detected_text}")
            
        # --- CONFIRMATION FORM ---
        if st.session_state['current_scan']:
            scan_data = st.session_state['current_scan']
            
            st.success(f"✅ Data: **{scan_data['number']}**")
            if 'description' in scan_data:
                st.info(f"📦 {scan_data['description']}")
                
            # --- NIK INPUT & VALIDATION (Outside Form for interactivity) ---
            st.caption("Masukkan Detail Pengambil:")
            input_nik = st.text_input("NIK Operator (6 Digit)", max_chars=6, placeholder="Contoh: 123456", key="nik_input")
            
            valid_nik = False
            operator_name = ""
            
            if input_nik and len(input_nik) == 6 and input_nik.isdigit():
                if df_operators is not None:
                    op_match = df_operators[df_operators['Personnel Number'] == input_nik]
                    if not op_match.empty:
                        valid_nik = True
                        operator_name = op_match.iloc[0]['Name']
                        st.info(f"👤 Operator: **{operator_name}**")
                        
                        # --- SHOW HISTORY FOR THIS NIK ---
                        # Load current data file
                        nik_str = st.session_state['user_nik']
                        user_file_xlsx = f"data_{nik_str}.xlsx"
                        user_file_csv = f"data_{nik_str}.csv"
                        df_history = pd.DataFrame()
                        
                        if os.path.exists(user_file_xlsx):
                            try: df_history = pd.read_excel(user_file_xlsx)
                            except: pass
                        elif os.path.exists(user_file_csv):
                            try: df_history = pd.read_csv(user_file_csv)
                            except: pass
                            
                        if not df_history.empty and "NIK Operator" in df_history.columns:
                            # Filter by NIK (ensure string comparison)
                            df_history['NIK Operator'] = df_history['NIK Operator'].astype(str)
                            user_history = df_history[df_history['NIK Operator'] == input_nik]
                            
                            if not user_history.empty:
                                with st.expander(f"Riwayat Pengambilan ({len(user_history)})"):
                                    st.dataframe(user_history[['Timestamp', 'Nama Barang', 'Quantity']].sort_values(by="Timestamp", ascending=False).head(5))
                            else:
                                st.caption("Belum ada riwayat pengambilan.")
                    else:
                        st.error("❌ NIK tidak terdaftar!")
                else:
                    st.warning("⚠️ Database operator tidak ditemukan.")
                    valid_nik = True # Allow if DB missing
    
            with st.form("save_form"):
                qty = st.number_input("Jumlah (Pcs)", min_value=1, value=1)
                reason = st.text_area("Keterangan / Keperluan:", placeholder="Contoh: Penggantian part mesin A...")
                
                c1, c2 = st.columns(2)
                with c1:
                    if st.form_submit_button("💾 SIMPAN DATA"):
                        if valid_nik:
                            save_data(
                                scan_data['number'], 
                                input_nik, # Operator NIK
                                operator_name, # Operator Name
                                qty, 
                                scan_data.get('description', ''), # Item Name
                                scan_data['image_name'],
                                st.session_state['user_nik'], # Session NIK
                                reason # Reason
                            )
                            st.session_state['current_scan'] = None # Reset
                            st.rerun()
                        else:
                            st.error("⚠️ NIK tidak valid!")
                        
                with c2:
                    if st.form_submit_button("❌ BATAL / RESET"):
                        st.session_state['current_scan'] = None
                        st.rerun()

elif page == "Riwayat Pengambilan":
    st.title("📜 Riwayat Pengambilan")
    
    # Load Operator Database (Cached) for Mapping
    @st.cache_data
    def load_operator_db():
        db_path = "operator.csv"
        if os.path.exists(db_path):
            try:
                df_op = pd.read_csv(db_path, dtype=str)
                return df_op
            except Exception:
                return None
        return None
    
    df_operators = load_operator_db()
    
    # Dynamic Data View based on NIK
    nik_str = st.session_state['user_nik']
    # st.subheader(f"Data Hari Ini (NIK: {nik_str})") # Removed subheader to be cleaner
    
    user_file_xlsx = f"data_{nik_str}.xlsx"
    user_file_csv = f"data_{nik_str}.csv"
    
    data_found = False
    
    df = pd.DataFrame()
    file_type = None
    
    # Load Data
    if os.path.exists(user_file_xlsx):
        try:
            df = pd.read_excel(user_file_xlsx)
            file_type = 'xlsx'
        except Exception: pass
    elif os.path.exists(user_file_csv):
        try:
            df = pd.read_csv(user_file_csv, on_bad_lines='skip')
            file_type = 'csv'
        except Exception: pass
        
    # Display Data
    if not df.empty:
        # --- DATE FILTER ---
        st.caption("Filter Tanggal:")
        selected_date = st.date_input("Pilih Tanggal", value=datetime.now().date())
        
        # Convert Timestamp to datetime objects for filtering
        try:
            df['Timestamp_dt'] = pd.to_datetime(df['Timestamp'])
            df_filtered = df[df['Timestamp_dt'].dt.date == selected_date].copy()
        except Exception:
            df_filtered = df.copy() # Fallback if parsing fails
            
        if not df_filtered.empty:
            # --- DETERMINE OPERATOR NAME ---
            # If 'Nama Operator' exists in saved data, use it. Otherwise map from NIK.
            if 'Nama Operator' in df_filtered.columns:
                df_filtered['Operator'] = df_filtered['Nama Operator'].fillna(df_filtered['NIK Operator'])
            else:
                # Fallback: Map NIK TO OPERATOR NAME
                if df_operators is not None:
                    nik_to_name = dict(zip(df_operators['Personnel Number'], df_operators['Name']))
                    df_filtered['Operator'] = df_filtered['NIK Operator'].astype(str).map(nik_to_name).fillna(df_filtered['NIK Operator'])
                else:
                    df_filtered['Operator'] = df_filtered['NIK Operator']

            # Select and Rename Columns
            cols_to_show = ['Timestamp', 'Component Number', 'Nama Barang', 'Quantity', 'Keterangan', 'Operator']
            # Ensure columns exist (handle legacy data)
            existing_cols = [c for c in cols_to_show if c in df_filtered.columns or c == 'Operator']
            
            st.dataframe(
                df_filtered[existing_cols].sort_values(by="Timestamp", ascending=False),
                column_config={
                    "Timestamp": "Waktu",
                    "Component Number": "No. Komponen",
                    "Nama Barang": "Nama Komponen",
                    "Quantity": "Qty",
                    "Keterangan": "Ket.",
                    "Operator": "Operator"
                },
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info(f"Tidak ada data untuk tanggal {selected_date.strftime('%d-%m-%Y')}.")
        
        st.divider()
        st.subheader("Hapus Data")
        with st.expander("Opsi Hapus Data"):
            # Prepare for deletion (Using original df to allow deleting any data, or filtered? Usually safer to delete from full list or filtered list)
            # Let's show all data for deletion to be safe/flexible, or just filtered? 
            # User asked for "data list pengambilan hari ini ditampilkan...", deletion logic was previous request.
            # I will keep deletion logic on the FULL dataframe for now to allow managing all data, 
            # OR I can filter it too. Let's keep it on full df but maybe sort by timestamp.
            
            # Create a temporary column for display labels
            # Handle missing columns in legacy data
            if 'Nama Barang' not in df.columns: df['Nama Barang'] = "-"
            
            df['display_label'] = df['Timestamp'].astype(str) + " | " + df['Component Number'].astype(str) + " | " + df['Nama Barang'].astype(str)
            
            # Show options in reverse order (newest first)
            options = df['display_label'].tolist()[::-1]
            
            selected_labels = st.multiselect(
                "Pilih data yang ingin dihapus (Semua Tanggal):",
                options=options
            )
            
            if st.button("🗑️ Hapus Data Terpilih"):
                if selected_labels:
                    try:
                        # Filter out selected rows
                        df_remaining = df[~df['display_label'].isin(selected_labels)].drop(columns=['display_label', 'Timestamp_dt'], errors='ignore')
                        
                        # Save back to file
                        if file_type == 'xlsx':
                            df_remaining.to_excel(user_file_xlsx, index=False)
                        elif file_type == 'csv':
                            df_remaining.to_csv(user_file_csv, index=False)
                            
                        st.success(f"✅ Berhasil menghapus {len(selected_labels)} data.")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Gagal menghapus: {e}")
                else:
                    st.warning("⚠️ Pilih minimal satu data untuk dihapus.")
    else:
        st.info(f"Belum ada data tersimpan untuk NIK {nik_str}.")
