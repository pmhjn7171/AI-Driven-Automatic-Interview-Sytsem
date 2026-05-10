# app.py (minor fixes for consistency and bug in question generation)
import streamlit as st
import asyncio
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from utils import (
    transcribe_with_speechmatics,
    extract_resume_info_using_llm,
    get_ai_greeting_message,
    get_final_thanks_message,
    speak_text,
    analyze_candidate_response_and_generate_new_question,
    get_feedback_of_candidate_response,
    get_overall_evaluation_score,
    save_interview_data,
    load_content_streamlit,
)

MAX_QUESTIONS = 5
PASS_SCORE_THRESHOLD = 6.0


# Configuration and Styling
def setup_page_config():
    """Setup page configuration and custom CSS"""
    st.set_page_config(page_title="AI Interview App", layout="wide")

    st.markdown(
        """
    <style>
    .audio-section {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 20px;
        margin-top: 20px;
        text-align: center;
        border: 2px solid #e9ecef;
    }
    .interview-progress {
        background-color: #e8f5e8;
        border-radius: 10px;
        padding: 15px;
        margin-bottom: 20px;
        text-align: center;
    }
    </style>
    """,
        unsafe_allow_html=True,
    )


def initialize_session_state():
    """Initialize all session state variables"""
    defaults = {
        "interview_started": False,
        "name": "",
        "resume_highlights": "",
        "job_description": "",
        "qa_index": 1,
        "conversations": [],
        "current_question": "",
        "question_spoken": False,
        "awaiting_response": False,
        "processing_audio": False,
        "messages": [],
        "interview_completed": False,
        "max_questions": MAX_QUESTIONS,
        "ai_voice": "Alex (Male)",
        "thanks_message_prepared": False,
        "thanks_message_spoken": False,
        "show_final_results": False,
        "cheat_process": None,
        "cheat_true_count": 0,
        "cheat_false_count": 0,
        "cheated": False,
        "final_result": "",
    }

    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def get_ai_voice_details():
    """Get AI voice configuration"""
    return {
        "Alex (Male)": {"name": "Alex", "code": "en-US-GuyNeural"},
        "Aria (Female)": {"name": "Aria", "code": "en-US-AriaNeural"},
        "Natasha (Female)": {"name": "Natasha", "code": "en-AU-NatashaNeural"},
        "Sonia (Female)": {"name": "Sonia", "code": "en-GB-SoniaNeural"},
    }

def get_instructions():
    """Get instructions for the user"""
    return """
    #### Please follow these steps to use the AI Interview App:
    1. **Upload Resume**: Upload your resume in PDF format.
    2. **Job Description**: Paste the job description.
    3. **Start Interview**: Click the "Start Interview" button to begin the AI-driven interview.
    4. **Maximum Questions**: You can set the maximum number of questions for the interview. (default: 5)
    5. **Voice Selection**: Choose the AI voice for the interview.(default: Alex (Male))
    6. **Answer Questions**: Answer the questions posed by the AI interviewer.
    7. **Review Results**: After the interview, review your performance and feedback.

    **Note**: The AI interviewer will ask you questions based on your resume and the job description.

    I hope you find the experience helpful!
    """

def render_sidebar():
    """Render sidebar with candidate information and settings"""
    st.sidebar.title("Candidate Information")

    # File upload
    uploaded_resume = st.sidebar.file_uploader("Upload your Resume (PDF)", type=["pdf"])

    # Job description
    job_description = st.sidebar.text_area("Paste the Job Description")

    # Settings
    max_questions = st.sidebar.number_input(
        "Maximum number of questions",
        min_value=1,
        max_value=10,
        value=MAX_QUESTIONS,
    )
    st.session_state["max_questions"] = max_questions

    ai_voice = st.sidebar.radio(
        "Select AI Interviewer Voice",
        ["Alex (Male)", "Aria (Female)", "Natasha (Female)", "Sonia (Female)"],
    )
    st.session_state["ai_voice"] = ai_voice

    submit = st.sidebar.button("Submit")

    return uploaded_resume, job_description, submit


