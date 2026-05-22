import re
import os
from bs4 import BeautifulSoup
from pathlib import Path

def extract_text_from_html(file_path):
    # 1. Read the HTML file
    with open(file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()

    # 2. Parse the HTML
    soup = BeautifulSoup(html_content, 'html.parser')

    # 3. Destroy all script and style tags
    for unwanted_tag in soup(["script", "style", "meta", "head", "noscript"]):
        unwanted_tag.extract()

    # 4. Format headings to stand out in the plain text
    for i in range(1, 7):
        for heading in soup.find_all(f'h{i}'):
            heading_text = heading.get_text(strip=True)
            if heading_text:
                heading.replace_with(f"\n\n{'#' * i} {heading_text.upper()}\n\n")

    # 5. Extract the remaining text, using newlines to separate elements
    text = soup.get_text(separator='\n')

    # 6. Clean up the output
    cleaned_text = re.sub(r'\n{3,}', '\n\n', text).strip()

    return cleaned_text

if __name__ == "__main__":
    
    # Define your folders using pathlib
    input_folder = Path('release_notes/release_notes_html')
    output_folder = Path('release_notes/release_notes_text')
    
    # Ensure the output folder exists
    output_folder.mkdir(parents=True, exist_ok=True)
    
    # Check if input directory exists
    if not input_folder.is_dir():
        print(f"❌ Error: The input folder '{input_folder}' does not exist.")
    else:
        # Grab all HTML files
        html_files = list(input_folder.glob('*.html'))
        
        if not html_files:
            print(f"⚠️ No HTML files found in '{input_folder}'.")
        else:
            print(f"Found {len(html_files)} files. Starting extraction...\n")
            
            for html_file in html_files:
                print(f"Processing: {html_file.name}")
                
                try:
                    # 1. Extract the text
                    plain_text = extract_text_from_html(html_file)
                    
                    # 2. Clean the filename (Remove emojis/non-ASCII characters)
                    # r'[^\x00-\x7F]+' matches any character that is NOT standard ASCII text
                    clean_stem = re.sub(r'[^\x00-\x7F]+', '', html_file.stem).strip()
                    
                    # 3. Construct the output file path using the cleaned stem
                    output_file_path = output_folder / f"{clean_stem}.txt"
                    
                    # 4. Save the result
                    with open(output_file_path, 'w', encoding='utf-8') as out_file:
                        out_file.write(plain_text)
                        
                    print(f"  ✅ Saved: {output_file_path.name}")
                        
                except Exception as e:
                    print(f"  ❌ Error processing {html_file.name}: {e}")
            
            print("\n🎉 All files processed successfully!")