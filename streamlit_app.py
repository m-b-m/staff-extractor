import re
import io
import fitz  # PyMuPDF
import streamlit as st

st.title("Staff System Extractor")

# File uploader for PDF
uploaded_file = st.file_uploader("Upload a music PDF", type=["pdf"])
if uploaded_file is not None:
    try:
        # Load PDF into PyMuPDF document
        pdf_data = uploaded_file.read()
        doc = fitz.open(stream=pdf_data, filetype="pdf")
    except Exception as e:
        st.error(f"Error opening PDF: {e}")
    else:
        # User input for labels (comma-separated)
        labels_input = st.text_input("Enter staff labels to extract (comma-separated)", "")
        if labels_input:
            # Prepare label list and normalized set for matching
            label_list = [lbl.strip() for lbl in labels_input.split(",") if lbl.strip()]
            norm_labels = { re.sub(r"[^A-Za-z0-9]", "", lbl).lower() for lbl in label_list }
            
            # Find all candidate labels near left margin
            left_margin_threshold = 50  # points (approx 0.7 inches) for left-aligned labels
            all_labels = []  # will hold tuples (page_number, top_y, bottom_y, text)
            for page_index in range(doc.page_count):
                page = doc[page_index]
                blocks = page.get_text("dict")["blocks"]
                for block in blocks:
                    if block.get("type") == 0:  # text block
                        for line in block.get("lines", []):
                            x0, y0, x1, y1 = line["bbox"]
                            text = "".join(span["text"] for span in line["spans"]).strip()
                            if not text:
                                continue
                            # Check if text is near left and contains letters (likely a label)
                            if x0 < left_margin_threshold and re.search("[A-Za-z]", text):
                                # Exclude obvious non-label lines (composer, title, etc.)
                                if any(kw in text for kw in ["Words and Music by", "Arr.", "From "]):
                                    continue
                                all_labels.append((page_index + 1, y0, y1, text))
            # Sort labels by page and vertical position
            all_labels.sort(key=lambda t: (t[0], t[1]))
            
            # Filter for target labels
            target_labels = [lab for lab in all_labels 
                             if re.sub(r"[^A-Za-z0-9]", "", lab[3]).lower() in norm_labels]
            
            if not target_labels:
                st.warning("No staff systems found for the given labels.")
            else:
                # Prepare a new PDF for output
                output_doc = fitz.open()
                page_width, page_height = doc[0].rect.width, doc[0].rect.height
                # Define layout parameters for output pages
                top_margin = 10  # points
                bottom_margin = 10
                vertical_gap = 5   # gap between cropped images on output page
                # Use a matrix to scale images (for better resolution)
                zoom_factor = 2.0  # 2x zoom for higher DPI output
                mat = fitz.Matrix(zoom_factor, zoom_factor)
                
                y_cursor = 0
                output_page = None
                
                # Helper function to add a new blank page to output_doc
                def add_output_page():
                    return output_doc.new_page(width=page_width, height=page_height)
                
                # Iterate through each target label and crop the corresponding region
                prev_page = None
                for (page_num, label_y_top, label_y_bottom, label_text) in target_labels:
                    page = doc[page_num - 1]
                    # Determine crop top boundary
                    if prev_page != page_num:  # new page in original PDF
                        # If this label is first on its page (no previous label on same page)
                        # include a small margin above
                        top_crop = max(0, label_y_top - 20)
                    else:
                        # Not the first label on page – start exactly at this label
                        top_crop = label_y_top
                    prev_page = page_num
                    # Determine crop bottom boundary (either next label or fallback height)
                    # Find the next label on the same page
                    next_label = next((lab for lab in all_labels 
                                       if lab[0] == page_num and lab[1] > label_y_top), None)
                    if next_label:
                        bottom_crop = next_label[1]  # top Y of the next label
                    else:
                        # No next label on this page: extend a fixed fallback height
                        bottom_crop = min(page.rect.height, label_y_top + 120)
                    
                    # Clip and render the region to an image (pixmap)
                    clip_rect = fitz.Rect(0, top_crop, page_width, bottom_crop)
                    pix = page.get_pixmap(matrix=mat, clip=clip_rect)
                    img_height_points = pix.height / zoom_factor  # height in points at original scale
                    
                    # Start a new output page if needed
                    if output_page is None or y_cursor + img_height_points > page_height - bottom_margin:
                        output_page = add_output_page()
                        y_cursor = top_margin
                    # Compute target rectangle on output page and insert the image
                    target_rect = fitz.Rect(0, y_cursor, page_width, y_cursor + img_height_points)
                    output_page.insert_image(target_rect, pixmap=pix)
                    # Update cursor for next image position
                    y_cursor += img_height_points + vertical_gap
                
                # Save output PDF to memory and provide download
                output_pdf_bytes = output_doc.save(inplace=False, garbage=4)  # compress and save
                st.success(f"Extraction complete! Extracted {len(target_labels)} staff systems.")
                st.download_button(
                    label="Download Extracted PDF",
                    data=output_pdf_bytes,
                    file_name="extracted_staves.pdf",
                    mime="application/pdf"
                )
