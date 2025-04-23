import google.generativeai as genai
import streamlit as st
import tempfile
import os
import time
from PIL import Image # Import PIL for displaying images in chat

# --- Configuration ---
# Read API key from Streamlit secrets
try:
    google_gemini_api = st.secrets["GOOGLE_API_KEY"]
    genai.configure(api_key=google_gemini_api)
except (KeyError, FileNotFoundError):
    st.error("🚨 GOOGLE_API_KEY not found. Please add it to your Streamlit secrets.")
    st.stop()

# Initialize the Generative Model (ensure it supports multimodal input)
MODEL_NAME = "gemini-1.5-flash" # Or "gemini-pro-vision" if flash gives issues
try:
    model = genai.GenerativeModel(MODEL_NAME)
except Exception as e:
    st.error(f"🚨 Error initializing Gemini model ({MODEL_NAME}): {e}")
    st.stop()

st.title("📘 Chat with Study Buddy AI")
st.caption("Upload chapter images and ask questions!")

# --- Helper Functions ---
def upload_and_process_files(uploaded_file_list):
    """Uploads files to Gemini, tracks state, and returns Gemini File objects."""
    processed_files = []
    temp_file_paths = []
    all_success = True

    if not uploaded_file_list:
        return [], [], True # No files to process

    with st.spinner(f"Processing {len(uploaded_file_list)} image(s)..."):
        try:
            for uploaded_file in uploaded_file_list:
                # Save temporarily
                with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(uploaded_file.name)[1]) as tmp_file:
                    tmp_file.write(uploaded_file.getvalue())
                    tmp_path = tmp_file.name
                    temp_file_paths.append(tmp_path)

                # Upload to Gemini
                print(f"Attempting to upload file: {uploaded_file.name}")
                # Giving a display name helps potentially
                file_to_upload = genai.upload_file(path=tmp_path, display_name=uploaded_file.name)
                print(f"File {uploaded_file.name} uploaded: {file_to_upload.name}, State: {file_to_upload.state.name}")

                # Wait for processing (Important!)
                while file_to_upload.state.name == "PROCESSING":
                    print(f"Waiting for file {uploaded_file.name}...")
                    time.sleep(2)
                    file_to_upload = genai.get_file(file_to_upload.name) # Refresh state

                if file_to_upload.state.name == "FAILED":
                    st.error(f"Upload failed for {uploaded_file.name}. Please try again.")
                    all_success = False
                    # Don't add failed files
                elif file_to_upload.state.name == "ACTIVE":
                     print(f"File {uploaded_file.name} is ACTIVE.")
                     processed_files.append(file_to_upload) # Add successful upload
                else:
                    st.warning(f"File {uploaded_file.name} in unexpected state: {file_to_upload.state.name}")
                    all_success = False # Treat unexpected states as issues for now

        except Exception as e:
            st.error(f"An error occurred during file processing: {e}")
            print(f"Error during Gemini upload/processing: {e}")
            all_success = False
        finally:
            # Clean up temp files
            for path in temp_file_paths:
                if os.path.exists(path):
                    try:
                        os.remove(path)
                        print(f"Temporary file removed: {path}")
                    except Exception as clean_e:
                        print(f"Error removing temp file {path}: {clean_e}")
    return processed_files, temp_file_paths, all_success


# --- Session State Initialization ---
if "messages" not in st.session_state:
    st.session_state.messages = [] # Stores chat history: [{"role": "user/model", "content": ["text", file_object]}]
if "gemini_files" not in st.session_state:
    st.session_state.gemini_files = {} # Stores maps original filename to Gemini File object {filename: File}
if "temp_paths" not in st.session_state:
    st.session_state.temp_paths = [] # To ensure cleanup on rerun if needed

# --- Sidebar for File Upload ---
with st.sidebar:
    st.subheader("Upload Images")
    uploaded_files = st.file_uploader(
        "Upload chapter images (jpeg, png)",
        type=["jpeg", "jpg", "png"],
        accept_multiple_files=True,
        label_visibility="collapsed"
    )
    # Display currently active files (optional)
    st.caption("Active Files in Session:")
    if st.session_state.gemini_files:
         for name in st.session_state.gemini_files.keys():
              st.markdown(f"- `{name}`")
    else:
         st.markdown("_No files uploaded yet._")