def process_resume_submission(uploaded_resume, job_description):
    """Process resume and job description submission"""
    with st.spinner("Processing resume..."):
        resume_content = load_content_streamlit(uploaded_resume)
        name, resume_highlights = extract_resume_info_using_llm(resume_content)

    # Store in session state
    st.session_state["name"] = name
    st.session_state["resume_highlights"] = resume_highlights
    st.session_state["job_description"] = job_description

    # Reset interview state
    reset_interview_state()

    st.success(f"Candidate Name: {name}")


def reset_interview_state():
    """Reset interview-related session state"""
    stop_cheating_service()
    interview_keys = [
        "interview_started",
        "qa_index",
        "conversations",
        "current_question",
        "question_spoken",
        "awaiting_response",
        "processing_audio",
        "messages",
        "interview_completed",
        "thanks_message_prepared",
        "thanks_message_spoken",
        "show_final_results",
        "cheat_true_count",
        "cheat_false_count",
        "cheated",
        "final_result",
        "cheat_process",
    ]

    for key in interview_keys:
        if key in ["interview_started", "interview_completed", "cheated"]:
            st.session_state[key] = False
        elif key in ["qa_index"]:
            st.session_state[key] = 1
        elif key in ["conversations", "messages"]:
            st.session_state[key] = []
        elif key in ["current_question"]:
            st.session_state[key] = ""
        elif key in ["cheat_true_count", "cheat_false_count"]:
            st.session_state[key] = 0
        elif key in ["final_result"]:
            st.session_state[key] = ""
        elif key in ["cheat_process"]:
            st.session_state[key] = None
        else:
            st.session_state[key] = False


def start_interview():
    """Initialize and start the interview"""
    st.session_state["interview_started"] = True
    reset_interview_state()
    st.session_state["interview_started"] = True  # Reset above sets this to False
    start_cheating_service()

    # Get greeting message
    ai_voice_details = get_ai_voice_details()
    interviewer_name = ai_voice_details[st.session_state["ai_voice"]]["name"]
    greeting_message = get_ai_greeting_message(
        st.session_state["name"], interviewer_name=interviewer_name
    )

    st.session_state["current_question"] = greeting_message
    st.session_state["messages"].append(
        {"role": "assistant", "content": greeting_message}
    )


def display_chat_messages():
    """Display all chat messages from history"""
    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])


def get_cheating_service_paths():
    """Return script and status file paths for anti-cheat service."""
    base_dir = Path(__file__).resolve().parent / "anti_cheat_service"
    return (
        base_dir / "detect_cheating.py",
        base_dir / "cheating_status.txt",
    )


def clear_cheating_status_file():
    """Clear previous cheating samples before a new interview run."""
    _, status_file = get_cheating_service_paths()
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text("", encoding="utf-8")


