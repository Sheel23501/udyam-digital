"""Phone-shaped look for the customer journey: narrow column, Devanagari-capable font, no Streamlit chrome."""
import streamlit as st

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;600&family=Inter:wght@400;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stChatMessage, button, input, textarea, label {
  font-family: Inter, 'Noto Sans Devanagari', sans-serif;
}
.block-container { max-width: 440px; padding-top: 0.6rem; padding-bottom: 5rem; }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; height: 0; }
[data-testid="stChatMessage"] { border-radius: 16px; padding: 0.5rem 0.75rem; }
.brand { display:flex; align-items:center; gap:8px; margin-bottom:0.25rem; }
.brand .logo { width:30px; height:30px; border-radius:8px; background:#E40046; color:#fff; font-weight:700;
               display:flex; align-items:center; justify-content:center; font-size:15px; }
.brand .name { font-weight:700; font-size:1.05rem; letter-spacing:-0.01em; }
.steps { display:flex; gap:6px; margin:0.25rem 0 0.75rem 0; }
.steps span { flex:1; height:4px; border-radius:2px; background:#E5E7EB; }
.steps span.done { background:#E40046; }
.price { font-size: 2.2rem; font-weight: 700; color: #E40046; line-height: 1.1; }
.muted { color: #6B7280; font-size: 0.85rem; }
.item { display:flex; justify-content:space-between; gap:8px; padding:6px 0; border-bottom:1px solid #F1F2F4; }
.item .n { font-weight:600; }
.item .d { color:#6B7280; font-size:0.82rem; }
.item .p { white-space:nowrap; color:#374151; font-size:0.9rem; }
.pill { display:inline-block; padding:2px 10px; border-radius:999px; font-size:0.78rem; font-weight:600; }
.pill.pass { background:#DCFCE7; color:#166534; }  .pill.review { background:#FEF3C7; color:#92400E; }
.pill.fail { background:#FEE2E2; color:#991B1B; }  .pill.info { background:#E0E7FF; color:#3730A3; }
.check { display:flex; gap:10px; padding:8px 0; border-bottom:1px solid #F1F2F4; align-items:flex-start; }
.check .ic { font-size:1.1rem; width:1.4rem; }
.check .msg { font-size:0.92rem; }
.check .ev { color:#6B7280; font-size:0.78rem; }
.tl { position:relative; padding-left:26px; }
.tl .st { position:relative; padding:6px 0 14px 0; }
.tl .st:before { content:""; position:absolute; left:-21px; top:10px; width:12px; height:12px; border-radius:50%;
                 background:#E5E7EB; border:2px solid #fff; box-shadow:0 0 0 2px #E5E7EB; }
.tl .st.done:before { background:#E40046; box-shadow:0 0 0 2px #E40046; }
.tl .st.cur .lab { font-weight:700; color:#E40046; }
.tl .st:after { content:""; position:absolute; left:-16px; top:22px; bottom:-4px; width:2px; background:#E5E7EB; }
.tl .st:last-child:after { display:none; }
.tl .lab { font-size:0.95rem; }  .tl .eta { color:#6B7280; font-size:0.8rem; }
.big-btn button { width:100%; padding:0.8rem; font-size:1.05rem; }
.chip button { border-radius:999px; font-size:0.85rem; padding:0.25rem 0.75rem; }
.sms { background:#F1F5F9; border-radius:14px 14px 14px 4px; padding:10px 12px; margin:6px 0 2px 0; font-size:0.95rem; }
.sms .sms-from { color:#6B7280; font-size:0.75rem; font-weight:600; text-transform:uppercase; letter-spacing:0.04em; margin-bottom:2px; }
div[data-testid="stToast"] { font-family: Inter, 'Noto Sans Devanagari', sans-serif; }
</style>"""


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)
