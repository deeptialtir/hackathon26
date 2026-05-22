import csv
import re
import os
from pathlib import Path

def parse_release_notes(input_text):
    # (The existing parsing logic remains exactly the same as your script above)
    text = input_text
    text = re.sub(r'\n\s*:\s*', ' : ', text)
    text = re.sub(r'\n\s*&\s*', ' & ', text)
    text = re.sub(r'\n\s*(@\w)', r' \1', text)
    text = re.sub(r'-\s*\n\s*', '- ', text)
    text = re.sub(r'\n\s*(Verified|Not sync)', r' - \1', text, flags=re.IGNORECASE)
    text = re.sub(r'\n\s*(Link)', r' - \1', text, flags=re.IGNORECASE)
    text = re.sub(r'\n\s*(https?://[^\s]+)', r' \1', text)
    
    lines = [line.strip() for line in text.split('\n') if line.strip()]

    records = []
    current_section = "Metadata"
    current_category = "General"
    category_owner = ""

    for line in lines:
        if re.match(r'^#\s*\d+', line): continue
        if '## LIST OF DEPLOYED ITEMS' in line:
            current_section = "Deployed Items"; current_category = "General"; continue
        if '### OPEN ISSUES ON STAGE:' in line:
            current_section = "Open Issues - Stage"; current_category = "Issues"; continue
        if '## ISSUES FOUND ON PROD:' in line:
            current_section = "Issues - Prod"; current_category = "Issues"; continue
        if 'Components Involved' in line:
            current_section = "Artefacts"; continue

        if current_section in ["Metadata", "Artefacts"]:
            if ':' in line:
                parts = line.split(':', 1)
                records.append({'Section': current_section, 'Category': 'Release Info' if current_section == 'Metadata' else 'Artefacts', 'Item_Description': parts[0].strip(), 'Status_Value': parts[1].strip(), 'Owner': '', 'Links': ''})
            elif records and records[-1]['Section'] == current_section:
                records[-1]['Status_Value'] += f" {line}"
        elif current_section == "Deployed Items":
            if ':' in line:
                prefix, suffix = [p.strip() for p in line.split(':', 1)]
                if len(prefix.split()) <= 4:
                    current_category = prefix
                    cat_owners = re.findall(r'@[\w]+(?:\s+[\w]+)?', suffix)
                    category_owner = ", ".join([o.strip() for o in cat_owners]) if cat_owners else ""
                    if len(suffix) > 10 and not suffix.startswith('- @'): line = suffix
                    else: continue
            links = re.findall(r'https?://[^\s]+', line)
            link_str = ", ".join(links)
            line = re.sub(r'https?://[^\s]+', '', line)
            owners = re.findall(r'@[\w]+(?:\s+[\w]+)?', line)
            owner_str = ", ".join([o.strip() for o in owners])
            line = re.sub(r'@[\w]+(?:\s+[\w]+)?', '', line)
            line = re.sub(r'[:-]?\s*Link\s*$', '', line, flags=re.IGNORECASE).strip()
            status_match = re.search(r'(?:-[\s-]*)?(Verified.*|Not sync.*|No change.*)$', line, re.IGNORECASE)
            status = status_match.group(1).strip(' -') if status_match else ""
            line = line[:status_match.start()] if status_match else line
            desc = line.strip(' -')
            if desc:
                if not desc[0].isupper() and not status and not owner_str and not link_str and records and records[-1]['Section'] == current_section:
                    records[-1]['Item_Description'] += f"\n{desc}"
                else:
                    records.append({'Section': current_section, 'Category': current_category, 'Item_Description': desc, 'Status_Value': status, 'Owner': owner_str if owner_str else category_owner, 'Links': link_str})
        elif current_section in ["Open Issues - Stage", "Issues - Prod"]:
            links = re.findall(r'https?://[^\s]+', line)
            link_str = ", ".join(links)
            line_clean = re.sub(r'https?://[^\s]+', '', line)
            owner_match = re.search(r'-\s*([A-Z][a-z]+ [A-Z][a-z]+)\s*$', line_clean)
            owner = owner_match.group(1).strip() if owner_match else ""
            line_clean = re.sub(r'[:-]?\s*Link.*$', '', re.sub(r'-\s*([A-Z][a-z]+ [A-Z][a-z]+)\s*$', '', line_clean), flags=re.IGNORECASE).strip(' -:')
            if line_clean:
                records.append({'Section': current_section, 'Category': current_category, 'Item_Description': line_clean, 'Status_Value': 'Open', 'Owner': owner, 'Links': link_str})
    return records

def generate_csv(records, output_path):
    headers = ['Section', 'Category', 'Item_Description', 'Status_Value', 'Owner', 'Links']
    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)

if __name__ == '__main__':
    input_dir = Path('release_notes/release_notes_text')
    output_dir = Path('release_notes/release_notes_csv')
    output_dir.mkdir(parents=True, exist_ok=True)

    txt_files = list(input_dir.glob('*.txt'))
    if not txt_files:
        print(f"⚠️ No text files found in {input_dir}")
    else:
        for txt_file in txt_files:
            print(f"Processing: {txt_file.name}")
            with open(txt_file, 'r', encoding='utf-8') as f:
                raw_data = f.read()
            
            records = parse_release_notes(raw_data)
            output_csv = output_dir / f"{txt_file.stem}.csv"
            generate_csv(records, output_csv)
            print(f"  ✅ Saved to {output_csv}")