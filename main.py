import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime
from google.cloud import firestore
from google.oauth2.service_account import Credentials
import os
import json


# Constants for Prodia API
BASE_URL = "https://api.prodia.com/v1"
HEADERS = {
    "accept": "application/json",
    "content-type": "application/json",
    "X-Prodia-Key": st.secrets["PRODIA_API_KEY"]
}

# Initialize Firebase
print(st.secrets["FIREBASE_CRED"])
service_account_info = json.loads(st.secrets["FIREBASE_CRED"])
service_account_info['private_key'] = service_account_info['private_key'].encode('utf-8').decode('unicode_escape')
credentials = Credentials.from_service_account_info(service_account_info)
db = firestore.Client(credentials=credentials)
problematic_part = st.secrets["FIREBASE_CRED"].splitlines()[4][40:50]  # This gets the line 5 and 10 characters around column 46
print(f"Problematic part: {problematic_part}")
# Functions for Prodia API
def generate_image(payload, model):
    response = requests.post(f"{BASE_URL}/sd/generate", json=payload, headers=HEADERS)
    if response.status_code == 200:
        job_id = response.json()["job"]
        while True:
            time.sleep(5)
            job_status = check_job_status(job_id)
            if job_status["status"] == "succeeded":
                return job_status["imageUrl"]

def check_job_status(job_id):
    response = requests.get(f"{BASE_URL}/job/{job_id}", headers=HEADERS)
    return response.json()

# Gallery page to display generated images
def prompt_gallery_page():
    st.header("Prompt Gallery")

    # Load images and prompts from Firebase Firestore
    docs = db.collection(st.session_state.current_session).document('generated_images').collection('images').stream()
    entries = [doc.to_dict() for doc in docs]
    total_entries = len(entries)

    # Initialize gallery_start_index in session_state if not present
    if 'gallery_start_index' not in st.session_state:
        st.session_state.gallery_start_index = 0

    # Extract relevant data for the current page
    start_index = st.session_state.gallery_start_index
    end_index = start_index + 4
    current_page_entries = entries[start_index:end_index]

    # Display the images and prompts
    for entry in current_page_entries:
        st.image(entry['image_url'], caption=entry['positive_prompt'], use_column_width=True)

    # Navigation buttons and page number display
    col1, col2, col3 = st.columns(3)

    # Back button
    if start_index > 0:
        if col1.button("Back"):
            st.session_state.gallery_start_index -= 4

    # Page number
    current_page_num = start_index // 4 + 1
    total_pages = (total_entries - 1) // 4 + 1
    col2.write(f"Page {current_page_num} of {total_pages}")

    # Next button
    if end_index < total_entries:
        if col3.button("Next"):
            st.session_state.gallery_start_index += 4

# Page to create art using AI
def create_art_page():
    st.header("Create Your AI Art")

    # Initialize the generation counter
    if 'generation_attempts' not in st.session_state:
        st.session_state.generation_attempts = 3

    st.write(f"You have {st.session_state.generation_attempts} attempts left to generate an image you like.")
    
    model_options = ["dreamshaper_8.safetensors [9d40847d]", "deliberate_v2.safetensors [10ec4b29]", "anything-v4.5-pruned.ckpt [65745d25]"]
    model = st.selectbox("Select a Model", model_options)
    prompt = st.text_input("Positive Prompt", value="Example: Mystical forest at dawn")
    negative_prompt = st.text_input("Negative Prompt", value="Example: No animals")

    # Disable the button if no attempts left
    generate_button_disabled = st.session_state.generation_attempts <= 0

    if st.button("Generate", disabled=generate_button_disabled):
        # Payload for the Prodia API
        payload = {
            "model": model,
            "prompt": prompt,
            "negative_prompt": negative_prompt,
            "steps": 25,
            "cfg_scale": 3,
            "upscale": True,
            "sampler": "DPM++ 2M Karras",
            "aspect_ratio": "square"
        }
        with st.spinner("Generating your AI Art..."):
            generated_image_url = generate_image(payload, model)
            st.image(generated_image_url, caption="Generated Image", use_column_width=True)

            # Decrement the generation counter
            st.session_state.generation_attempts -= 1

            # Store the generated image details in Firebase Firestore
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            db.collection(st.session_state.current_session).document('generated_images').collection('images').add({
                'positive_prompt': prompt,
                'image_url': generated_image_url,
                'timestamp': timestamp
            })
            st.success("Your artwork has been generated and saved!")