# --- Process Newly Uploaded Files ---
# We process files here *before* the chat input, so they are ready if the user asks about them immediately.
newly_uploaded_file_objects = []
if uploaded_files:
    # Filter out files already processed and stored in session state
    files_to_process = [f for f in uploaded_files if f.name not in st.session_state.gemini_files]

    if files_to_process:
        processed_files, temp_paths, success = upload_and_process_files(files_to_process)
        st.session_state.temp_paths.extend(temp_paths) # Track for potential cleanup needed later if errors occur mid-script

        if success:
            for original_file, gemini_file in zip(files_to_process, processed_files):
                 st.session_state.gemini_files[original_file.name] = gemini_file
            st.success(f"Successfully processed {len(processed_files)} new image(s).")
            # Rerun to update the sidebar list immediately and clear the uploader state visually
            st.rerun()
        else:
             st.error("Some files could not be processed. Please check errors above.")


# --- Display Chat History ---
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        # Content can be a list (text + images/files)
        for item in message["content"]:
            if isinstance(item, str):
                st.markdown(item)
            elif hasattr(item, 'read'): # Handle display of uploaded images in chat
                try:
                    # Display the image the user uploaded
                    img = Image.open(item)
                    # Calculate a reasonable width (e.g., max 400px)
                    max_width = 400
                    aspect_ratio = img.height / img.width
                    new_width = min(img.width, max_width)
                    new_height = int(new_width * aspect_ratio)
                    st.image(img, width=new_width)
                except Exception as e:
                    st.warning(f"Could not display image {getattr(item, 'name', 'N/A')}: {e}")


# --- Handle Chat Input ---
if prompt := st.chat_input("Ask a question about the uploaded images..."):
    # 1. Display user message immediately
    # Include thumbnails of *active* files user might be referring to
    user_message_content = [prompt]
    # Create copies of uploaded file objects for display (don't pass Gemini objects to PIL)
    display_files = [f for f in uploaded_files if f.name in st.session_state.gemini_files] # Get original UploadedFile objects
    if display_files:
        user_message_content.append(f"(Referring to images: {', '.join([f.name for f in display_files])})_")
        # Add images directly to user message display if desired
        # for uf in display_files:
        #    user_message_content.append(uf) # Requires handling in display loop above

    st.session_state.messages.append({"role": "user", "content": [prompt]}) # Store only text for history simplicity
    with st.chat_message("user"):
        st.markdown(prompt)
        # Display images associated with this turn if needed (optional)
        # for uf in display_files:
        #     st.image(uf, width=100) # Small thumbnails

    # 2. Prepare content for Gemini
    # We will send *all* currently active Gemini file objects along with the user prompt.
    # Gemini models are designed to handle multimodal input this way.
    if not st.session_state.gemini_files:
        st.warning("Please upload images before asking questions.")
        st.stop()

    gemini_content_list = list(st.session_state.gemini_files.values()) + [prompt]

    # 3. Generate response
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        message_placeholder.markdown("🧠 Thinking...")
        try:
            print(f"Generating content with {len(st.session_state.gemini_files)} files and prompt: '{prompt[:50]}...'")
            response = model.generate_content(gemini_content_list)

            # Check for empty or blocked response
            if not response.parts:
                 response_text = "⚠️ Model did not provide a response. This might be due to safety settings or lack of relevant content in the images."
                 print("Warning: Received empty response from Gemini.")
            else:
                 response_text = response.text

            message_placeholder.markdown(response_text)
            # Store assistant response (text only for now)
            st.session_state.messages.append({"role": "assistant", "content": [response_text]})

        except Exception as e:
            error_message = f"An error occurred: {e}"
            st.error(error_message)
            print(f"Error during Gemini generation: {e}")
            st.session_state.messages.append({"role": "assistant", "content": [f"Error generating response: {e}"]})

    # Clean up temporary files (optional - could leave until session ends)
    # for path in st.session_state.get("temp_paths", []):
    #     if os.path.exists(path):
    #         try:
    #             os.remove(path)
    #             print(f"Temporary file cleaned up during run: {path}")
    #         except Exception as clean_e:
    #             print(f"Error cleaning temp file {path} during run: {clean_e}")
    # st.session_state.temp_paths = [] # Clear list if cleaned