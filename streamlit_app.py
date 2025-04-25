import streamlit as st
import fitz  # PyMuPDF
import io

# Convert millimeters to points
def mm_to_pt(mm):
    return mm * 72 / 25.4

# Core extraction function
# voice_labels: list of exact labels to search (e.g. ['Tenor II', 'Ten II'])
def extract_voice(input_bytes, voice_labels, shift_mm, shrink_mm, margin_pt):
    # Open source PDF from bytes
    src = fitz.open(stream=input_bytes, filetype='pdf')
    dst = fitz.open()
    a4 = fitz.paper_rect('a4')
    w, h = a4.width, a4.height
    shift = mm_to_pt(shift_mm)
    shrink = mm_to_pt(shrink_mm)

    # Hierarchy for boundary detection
    hierarchy = ['Tenor I', 'Tenor II', 'Bass I', 'Bass II']
    # Choose first matching canonical label in hierarchy
    canonical = next((hl for hl in hierarchy if hl in voice_labels), None)

    # Start first output page
    current_page = dst.new_page(width=w, height=h)
    y_offset = margin_pt

    # Iterate through all pages
    for page_num in range(len(src)):
        page = src[page_num]
        # Find any of the voice labels on the page
        instances = None
        for lbl in voice_labels:
            inst = page.search_for(lbl)
            if not inst:
                # also try variant with a dot after first word
                dot_lbl = lbl.replace(' ', '. ')  
                inst = page.search_for(dot_lbl)
            if inst:
                instances = inst
                break
        if not instances:
            continue
        t = instances[0]

        # Determine bottom boundary via next label in hierarchy
        b_list = []
        if canonical:
            try:
                idx = hierarchy.index(canonical)
                next_lbl = hierarchy[idx + 1]
                b_list = page.search_for(next_lbl)
            except (ValueError, IndexError):
                b_list = []

        y0 = max(0, t.y0 - margin_pt - shift)
        if b_list:
            y1 = b_list[0].y0 - shift
        else:
            # fallback region if no next label
            y1 = t.y1 + mm_to_pt(100) - shift

        # Center and shrink the clip region by 'shrink'
        center_y = (y0 + y1) / 2
        half_h = (y1 - y0 - shrink) / 2
        y0_clip = center_y - half_h
        y1_clip = center_y + half_h

        clip = fitz.Rect(0, y0_clip, page.rect.width, y1_clip)
        scale = (w - 2 * margin_pt) / page.rect.width
        scaled_h = (y1_clip - y0_clip) * scale

        # If not enough space on current A4, start a new page
        if y_offset + scaled_h > h - margin_pt:
            current_page = dst.new_page(width=w, height=h)
            y_offset = margin_pt

        dest = fitz.Rect(margin_pt, y_offset,
                         margin_pt + (w - 2 * margin_pt),
                         y_offset + scaled_h)
        current_page.show_pdf_page(dest, src, page_num, clip=clip)
        y_offset += scaled_h + margin_pt

    # Save to bytes
    buf = io.BytesIO()
    dst.save(buf)
    return buf.getvalue()

# Streamlit UI
st.title('TTBB Voice Extractor & A4 Stacker')
uploaded_file = st.file_uploader('Upload TTBB Score PDF', type=['pdf'])
voice_input = st.text_input('Voice Labels (comma-separated)', value='Tenor II, Ten II')
# Parse input labels
voice_labels = [v.strip() for v in voice_input.split(',') if v.strip()]

# Parameter inputs
col1, col2, col3 = st.columns(3)
with col1:
    shift_mm = st.number_input('Shift Up (mm)', min_value=0.0, max_value=100.0, value=5.0)
with col2:
    shrink_mm = st.number_input('Shrink Height (mm)', min_value=0.0, max_value=100.0, value=5.0)
with col3:
    margin_pt = st.number_input('Margin (pt)', min_value=0.0, max_value=200.0, value=20.0)

# Extract button
def process():
    input_bytes = uploaded_file.read()
    return extract_voice(input_bytes, voice_labels, shift_mm, shrink_mm, margin_pt)

if uploaded_file and st.button('Extract & Generate PDF'):
    with st.spinner('Processing...'):
        pdf_bytes = process()
    st.success('Done! Download below.')
    st.download_button(
        'Download Extracted PDF',
        data=pdf_bytes,
        file_name='extracted_' + '_'.join([v.replace(' ', '_') for v in voice_labels]) + '.pdf',
        mime='application/pdf'
    )
