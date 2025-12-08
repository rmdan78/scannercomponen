try:
    import streamlit
    print("Streamlit: OK")
except ImportError as e:
    print(f"Streamlit: FAIL ({e})")

try:
    import pandas
    print("Pandas: OK")
except ImportError as e:
    print(f"Pandas: FAIL ({e})")

try:
    import easyocr
    print("EasyOCR: OK")
except ImportError as e:
    print(f"EasyOCR: FAIL ({e})")

try:
    import cv2
    print("OpenCV: OK")
except ImportError as e:
    print(f"OpenCV: FAIL ({e})")

try:
    import openpyxl
    print("OpenPyXL: OK")
except ImportError as e:
    print(f"OpenPyXL: FAIL ({e})")
