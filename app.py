import os
import json
import time
import streamlit as st
import pypdf
from google import genai
from google.genai import types

st.set_page_config(page_title="PDF AI CBT 문제 은행", page_icon="📝", layout="wide")

st.title("📝 PDF AI CBT 응시 시스템 (Gemini AI)")
st.caption("PDF 학습 자료를 바탕으로 문제를 풀고, 점수 확인 및 오답 재풀기가 가능합니다.")

# Secrets에서 API 키 자동 불러오기
try:
    api_key = st.secrets["GEMINI_API_KEY"]
except Exception:
    api_key = None

# 사이드바 설정 (API 키 입력창 제거)
with st.sidebar:
    st.header("⚙️ 문제 설정")
    
    # 최신 지원 모델
    model_name = st.selectbox("AI 모델", ["gemini-3.8-flash", "gemini-3.5-flash-lite"], index=0)
    
    count = st.slider("문제 수", 1, 50, 5)
    difficulty = st.selectbox("난이도", ["하", "중", "상", "최상"])
    question_type = st.selectbox("문제 유형", ["혼합형", "4지선다형", "OX퀴즈"])

# 세션 상태 초기화
if "quiz_data" not in st.session_state:
    st.session_state.quiz_data = None
if "user_answers" not in st.session_state:
    st.session_state.user_answers = {}
if "submitted" not in st.session_state:
    st.session_state.submitted = False

uploaded_files = st.file_uploader("📄 PDF 파일을 업로드하세요", type=["pdf"], accept_multiple_files=True)

def extract_text_from_pdfs(files):
    extracted_text = ""
    for f in files:
        pdf_reader = pypdf.PdfReader(f)
        for page in pdf_reader.pages:
            text = page.extract_text()
            if text:
                extracted_text += text + "\n"
    return extracted_text

def generate_quiz(text, api_key, model_name, count, difficulty, question_type):
    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    제공된 학습 자료를 바탕으로 {count}개의 객관식 시험 문제를 출제해 주세요.
    난이도: {difficulty}
    문제 유형: {question_type}

    반드시 아래의 JSON 배열 형식으로만 응답해야 합니다. 다른 서론이나 결론, 마크다운 기호 없이 순수 JSON 구조만 반환하세요.
    [
        {{
            "id": 1,
            "question": "문제 내용",
            "options": ["1번 보기", "2번 보기", "3번 보기", "4번 보기"],
            "answer": "정답 보기의 문자 그대로 (예: 1번 보기)",
            "explanation": "해설 내용"
        }}
    ]

    학습 자료 내용:
    {text[:20000]}
    """
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json"
                )
            )
            return json.loads(response.text)
        except Exception as e:
            if "503" in str(e) and attempt < max_retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise e

if st.button("🚀 새 CBT 문제 생성하기"):
    if not api_key:
        st.error("API 키 설정이 되어있지 않습니다. .streamlit/secrets.toml 파일을 확인해 주세요.")
    elif not uploaded_files:
        st.error("PDF 파일을 업로드해주세요.")
    else:
        with st.spinner("Gemini AI가 CBT 시험문제를 출제하고 있습니다..."):
            try:
                raw_text = extract_text_from_pdfs(uploaded_files)
                st.session_state.quiz_data = generate_quiz(raw_text, api_key, model_name, count, difficulty, question_type)
                st.session_state.user_answers = {}
                st.session_state.submitted = False
                st.success("문제 출제가 완료되었습니다!")
                st.rerun()
            except Exception as e:
                st.error("문제 생성 중 오류가 발생했습니다.")
                st.code(str(e))

# 문제 풀이 화면
if st.session_state.quiz_data:
    st.divider()
    st.subheader("✍️ CBT 시험 응시")
    
    for idx, q in enumerate(st.session_state.quiz_data):
        st.markdown(f"**Q{idx+1}. {q['question']}**")
        
        selected_option = st.radio(
            f"Q{idx+1} 선택지",
            options=q["options"],
            key=f"q_{q['id']}",
            index=None if f"q_{q['id']}" not in st.session_state.user_answers else q["options"].index(st.session_state.user_answers[f"q_{q['id']}"]),
            disabled=st.session_state.submitted,
            label_visibility="collapsed"
        )
        
        if selected_option:
            st.session_state.user_answers[f"q_{q['id']}"] = selected_option
            
        if st.session_state.submitted:
            user_ans = st.session_state.user_answers.get(f"q_{q['id']}", "미응답")
            correct_ans = q["answer"]
            
            if user_ans == correct_ans:
                st.success(f"⭕ 정답입니다! (선택한 답: {user_ans})")
            else:
                st.error(f"❌ 오답입니다. (선택한 답: {user_ans} / 정답: {correct_ans})")
            
            st.info(f"💡 해설: {q['explanation']}")
            st.write("---")

    if not st.session_state.submitted:
        if st.button("🏁 답안 제출 및 채점하기", type="primary"):
            st.session_state.submitted = True
            st.rerun()
    else:
        correct_count = sum(1 for q in st.session_state.quiz_data if st.session_state.user_answers.get(f"q_{q['id']}") == q["answer"])
        total_count = len(st.session_state.quiz_data)
        score = int((correct_count / total_count) * 100)
        
        st.balloons()
        st.metric("최종 점수", f"{score}점", f"{correct_count}/{total_count} 정답")
        
        if st.button("🔄 다시 풀기"):
            st.session_state.submitted = False
            st.session_state.user_answers = {}
            st.rerun()