# Page to enter contest using generated art
def enter_contest_page():
    st.header("Enter the Contest")

    # Fetch all generated images from Firestore
    generated_art_ref = db.collection(st.session_state.current_session).document('generated_images').collection('images')
    submissions = [doc.to_dict() for doc in generated_art_ref.stream()]

    # Fetch all image URLs from contest_entries
    contest_entries_ref = db.collection(st.session_state.current_session).document('contest_entries').collection('entries')
    contest_submissions = [doc.to_dict() for doc in contest_entries_ref.stream()]
    submitted_image_urls = {sub.get('image_url') for sub in contest_submissions}

    # Filter out already submitted images and create the dropdown options
    image_options = []
    for sub in submissions:
        if sub['image_url'] not in submitted_image_urls:
            prompt = sub.get('positive_prompt', 'No Prompt Available')
            image_options.append((sub['image_url'], prompt))

    # Check if there are any artworks left to submit
    if not image_options:
        st.write("All artworks have been submitted to the contest.")
        return

    selected_image_url, selected_prompt = st.selectbox("Select your original creation:", image_options, format_func=lambda x: x[1])

    # Display the selected image
    st.image(selected_image_url, caption=selected_prompt, use_column_width=True)

    # Input fields for contest entry
    artwork_name = st.text_input("Name your Artwork:")
    description = st.text_area("Describe your artwork:", max_chars=150)
    
    # Dropdown to specify the contest category
    contest_categories = [
        "Innovation Leadership",
        "Diversity and Community Impact",
        "The Future of Creativity",
        "The People's Choice"
    ]
    selected_category = st.selectbox("Select the Category you want to enter:", contest_categories)
    
    # Dropdown to specify the social media platform
    social_platforms = ["Twitter", "Instagram", "LinkedIn", "Facebook", "Others"]
    selected_platform = st.selectbox("Select your Social Media Platform:", social_platforms)
    
    social_handle = st.text_input(f"Your {selected_platform} Handle:")
    post_link = st.text_input("Link to your post on social media:")

    if st.button("Enter the Contest"):
        # Save the contest entry details to Firestore
        contest_entries_ref.add({
            'artwork_name': artwork_name,
            'description': description,
            'contest_category': selected_category,
            'social_platform': selected_platform,
            'social_handle': social_handle,
            'post_link': post_link,
            'image_url': selected_image_url,
            'prompt': selected_prompt
        })
        st.success("You have successfully entered the contest!")

# Page to cast vote for contest entries
def cast_vote_page():
    st.header("Cast Your Vote")

    # Categories
    categories = [
        "Innovation Leadership",
        "Diversity and Community Impact",
        "The Future of Creativity",
        "The People's Choice"
    ]

    # Create a dictionary to store user's votes
    user_votes = {}
    selected_artworks = []

    for category in categories:
        # Fetch the list of submitted images for the specific category from Firebase
        docs = db.collection(st.session_state.current_session).document('contest_entries').collection('entries').where('contest_category', '==', category).stream()
        submissions = [doc.to_dict() for doc in docs]

        # Extract artwork options for dropdowns
        all_artwork_options = [(sub['image_url'], f"{sub['artwork_name']} by {sub['social_handle']} ({sub.get('platform', 'Unknown')})", sub['description']) for sub in submissions]

        # Check if there's any submission for the category
        if not all_artwork_options:
            st.warning(f"There are no submissions for {category} yet.")
            continue

        available_options = [option for option in all_artwork_options if option not in selected_artworks]
        
        selected_artwork_url, selected_artwork_display, description = st.selectbox(f"Vote for {category}", available_options, format_func=lambda x: x[1], key=category)
        
        # Display the selected image with description
        st.image(selected_artwork_url, caption=selected_artwork_display, use_column_width='auto')
        st.write(description)
        
        selected_artworks.append((selected_artwork_url, selected_artwork_display, description))
        user_votes[category] = {
            'artwork_url': selected_artwork_url,
            'display': selected_artwork_display
        }

    social_platforms = ["Twitter", "LinkedIn", "Instagram"]
    social_platform = st.selectbox("Your Social Media Platform:", social_platforms)
    social_handle = st.text_input(f"Your {social_platform} Handle:")
    
    if st.button("Submit Votes"):
        if not social_handle:
            st.warning(f"Please provide your {social_platform} handle.")
            return
        
        # Save user's votes to Firestore with their social handle
        user_votes['social_platform'] = social_platform
        user_votes['social_handle'] = social_handle
        db.collection(st.session_state.current_session).document('votes').collection('votes_data').add(user_votes)
        st.success("Thank you for casting your votes!")

