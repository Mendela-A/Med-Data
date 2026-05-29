import re

html_path = r"c:\Users\mendela.a\Documents\python_work_projects\test\templates\statisty\form016.html"

with open(html_path, "r", encoding="utf-8") as f:
    content = f.read()

# Extract the table header between <thead> and </thead>
match = re.search(r"<thead>(.*?)</thead>", content, re.DOTALL)
if not match:
    print("Could not find thead")
    exit(1)

thead_content = match.group(1)

# Let's count rows and cells in each row
rows = re.findall(r"<tr>(.*?)</tr>", thead_content, re.DOTALL)
print(f"Total header rows: {len(rows)}")

for idx, r in enumerate(rows, 1):
    cells = re.findall(r"<th(.*?)>(.*?)</th>", r, re.DOTALL)
    if not cells:
        cells = re.findall(r"<td(.*?)>(.*?)</td>", r, re.DOTALL)
        type_str = "TD"
    else:
        type_str = "TH"
    print(f"\nRow {idx} ({type_str}) has {len(cells)} cells:")
    for c_attr, c_text in cells:
        clean_text = re.sub(r"\s+", " ", c_text).strip()
        rowspan = re.search(r'rowspan="(\d+)"', c_attr)
        colspan = re.search(r'colspan="(\d+)"', c_attr)
        rowspan_val = int(rowspan.group(1)) if rowspan else 1
        colspan_val = int(colspan.group(1)) if colspan else 1
        print(f"  - '{clean_text}' [rowspan={rowspan_val}, colspan={colspan_val}]")
