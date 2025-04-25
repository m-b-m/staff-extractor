import streamlit as st
import fitz  # PyMuPDF for PDF processing

st.title("🎼 Staff Extractor")
st.write("Upload a PDF of sheet music and specify a staff label to extract.")

# File uploader for the PDF
uploaded_file = st.file_uploader("Choose a PDF file", type=["pdf"])
# Text input (or select box) for the staff label
label = st.text_input("Staff label (e.g., Bass I, Tenor II, etc.)").strip()

if uploaded_file and label:
    try:
        # Load the PDF with PyMuPDF
        pdf_doc = fitz.open(stream=uploaded_file.read(), filetype="pdf")
    except Exception as e:
        st.error(f"Error loading PDF: {e}")
        st.stop()
    
    output_pdf = fitz.open()  # New PDF to collect extracted staff segments
    
    # Loop through each page of the PDF
    for page_index in range(pdf_doc.page_count):
        page = pdf_doc.load_page(page_index)
        page_text = page.get_text("dict")  # get structured text (dict with blocks, lines)
        
        # Find all text lines on this page that look like staff labels (left margin lines)
        label_lines = []
        for block in page_text["blocks"]:
            for line in block["lines"]:
                # Combine all spans in the line to get full text
                line_text = "".join(span["text"] for span in line["spans"]).strip()
                # Consider this line a label if it contains letters and is near the left margin
                if line_text and any(ch.isalpha() for ch in line_text) and line["bbox"][0] < 100:
                    label_lines.append((line_text, line["bbox"]))
        # Sort lines by their vertical position (top y-coordinate)
        label_lines.sort(key=lambda x: x[1][1])
        
        # Find occurrences of the exact label on this page
        occurrences = [ (text, bbox) for (text, bbox) in label_lines if text == label ]
        if not occurrences:
            continue  # skip this page if label not present as a full line
        
        # If the label appears, determine vertical regions for each occurrence
        for idx, (text, bbox) in enumerate(label_lines):
            if text != label:
                continue  # skip lines that are not the target label
            
            # Determine the vertical boundaries for the staff region around this label
            top_y = bbox[1]
            bottom_y = bbox[3]
            
            # Find the previous label (above) and next label (below) in the sorted label list
            prev_label = label_lines[idx-1][1] if idx > 0 else None
            next_label = label_lines[idx+1][1] if idx < len(label_lines) - 1 else None
            
            # Adjust top boundary: if there is a label above, use its bottom as the top cut (to exclude above staff)
            if prev_label:
                top_y = prev_label[3]
            else:
                top_y = 0  # no label above, start from page top
            
            # Adjust bottom boundary: if there is a label below, use its top as the bottom cut (to exclude below staff)
            if next_label:
                bottom_y = next_label[1]
            else:
                bottom_y = page.rect.y1  # no label below, use page bottom
            
            # Optionally, add a small margin above and below to ensure full capture
            margin = 5.0  # in points, expand region slightly
            top_y = max(0, top_y - margin)
            bottom_y = min(page.rect.y1, bottom_y + margin)
            
            # Define the rectangle region for the staff on this page
            staff_region = fitz.Rect(0, top_y, page.rect.width, bottom_y)
            
            # Extract the region as a new page in the output PDF
            new_page = output_pdf.new_page(width=staff_region.width, height=staff_region.height)
            new_page.show_pdf_page(new_page.rect, pdf_doc, page_index, clip=staff_region)
    
    # Offer the output PDF for download if any pages were added
    if output_pdf.page_count > 0:
        pdf_bytes = output_pdf.write()  # get the PDF content as bytes
        st.success(f"Extracted staff '{label}' from the PDF.")
        st.download_button(
            label="📥 Download Extracted Staves PDF",
            data=pdf_bytes,
            file_name=f"{label}_staves.pdf",
            mime="application/pdf"
        )
    else:
        st.warning(f"No staves labeled '{label}' were found in the document.")
