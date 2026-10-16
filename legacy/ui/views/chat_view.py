"""Multi-turn context-aware roadmap copilot view."""
import streamlit as st
from ui.components import render_navbar
from services import ai_service


def render():
    render_navbar()

    profile = st.session_state.get("profile", {})
    role = st.session_state.get("selected_role")
    roadmap = st.session_state.get("roadmap")

    if not role or not roadmap:
        st.session_state.page = "roadmap"
        st.rerun()

    st.markdown(f"## 💬 Roadmap Copilot: **{role['title']}**")
    st.caption("AI career mentor pre-loaded with your background, target role, and generated roadmap.")
    st.markdown("---")

    # Suggested Prompts
    if not st.session_state.get("chat_messages"):
        st.markdown("**💡 High-impact questions to ask your copilot:**")
        suggestions = [
            f"How should I split my 1.5 hours/day between DSA and {role['title']} projects?",
            f"What specific interview questions will Indian tech recruiters ask me?",
            f"Which of the 3 recommended projects should I push to GitHub first?",
            f"How do I explain my lack of prior work experience during technical rounds?"
        ]
        sc1, sc2 = st.columns(2)
        for idx, text in enumerate(suggestions):
            with (sc1 if idx % 2 == 0 else sc2):
                if st.button(text, key=f"copilot_sug_{idx}", use_container_width=True):
                    st.session_state.setdefault("chat_messages", []).append({"role": "user", "content": text})
                    with st.spinner("Analyzing with profile context..."):
                        try:
                            reply = ai_service.send_chat_message(profile, role, roadmap, text, [])
                        except ai_service.AIConfigurationError as e:
                            st.error(f"⚙️ **AI is not configured.** {e}")
                            st.stop()
                        except Exception as e:
                            st.error(f"Could not reach the AI right now: {e}")
                            st.stop()
                    st.session_state.chat_messages.append({"role": "model", "content": reply})
                    st.rerun()
        st.markdown("---")

    # Render History
    for msg in st.session_state.get("chat_messages", []):
        if msg["role"] == "user":
            with st.chat_message("user"):
                st.markdown(msg["content"])
        else:
            with st.chat_message("assistant", avatar="🧭"):
                st.markdown(msg["content"])

    # Input Box
    user_input = st.chat_input(f"Ask any question about your {role['title']} roadmap...")
    if user_input:
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant", avatar="🧭"):
            try:
                reply = st.write_stream(
                    ai_service.stream_chat_message(
                        profile,
                        role,
                        roadmap,
                        user_input,
                        st.session_state.get("chat_messages", []),
                    )
                )
            except ai_service.AIConfigurationError as e:
                st.error(f"⚙️ **AI is not configured.** {e}")
                st.stop()
            except Exception as e:
                st.error(f"Could not reach the AI right now: {e}")
                st.stop()

        st.session_state.setdefault("chat_messages", []).append({"role": "user", "content": user_input})
        st.session_state.chat_messages.append({"role": "model", "content": reply})
        st.rerun()

    st.markdown("---")
    c1, c2 = st.columns([1.5, 4.0])
    with c1:
        if st.button("← Back to Roadmap", use_container_width=True):
            st.session_state.page = "roadmap"
            st.rerun()
    with c2:
        if st.button("🗑️ Clear Conversation", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()
