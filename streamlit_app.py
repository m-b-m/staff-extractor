import streamlit as st
import fitz  # PyMuPDF
import io

# Convert mm to points
def mm_to_pt(mm):
    return mm * 72 / 25.4

# Core extraction function
def extract_voice(input_bytes, voice_label, shift_mm, shrink_mm, margin_pt):
    src = fitz.open(stream=input_bytes, filetype='pdf')
    dst = fitz.open()
    a4 = fitz.paper_rect('a4')
    w, h = a4.width, a4.height
    shift = mm_to_pt(shift_mm)
    shrink = mm_to_pt(shrink_mm)
    page_out = dst.new_page(width=w, height=h)
    y_off = margin_pt
    hierarchy = ['Tenor I', 'Tenor II', 'Bass I', 'Bass II']
    for i in range(len(src)):
        pg = src[i]
        parts = voice_label.split(' ', 1)
        if len(parts) == 2:
            fw, sv = parts
        else:
            fw = voice_label; sv = ''
        syns = [voice_label, f'{fw}. {sv}', f'{fw} {sv}', voice_label.replace(' ', '. ')]
        if len(fw) > 3:
            ab = fw[:3]
            syns += [f'{ab} {sv}', f'{ab}. {sv}']
        syns = list(dict.fromkeys(syns))
        inst = None
        for lbl in syns:
            inst = pg.search_for(lbl)
            if inst: break
        if not inst: continue
        t = inst[0]
        b_list = []
        try:
            idx = hierarchy.index(voice_label)
            nl = hierarchy[idx + 1]
            parts_n = nl.split(' ', 1)
            if len(parts_n) == 2:
                fw2, sv2 = parts_n
            else:
                fw2 = nl; sv2 = ''
            syns_n = [nl, f'{fw2}. {sv2}', f'{fw2} {sv2}', nl.replace(' ', '. ')]
            if len(fw2) > 3:
                ab2 = fw2[:3]
                syns_n += [f'{ab2} {sv2}', f'{ab2}. {sv2}']
            syns_n = list(dict.fromkeys(syns_n))
            for lbl2 in syns_n:
                bl = pg.search_for(lbl2)
                if bl:
                    b_list = bl; break
        except:
            b_list = []
        y0 = max(0, t.y0 - margin_pt - shift)
        y1 = b_list[0].y0 - shift if b_list else t.y1 + mm_to_pt(100) - shift
        center = (y0 + y1) / 2
        half_h = (y1 - y0 - shrink) / 2
        y0n = center - half_h; y1n = center + half_h
        clip = fitz.Rect(0, y0n, pg.rect.width, y1n)
        scale = (w - 2 * margin_pt) / pg.rect.width
        sh = (y1n - y0n) * scale
        if y_off + sh > h - margin_pt:
            page_out = dst.new_page(width=w, height=h)
            y_off = margin_pt
        dest = fitz.Rect(margin_pt, y_off, margin_pt + (w - 2 * margin_pt), y_off + sh)
        page_out.show_pdf_page(dest, src, i, clip=clip)
        y_off += sh + margin_pt
    buf = io.BytesIO()
    dst.save(buf)
    return buf.getvalue()

st.title('TTBB Voice Extractor & A4 Stacker')
uploaded_file = st.file_uploader('Upload TTBB Score PDF', type=['pdf'])
voice_label = st.text_input('Voice Label', value='Tenor II')
c1, c2, c3 = st.columns(3)
with c1:
    shift_mm = st.number_input('Shift Up (mm)', 0.0, 100.0, 5.0)
with c2:
    shrink_mm = st.number_input('Shrink Height (mm)', 0.0, 100.0, 5.0)
with c3:
    margin_pt = st.number_input('Margin (pt)', 0.0, 200.0, 20.0)
if uploaded_file and st.button('Extract & Generate PDF'):
    with st.spinner('Processing...'):
        inp = uploaded_file.read()
        outp = extract_voice(inp, voice_label, shift_mm, shrink_mm, margin_pt)
    st.success('Done! Download below.')
    st.download_button('Download Extracted PDF', data=outp, file_name=voice_label.replace(' ', '_') + '.pdf', mime='application/pdf')