# Page to view live votes leaderboard
def live_votes_page():
    st.header("Live Votes Leaderboard")

    # Fetch all votes from Firestore
    docs = db.collection(st.session_state.current_session).document('votes').collection('votes_data').stream()
    all_votes = [doc.to_dict() for doc in docs]

    # Create a dictionary to store vote counts
    vote_counts = {}
    # Create a set to store unique voter combinations
    unique_voters = set()

    # Loop through all votes and increment the vote count for each artwork
    for vote in all_votes:
        social_handle = vote.get('social_handle')
        social_platform = vote.get('social_platform')
        
        # Check for valid social_handle and social_platform
        if not social_handle or not social_platform:
            continue
        
        # Check for unique voter
        voter_id = f"{social_handle}_{social_platform}"
        if voter_id in unique_voters:
            continue
        unique_voters.add(voter_id)

        for category, details in vote.items():
            # Skip non-category items
            if category not in ["Innovation Leadership", "The Future of Creativity", "The People's Choice"]:
                continue
            
            artwork_display = details.get('display', None)
            if artwork_display:
                # Increment the vote count for the artwork
                if artwork_display in vote_counts:
                    vote_counts[artwork_display]["count"] += 1
                else:
                    vote_counts[artwork_display] = {
                        "artwork": artwork_display.split(" by ")[0],
                        "artist": artwork_display.split(" by ")[1].split(" ")[0],
                        "category": category,
                        "count": 1
                    }

    # Convert the dictionary to a pandas DataFrame and sort by vote count
    df_votes = pd.DataFrame(vote_counts.values()).sort_values(by="count", ascending=False)

    # Display the leaderboard
    st.table(df_votes)

# Admin page to manage sessions
def admin_page():
    st.header("Admin Section")

    # Password Protection for Admin Access
    admin_password = st.text_input("Enter Admin Password:", type="password")
    if admin_password != st.secrets["ADMIN_PASSWORD"]:
        st.warning("Incorrect password!")
        return

    # If correct password is entered
    st.success("Access granted!")

    # Fetch all existing sessions for the dropdown directly from Firestore
    sessions = [doc.to_dict() for doc in db.collection('sessions').stream()]
    session_names = [session['name'] for session in sessions]

    # Display a dropdown to select the current session
    current_session = st.selectbox("Select a session", ["Default Session"] + session_names)
    
    # Store current session in session_state
    st.session_state.current_session = current_session
    st.write(f"Current session set to: {current_session}")

    # Create a new session
    session_name = st.text_input("Name for the new session:")
    
    if st.button("Start New Session"):
        if not session_name:
            st.warning("Please provide a session name!")
            return

        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        db.collection('sessions').add({
            'name': session_name,
            'timestamp': timestamp
        })

        # Initialize collections for the new session
        db.collection(session_name).document('generated_images').set({})
        db.collection(session_name).document('contest_entries').set({})
        db.collection(session_name).document('votes').set({})

        st.success(f"New session '{session_name}' started!")
        
        # Refresh list of all sessions to update the dropdown
        sessions = [doc.to_dict() for doc in db.collection('sessions').stream()]
        session_names = [session['name'] for session in sessions]
