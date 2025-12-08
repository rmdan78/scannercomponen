import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os

def test_connection():
    print("--- MULAI TEST KONEKSI GOOGLE SHEETS ---")
    
    # 1. Cek File Credentials
    cred_file = 'Credentials.json'
    if not os.path.exists(cred_file):
        cred_file = 'credentials.json' # Coba lowercase
        
    if not os.path.exists(cred_file):
        print("❌ ERROR: File Credentials.json TIDAK DITEMUKAN!")
        return

    print(f"✅ File credential ditemukan: {cred_file}")

    # 2. Cek Dependencies & Scope
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    
    try:
        # 3. Auth
        print("⏳ Mencoba otentikasi dengan Google...")
        creds = ServiceAccountCredentials.from_json_keyfile_name(cred_file, scope)
        client = gspread.authorize(creds)
        print("✅ Otentikasi BERHASIL!")
        print(f"   Email Service Account: {creds.service_account_email}")
        
        # 4. Open Sheet
        sheet_name = "Data Scan"
        print(f"⏳ Mencoba membuka spreadsheet: '{sheet_name}'...")
        
        try:
            sheet = client.open(sheet_name).sheet1
            print("✅ BERHASIL MEMBUKA SHEET!")
            print(f"   Judul: {sheet.title}")
            print(f"   Jumlah Baris: {sheet.row_count}")
            
            # 5. Try Write
            print("⏳ Menulis baris tes...")
            sheet.append_row(["Tes", "Koneksi", "Berhasil"])
            print("✅ BERHASIL MENULIS DATA!")
            
        except gspread.SpreadsheetNotFound:
            print(f"❌ ERROR: Spreadsheet '{sheet_name}' TIDAK DITEMUKAN.")
            print("   SOLUSI: Pastikan nama file Google Sheet persis 'Data Scan' (tanpa kutip).")
            print("   SOLUSI: Pastikan sudah di-SHARE ke email service account di atas.")
            
    except Exception as e:
        print(f"❌ ERROR UTAMA: {e}")
        print("   Tips: Pastikan 'Google Sheets API' dan 'Google Drive API' sudah ENABLE di Google Cloud Console.")

if __name__ == "__main__":
    test_connection()
