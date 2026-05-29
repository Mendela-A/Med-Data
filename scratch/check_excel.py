import sys
import openpyxl

sys.stdout.reconfigure(encoding='utf-8')

wb = openpyxl.load_workbook(r"C:\Users\mendela.a\Downloads\04_data.xlsx", data_only=True)
sheet = wb['01']
for r in range(1, 100):
    row_vals = [sheet.cell(row=r, column=c).value for c in range(1, 21)]
    # filter out rows that are entirely empty
    if any(x is not None for x in row_vals):
        print(f"Row {r:02d}: {row_vals}")