def terms_and_conditions():
    st.sidebar.title("TERMS AND CONDITIONS")
    st.write("""
    **Terms and Conditions of Participation**

    By using the AI Art Prompt Labs platform, you agree to the following terms and conditions:

    1. **Ownership of Generated Images**: All images generated on our platform remain the property of Craft The Future.
    2. **Use of Generated Images**: We reserve the right to use any images generated on our platform for marketing, promotional, and other content-related purposes in the future.
    3. **No Compensation**: Participants will not be compensated for the use of images they generate on our platform.
    4. **Agreement**: By generating images on our platform, you are implicitly agreeing to these terms and conditions.

    If you do not agree with these terms, please refrain from using the platform.
    """)
def select_session():
    # Fetch all available collections (sessions) from Firestore
    collections = [collection.id for collection in db.collections()]
    
    # Ensure 'Default Session' is always part of the collections
    if "Default Session" not in collections:
        collections.insert(0, "Default Session")
    
    selected_session = st.sidebar.selectbox("Select a session", collections, index=collections.index(st.session_state.current_session))
    
    # Update session state with the selected session
    st.session_state.current_session = selected_session
    return selected_session
# Main Streamlit App
def main():
    st.title("AI Art Generator and Showcase")
    logo_url = "https://uploads-ssl.webflow.com/632c8750a360f9a85a9a72a8/633a2238ab4d88614f19f399_%5BOriginal%20size%5D%20%5BOriginal%20size%5D%20%5BOriginal%20size%5D%20%5BOriginal%20size%5D%20Craft%20The%20Future%20(1)-p-500.png"
    st.sidebar.image(logo_url, caption="Craft the Future", use_column_width=True, width=150)    
    # Initialize session state if not present
    if 'current_session' not in st.session_state:
        st.session_state.current_session = "Default Session"

    # Sidebar navigation
    st.sidebar.title("AI Art Prompt Labs /w CTF")
    st.sidebar.text("Select your event session:")
    current_session = select_session()  # Frontend session switcher
    st.sidebar.text(f"Current session: {current_session}")
    menu = ["TERMS AND CONDITIONS","Prompt Gallery", "Create Your Art", "Enter Contest", "Cast Your Vote", "Live Votes Leaderboard", "Admin"]
    choice = st.sidebar.selectbox("Menu", menu)
    st.sidebar.markdown("""
    **Menu Options Explained:**

    - **Prompt Gallery**: View the gallery of generated art images based on user prompts.
    - **Create Your Art**: Generate your own unique AI art based on positive and negative prompts.
    - **Enter Contest**: Submit your generated art for a chance to win in various categories.
    - **Cast Your Vote**: Vote for your favorite submitted artworks in different categories.
    - **Live Votes Leaderboard**: See which artworks are leading in votes in real-time.
    - **Admin**: Admin section for managing sessions.

    ---
    
    **Contest Entry Conditions:**
    
    All valid contest entries must be following [Craft The Future](https://www.linkedin.com/company/craft-the-future/?viewAsMember=true) on LinkedIn, [Instagram](https://www.instagram.com/_craftthefuture_/?img_index=1), and [Twitter](https://twitter.com/craftthefuture_). Make sure you are also following [FourevaMedia](https://twitter.com/FourevaMedia) on [Twitter](https://twitter.com/FourevaMedia), [Instagram](https://www.instagram.com/fourevamedia/), and [LinkedIn](https://www.linkedin.com/company/fourevamedia/).

    **Showcase Raffle:**
    
    All artworks submitted to the showcase will be entered into a raffle for CTF merch. Winners are drawn every hour. It's first-come, first-serve!

    **Winning the Contest:**

    If your artwork wins its category, you'll have the chance to have your art showcased as an LTM x CTF digital asset giveaway to all attendees on [OneOf Platform](https://www.oneof.com/app/).
    """)

    if choice == "TERMS AND CONDITIONS":
        terms_and_conditions()
    elif choice == "Prompt Gallery":
        prompt_gallery_page()
    elif choice == "Create Your Art":
        create_art_page()
    elif choice == "Enter Contest":
        enter_contest_page()
    elif choice == "Cast Your Vote":
        cast_vote_page()
    elif choice == "Live Votes Leaderboard":
        live_votes_page()
    elif choice == "Admin":
        admin_page()

if __name__ == "__main__":
    main()
