import streamlit as st
from agent import create_agent
from langchain_core.messages import HumanMessage

st.set_page_config(page_title="ChefGPT - Meal Planner", layout="centered")
st.title("🥗 Vertex AI Meal Planner")
st.caption("L200 Assessment Agent - Powered by LangGraph & Google Vertex AI")

agent = create_agent()

# Logic for Session State (Memory context within the UI)
if "messages" not in st.session_state:
    st.session_state.messages = []

user_id = st.sidebar.text_input("GCP User Identity", value="default_user")
config = {"configurable": {"thread_id": user_id}}

# Display chat history
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

if prompt := st.chat_input("Ex: Plan a high-protein vegetarian week for me."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    st.chat_message("user").write(prompt)

    # Orchestration: Invoke the Agent
    inputs = {"messages": [HumanMessage(content=prompt)]}
    
    with st.chat_message("assistant"):
        with st.spinner("Thinking..."):
            response = agent.invoke(inputs, config=config)
            # The last message in the state is the AI's response
            final_msg = response["messages"][-1].content
            st.write(final_msg)
            st.session_state.messages.append({"role": "assistant", "content": final_msg})

st.sidebar.divider()
st.sidebar.info("Running on Cloud Run. Memory persists via local SQLite checkpointer.")