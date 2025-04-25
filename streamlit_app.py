import streamlit as st
import fitz  # PyMuPDF
import io

# Convert mm to points
def mm_to_pt(mm):
    return mm * 72 / 25.4

# Core extraction function
def extract_voice(input_bytes, voice_labels, shift_mm, shrink_mm, margin_pt):
    # voice_labels: list of strings to match exactly
    src = fitz.open(stream=input_bytes, filetype='pdf')
    dst = fitz.open()
    a4 = fitz.paper_rect('a4')
    w, h = a4.width, a4.height
    shift = mm_to_pt(shift_mm)
    shrink = mm_to_pt(shrink_mm)

    # TTBB hierarchy for boundary detection
    hierarchy = ['Tenor I', 'Tenor II', 'Bass I', 'Bass II']

    # Determine canonical label for boundary detection (first that matches hierarchy)
    canonical = None
    for hl in hierarchy:
        if hl in voice_labels:
            canonical = hl
            break

    # Initialize output page and offset
    current_page = dst.new_page(width=w, height=h)
    y_offset = margin_pt

    # Process each source page
    for page_num in range(len(src)):
        page = src[page_num]
        # find voice label occurrence
        instances = None
        for lbl in voice_labels:
            inst = page.search_for(lbl)
            if inst:
                instances = inst
                break
        if not instances:
            continue
        t = instances[0]

        # Boundary detection using hierarchy
        b_list = []
        if canonical:
            try:
                idx = hierarchy.index(canonical)
                next_lbl = hierarchy[idx + 1]
                b_list = page.search_for(next_lbl)
            except (ValueError, IndexError):
                b_list = []

        # Compute original clip region
        y0_orig = max(0, t.y0 - margin_pt - shift)
        if b_list:
            y1_orig = b_list[0].y0 - shift
        else:
            y1_orig = t.y1 + mm_to_pt(100) - shift

        # Center and shrink
        center_y = (y0_orig + y1_orig) / 2
        half_h_new = (y1_orig - y0_orig - shrink) / 2
        y0 = center_y - half_h_new
        y1 = center_y + half_h_new

        clip = fitz.Rect(0, y0, page.rect.width, y1)
        scale = (w - 2 * margin_pt) / page.rect.width
        scaled_h = (y1 - y0) * scale

        # Start new A4 page if needed
        if y_offset + scaled_h > h - margin_pt:
            current_page = dst.new_page(width=w, height=h)
            y_offset = margin_pt

        # Place clipped content
        dest_rect = fitz.Rect(margin_pt, y_offset,
                              margin_pt + (w - 2 * margin_pt),
                              y_offset + scaled_h)
        current_page.show_pdf_page(dest_rect, src, page_num, clip=clip)
        y_offset += scaled_h + margin_pt

    # Return PDF bytes
    buf = io.BytesIO()
    dst.save(buf)
    return buf.getvalue()

# Streamlit UI
st.title('TTBB Voice Extractor & A4 Stacker')

uploaded_file = st.file_uploader('Upload TTBB Score PDF', type=['pdf'])
voice_input = st.text_input('Voice Labels (comma-separated)', value='Tenor II')

# Parse labels
voice_labels = [v.strip() for v in voice_input.split(',') if v.strip()]

col1, col2, col3 = st.columns(3)
with col1:
    shift_mm = st.number_input('Shift Up (mm)', 0.0, 100.0, 5.0)
with col2:
    shrink_mm = st.number_input('Shrink Height (mm)', 0.0, 100.0, 5.0)
with col3:
    margin_pt = st.number_input('Margin (pt)', 0.0, 200.0, 20.0)

if uploaded_file and st.button('Extract & Generate PDF'):
    with st.spinner('Processing...'):
        input_bytes = uploaded_file.read()
        output_bytes = extract_voice(input_bytes, voice_labels, shift_mm, shrink_mm, margin_pt)
    st.success('Done! Download below.')
    st.download_button('Download Extracted PDF',
                       data=output_bytes,
                       file_name='extracted_' + '_'.join([v.replace(' ', '_') for v in voice_labels]) + '.pdf',
                       mime='application/pdf')
