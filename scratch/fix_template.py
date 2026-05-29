import os

filepath = r"C:\Users\mendela.a\Documents\python_work_projects\test\templates\statisty\form016.html"

# Read the file as bytes
with open(filepath, 'rb') as f:
    data = f.read()

print("Original size:", len(data))

# The byte representation of "виписо" in UTF-8
# в = \xd0\xb2
# и = \xd0\xb8
# п = \xd0\xbf
# и = \xd0\xb8
# с = \xd1\x81
# о = \xd0\xbe
# then we had \xd0 followed by '{% if table %}'
target = b'\xd0\xb2\xd0\xb8\xd0\xbf\xd0\xb8\xd1\x81\xd0\xbe\xd0'
replacement = 'виписок</strong>.</div>\n{% endif %}\n'.encode('utf-8')

idx = data.find(target)
if idx != -1:
    print("Found target at index:", idx)
    # Reconstruct the text up to the idx, add replacement, then keep the rest
    part1 = data[:idx]
    # The rest starts with '{% if table %}' which is right after 'target' (since target has the corrupt \xd0 byte)
    part2 = data[idx + len(target):]
    new_data = part1 + replacement + part2
else:
    print("Target not found directly, trying string replacement with replace handler")
    # Decode with replace, replace the character, and encode back
    text = data.decode('utf-8', errors='replace')
    text = text.replace('виписо', 'виписок</strong>.</div>\n{% endif %}\n')
    new_data = text.encode('utf-8')

# Now let's find the first '{% endblock %}' that is after the 'Немає записів за обраний період.' block
text = new_data.decode('utf-8')
end_marker = "Немає записів за обраний період.\n</div>\n{% endif %}\n{% endblock %}"
marker_idx = text.find(end_marker)

if marker_idx != -1:
    print("Found end marker at index:", marker_idx)
    final_text = text[:marker_idx + len(end_marker)]
else:
    # If the exact whitespace varies, let's search for the first occurrence of '{% endblock %}' after the tables/rules
    # We know the first block has:
    # </ul>\n</div>\n\n{% else %}\n<div class=\"alert alert-secondary\">\n  <i class=\"bi bi-inbox me-2\"></i>Немає записів за обраний період.\n</div>\n{% endif %}\n{% endblock %}"
    first_endblock = text.find("{% endblock %}", text.find("Правила агрегації"))
    if first_endblock != -1:
        # We want to keep everything up to this {% endblock %} plus 14 characters for '{% endblock %}'
        final_text = text[:first_endblock + len("{% endblock %}")]
        print("Found first block end at index:", first_endblock)
    else:
        print("Could not find appropriate end block!")
        final_text = text

# Write the cleaned file back in UTF-8
with open(filepath, 'w', encoding='utf-8') as f:
    f.write(final_text)

print("Cleaned file written. New size:", len(final_text.encode('utf-8')))
