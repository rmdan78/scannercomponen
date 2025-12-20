import pandas as pd
import os
import csv

file_path = 'data_general.csv'
new_header = ["Timestamp", "NIK Operator", "Nama Operator", "Component Number", "Nama Barang", "Quantity", "Image Name"]
rows = []

if os.path.exists(file_path):
    with open(file_path, 'r') as f:
        lines = f.readlines()
        
    for line in lines[1:]: # Skip old header
        parts = line.strip().split(',')
        if len(parts) < 5: continue
        
        # Normalize to 7 columns
        # 5 cols: Time, NIK, Comp, Qty, Img
        # 6 cols: Time, NIK, Comp, ItemName, Qty, Img
        # 7 cols: Time, NIK, Name, Comp, ItemName, Qty, Img
        
        new_row = []
        if len(parts) == 5:
            new_row = [parts[0], parts[1], "", parts[2], "", parts[3], parts[4]]
        elif len(parts) == 6:
            new_row = [parts[0], parts[1], "", parts[2], parts[3], parts[4], parts[5]]
        elif len(parts) >= 7:
            new_row = parts[:7] # Take first 7
            
        rows.append(new_row)

    # Write back
    with open(file_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(new_header)
        writer.writerows(rows)
    
    print("Fixed CSV file.")
else:
    print("File not found.")
