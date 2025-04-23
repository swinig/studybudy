import google.generativeai as genai
import streamlit as st
import tempfile
import os
import time

# Configure the Gemini API key

# Read API key from Streamlit secrets
google_gemini_api = st.secrets["GOOGLE_API_KEY"]
genai.configure(api_key=google_gemini_api)

# Initialize the Generative Model
model = genai.GenerativeModel("gemini-1.5-flash") # Using gemini-1.5-flash as it's generally recommended for chat/multi-turn

# client = genai.Client(api_key=google_gemini_api) # Removed deprecated client initialization

st.title("📘 Study Buddy AI: Learn from Book Images")

# Update file_uploader to accept multiple files
uploaded_files = st.file_uploader(
    "Upload chapter images (jpeg, png)",
    type=["jpeg", "jpg", "png"],
    accept_multiple_files=True # Allow multiple files
)

if uploaded_files: # Check if the list is not empty
    # Keep track of temporary file paths and uploaded file objects
    temp_file_paths = []
    gemini_files = []
    all_uploads_successful = True

    with st.spinner("Reading, uploading, and understanding the chapter images..."):
        try:
            for uploaded_file in uploaded_files:
                # Save uploaded image temporarily
                with tempfile.NamedTemporaryFile(delete=False, suffix=".jpg") as tmp_file:
                    tmp_file.write(uploaded_file.read())
                    tmp_path = tmp_file.name
                    temp_file_paths.append(tmp_path) # Store path for cleanup

                # Upload to Gemini
                print(f"Attempting to upload file: {uploaded_file.name} (temp path: {tmp_path})")
                myfile = genai.upload_file(path=tmp_path, display_name=uploaded_file.name) # Use genai.upload_file
                print(f"File {uploaded_file.name} uploaded successfully: {myfile.name}")

                # Ensure file state is ACTIVE before proceeding
                while myfile.state.name == "PROCESSING":
                    print(f"Waiting for file {uploaded_file.name} processing...")
                    time.sleep(2) # Add a small delay
                    myfile = genai.get_file(myfile.name) # Refresh file state

                if myfile.state.name == "FAILED":
                     st.error(f"File upload failed for {uploaded_file.name}.")
                     all_uploads_successful = False
                     # Decide if you want to stop entirely or just skip this file
                     # For now, we'll mark as failed and continue, but not generate content if any failed.
                     break # Stop processing further files if one fails

                gemini_files.append(myfile) # Add the successful upload to the list

            if all_uploads_successful and gemini_files:
                # Prompt (using the one you updated)
                prompt = """
                You are a study assistant and senior student of nursing and medical field. Please do the following based on the content of ALL the provided images:

                1. Summarize the chapter content across all images in depth and structured manner (headings, subheadings, bullet points, and paragraphs).
                2. Highlight key concepts, definitions, and important facts found anywhere in the images.
                3. List real-life examples or analogies (if applicable) to help understand difficult parts, drawing from all images.
                4. Extract 10 long and 10 short important questions with answers I might be asked in an exam or discussion, covering material from all images.
                Explain topics in detail, considering potential subtopics or multiple topics spread across the images. Take into account the context of the chapter and all provided images.
                """

                # Generate content - Pass the list of File objects and the prompt
                # The prompt should ideally come last in the list for multi-image prompts
                print(f"Generating content with {len(gemini_files)} files and prompt.")
                content_to_generate = gemini_files + [prompt] # Combine list of files and prompt
                response = model.generate_content(content_to_generate)

                # Display the result
                st.subheader("📄 AI Generated Study Notes (from all images):")
                st.text_area("Response", response.text, height=600)

                # Optional: Download button
                st.download_button(
                    label="Download Response as .txt",
                    data=response.text,
                    file_name="chapter_summary.txt",
                    mime="text/plain"
                )
            elif not gemini_files:
                 st.warning("No files were successfully uploaded or processed.")


        except Exception as e:
            st.error(f"An error occurred during processing: {e}")
            print(f"Error during Gemini processing: {e}")

        finally:
            # Clean up all temporary files
            print(f"Cleaning up {len(temp_file_paths)} temporary files...")
            for path in temp_file_paths:
                if os.path.exists(path):
                    os.remove(path)
                    print(f"Temporary file removed: {path}")

# No else block needed for if uploaded_files, as st.file_uploader handles the 'no file' state.