def start_cheating_service():
    """Start camera anti-cheat microservice in background if not already running."""
    existing = st.session_state.get("cheat_process")
    if existing is not None and existing.poll() is None:
        return

    script_file, _ = get_cheating_service_paths()
    clear_cheating_status_file()

    try:
        process = subprocess.Popen(
            [sys.executable, str(script_file)],
            cwd=str(script_file.parent),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        st.session_state["cheat_process"] = process
    except Exception as e:
        st.warning(f"Anti-cheat service could not start: {e}")
        st.session_state["cheat_process"] = None


def stop_cheating_service():
    """Stop camera anti-cheat microservice if running."""
    process = st.session_state.get("cheat_process")
    if process is None:
        return

    if process.poll() is None:
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    st.session_state["cheat_process"] = None


def read_cheating_counts():
    """Read anti-cheat status history and return (true_count, false_count)."""
    _, status_file = get_cheating_service_paths()
    if not status_file.exists():
        return 0, 0

    true_count = 0
    false_count = 0
    for line in status_file.read_text(encoding="utf-8").splitlines():
        token = line.strip().lower()
        if token == "true":
            true_count += 1
        elif token == "false":
            false_count += 1
    return true_count, false_count


def speak_current_question():
    """Speak the current question if not already spoken"""
    if st.session_state["current_question"] and not st.session_state["question_spoken"]:
        with st.spinner("AI Interviewer is speaking..."):
            ai_voice_details = get_ai_voice_details()
            speak_text(
                st.session_state["current_question"],
                voice=ai_voice_details[st.session_state["ai_voice"]]["code"],
            )
        st.session_state["question_spoken"] = True
        st.session_state["awaiting_response"] = True
        st.rerun()


def set_next_question(next_question):
    """Set the next question in session state"""
    st.session_state["current_question"] = next_question
    st.session_state["messages"].append({"role": "assistant", "content": next_question})
    st.session_state["question_spoken"] = False
    st.session_state["awaiting_response"] = False


def process_candidate_response(transcript):
    """Process candidate's response and move to next state"""
    # Add candidate's answer to chat
    st.session_state["messages"].append({"role": "user", "content": transcript})

    current_q = st.session_state["current_question"]
    qa_index = st.session_state["qa_index"]
    max_q = st.session_state["max_questions"]

    next_question = None
    if qa_index < max_q:
        # Not the last question - generate next question and feedback
        next_question, feedback = asyncio.run(analyze_candidate_response_and_generate_new_question(
            current_q,
            transcript,
            st.session_state["job_description"],
            st.session_state["resume_highlights"],
        ))
    else:
        # Last question - only generate feedback
        feedback_result = asyncio.run(get_feedback_of_candidate_response(
            current_q,
            transcript,
            st.session_state["job_description"],
            st.session_state["resume_highlights"],
        ))
        feedback = {"score": feedback_result["score"], "feedback": feedback_result["feedback"]}

    # Store conversation
    st.session_state["conversations"].append(
        {
            "Question": current_q,
            "Candidate Answer": transcript,
            "Evaluation": feedback["score"],
            "Feedback": feedback["feedback"],
        }
    )

    # Move to next question or complete interview
    st.session_state["qa_index"] += 1
    st.session_state["processing_audio"] = False
    st.session_state["awaiting_response"] = False

    if st.session_state["qa_index"] <= st.session_state["max_questions"]:
        # Prepare next question
        set_next_question(next_question)
        st.success("✅ Answer recorded! Preparing next question...")
    else:
        # Interview completed - prepare thanks message
        st.session_state["interview_completed"] = True
        prepare_thanks_message()


def prepare_thanks_message():
    """Prepare and display thanks message"""
    if not st.session_state["thanks_message_prepared"]:
        final_note = get_final_thanks_message(st.session_state["name"])
        st.session_state["messages"].append(
            {"role": "assistant", "content": final_note}
        )
        st.session_state["thanks_message_prepared"] = True
        st.session_state["qa_index"] -= 1
        st.rerun()


def speak_thanks_message():
    """Speak the thanks message"""
    if (
        st.session_state["thanks_message_prepared"]
        and not st.session_state["thanks_message_spoken"]
    ):

        # Get the last message (thanks message)
        thanks_message = st.session_state["messages"][-1]["content"]

        with st.spinner("AI Interviewer is giving final remarks..."):
            ai_voice_details = get_ai_voice_details()
            speak_text(
                thanks_message,
                voice=ai_voice_details[st.session_state["ai_voice"]]["code"],
            )

        st.session_state["thanks_message_spoken"] = True
        st.success("🎉 Interview completed! Thank you for your time.")

        # Now show final results
        st.session_state["show_final_results"] = True
        st.rerun()


def handle_audio_recording():
    """Handle audio recording and processing"""
    if not (
        st.session_state["awaiting_response"]
        and not st.session_state["processing_audio"]
    ):
        return

    st.write("**🎙️ Please record your answer to the question above**")

    audio_key = f"audio_input_{st.session_state['qa_index']}_{len(st.session_state['messages'])}"
    audio_data = st.audio_input("Record your answer", key=audio_key)

    if audio_data is not None:
        st.session_state["processing_audio"] = True

        with st.spinner("Processing your answer..."):
            # Save audio file
            name = st.session_state["name"]
            filename = f"audio/{name}/{name}_{st.session_state['qa_index'] + 1}.wav"
            os.makedirs(os.path.dirname(filename), exist_ok=True)

            with open(filename, "wb") as f:
                f.write(audio_data.read())

            # Transcribe audio
            transcript = transcribe_with_speechmatics(filename)

            if transcript and transcript.strip():
                process_candidate_response(transcript)
                st.rerun()
            else:
                st.error("No speech detected in audio. Please try recording again.")
                st.session_state["processing_audio"] = False


def display_final_results():
    """Display final interview results"""
    if (
        not st.session_state["show_final_results"]
        or not st.session_state["conversations"]
    ):
        return

    with st.spinner("Calculating final score..."):
        stop_cheating_service()
        true_count, false_count = read_cheating_counts()
        cheated = true_count > false_count

        final_score = get_overall_evaluation_score(st.session_state["conversations"])
        final_result = (
            "PASS" if (not cheated and final_score >= PASS_SCORE_THRESHOLD) else "FAIL"
        )
        st.session_state["cheat_true_count"] = true_count
        st.session_state["cheat_false_count"] = false_count
        st.session_state["cheated"] = cheated
        st.session_state["final_result"] = final_result

        # Save interview data
        now = datetime.now().isoformat() + "Z"
        interview_data = {
            "name": st.session_state["name"],
            "createdAt": now,
            "updatedAt": now,
            "id": 1,
            "job_description": st.session_state["job_description"],
            "resume_highlights": st.session_state["resume_highlights"],
            "conversations": st.session_state["conversations"],
            "overall_score": round(final_score, 2),
            "cheating_true_count": true_count,
            "cheating_false_count": false_count,
            "cheated": cheated,
            "result": final_result,
        }
        save_interview_data(interview_data, candidate_name=st.session_state["name"])

    # Display results
    st.subheader("🎉 Interview Results")
    st.markdown(f"**Candidate:** {st.session_state['name']}")
    st.markdown(f"**Overall Score:** {final_score:.2f}/10")
    st.markdown(f"**Cheating Status:** {'Cheated' if st.session_state['cheated'] else 'Not Cheated'}")
    st.markdown(
        f"**Anti-Cheat Samples:** true={st.session_state['cheat_true_count']}, false={st.session_state['cheat_false_count']}"
    )
    st.markdown(f"**Final Decision:** {st.session_state['final_result']}")

    # Show detailed summary
    st.subheader("Detailed Interview Summary")
    for i, conv in enumerate(st.session_state["conversations"], 1):
        with st.expander(f"Question {i} (Score: {conv['Evaluation']}/10)"):
            st.write(f"**Q:** {conv['Question']}")
            st.write(f"**A:** {conv['Candidate Answer']}")
            st.write(f"**Feedback:** {conv['Feedback']}")

    # New interview option
    if st.button("Start New Interview"):
        stop_cheating_service()
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


def render_interview_progress():
    """Render interview progress indicator"""
    if st.session_state.get("interview_started", False):
        progress_text = f"Question {st.session_state['qa_index']} of {st.session_state['max_questions']}"
        st.markdown(
            f'<div class="interview-progress"><strong>{progress_text}</strong></div>',
            unsafe_allow_html=True,
        )


def main():
    """Main application function"""
    # Setup
    setup_page_config()
    initialize_session_state()

    # Header
    st.title("🤖 AI Interview System")
    instructions_placeholder = st.empty()
    if not st.session_state["interview_started"]:
        instructions_placeholder.markdown(get_instructions())

    # Sidebar
    uploaded_resume, job_description, submit = render_sidebar()

    # Process submission
    if submit and uploaded_resume and job_description:
        instructions_placeholder.empty()
        process_resume_submission(uploaded_resume, job_description)
        

    # Start interview button
    if st.session_state["name"] and not st.session_state["interview_started"]:
        if st.button("Start Interview"):
            start_interview()
            st.rerun()

    # Interview section
    if st.session_state.get("interview_started", False):
        render_interview_progress()

        # Show chat history
        st.subheader("Interview Chat")
        display_chat_messages()

        # Handle different interview states
        if not st.session_state["interview_completed"]:
            # Active interview
            speak_current_question()
            handle_audio_recording()
        elif not st.session_state["thanks_message_prepared"]:
            # Interview just completed - prepare thanks
            prepare_thanks_message()
        elif not st.session_state["thanks_message_spoken"]:
            # Thanks message prepared but not spoken
            speak_thanks_message()
        else:
            # Everything done - show results
            display_final_results()


if __name__ == "__main__":
    main()
