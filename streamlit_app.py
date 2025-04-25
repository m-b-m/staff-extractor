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

    # TTBB hierarchy for boundary detection\    hierarchy = ['Tenor I', 'Tenor II', 'Bass I', 'Bass II']

    # Determine canonical label for boundary detection (first that matches hierarchy)
    canonical = None
    for hl in hierarchy:
        if hl in voice_labels:
            canonical = hl
            break

    # Prepare extraction
    page_out = dst.new_page(width=w, height=h)
    y_off = margin_pt

    for i in range(len(src)):
        page = src[i]
        # find voice label occurrence
        instances = None
        for lbl in voice_labels:
            inst = page.search_for(lbl)
            if inst:
                instances = inst
                canonical_lbl = lbl
                break
        if not instances:
            continue
        t = instances[0]
        # boundary detection using canonical hierarchy
        b_list = []
        if canonical:
            try:
                idx = hierarchy.index(canonical)
                next_lbl = hierarchy[idx+1]
                b_list = page.search_for(next_lbl)
            except (ValueError, IndexError):
                b_list = []

        # compute original clip
        y0_orig = max(0, t.y0 - margin_pt - shift)
        y1_orig = b_list[0].y0 - shift if b_list else t.y1 + mm_to_pt(100) - shift

        # center and shrink
        center = (y0_orig + y1_orig) / 2
        half_h = (y1_orig - y0_orig - shrink) / 2
        y0 = center - half_h
        y1 = center + half_h

        clip = fitz.Rect(0, y0, page.rect.width, y1)
        scale = (w - 2 * margin_pt) / page.rect.width
        sh = (y1 - y0) * scale

        # new A4 page if needed
        if y_off + sh > h - margin_pt:
            page_out = dst.new_page(width=w, height=h)
            y_off = margin_pt

        dest = fitz.Rect(margin_pt, y_off,
                         margin_pt + (w - 2 * margin_pt),
                         y_off + sh)
        page_out.show_pdf_page(dest, src, i, clip=clip)
        y_off += sh + margin_pt

    # return PDF bytes\    buf = io.BytesIO()
    dst.save(buf)
    return buf.getvalue()

# Streamlit UI
st.title('TTBB Voice Extractor & A4 Stacker')

uploaded_file = st.file_uploader('Upload TTBB Score PDF', type=['pdf'])
voice_input = st.text_input('Voice Labels (comma-separated)', value='Tenor II')

# parse labelsoice_labels = [v.strip() for v in voice_input.split(',') if v.strip()]

col1, col2, col3 = st.columns(3)
with col1:
    shift_mm = st.number_input('Shift Up (mm)', 0.0, 100.0, 5.0)
with col2:
    shrink_mm = st.number_input('Shrink Height (mm)', 0.0, 100.0, 5.0)
with col3:
    margin_pt = st.number_input('Margin (pt)', 0.0, 200.0, 20.0)

if uploaded_file and st.button('Extract & Generate PDF'):
    with st.spinner('Processing...'):
        inp = uploaded_file.read()
        outp = extract_voice(inp, voice_labels, shift_mm, shrink_mm, margin_pt)
    st.success('Done! Download below.')
    st.download_button('Download Extracted PDF', data=outp,
                       file_name='extracted_' + '_'.join([v.replace(' ', '_') for v in voice_labels]) + '.pdf',
                       mime='application/pdf')
