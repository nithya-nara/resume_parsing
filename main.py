import os
from flask import Flask, render_template, request
from PyPDF2 import PdfReader
from nltk.tokenize import word_tokenize
from nltk.corpus import stopwords
from nltk.stem import WordNetLemmatizer
import nltk
import matplotlib.pyplot as plt
import re
import psycopg2
from flask import jsonify

app = Flask(__name__)

# Download NLTK resources
nltk.download('punkt')
nltk.download('stopwords')
nltk.download('wordnet')

# Function to connect to PostgreSQL database
def connect_to_database():
    conn = psycopg2.connect(
        dbname='new_db',
        user='new_user',
        password='resume',
        host='localhost',
        port='5432'
    )
    return conn

# Function to insert scanned resume details into the database
def insert_into_database(conn, filename, matched_keywords_percentage, skills):
    cursor = conn.cursor()
    cursor.execute("INSERT INTO resumes (filename, matched_keywords_percentage, skills) VALUES (%s, %s, %s)",
                   (filename, matched_keywords_percentage, skills))
    conn.commit()

# Function to retrieve previously scanned resumes from the database
def retrieve_resumes_from_database():
    conn = connect_to_database()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM resumes")
    resumes = cursor.fetchall()
    conn.close()
    return resumes

# Function to extract text from PDF resume
def extract_text_from_pdf(pdf_file):
    text = ""
    reader = PdfReader(pdf_file)
    for page in reader.pages:
        text += page.extract_text()
    return text

# Function to extract keywords from text
def extract_keywords(text):
    tokens = word_tokenize(text)
    tokens = [word.lower() for word in tokens]
    stop_words = set(stopwords.words('english'))
    tokens = [word for word in tokens if word.isalnum() and word not in stop_words]
    lemmatizer = WordNetLemmatizer()
    tokens = [lemmatizer.lemmatize(word) for word in tokens]
    return tokens

# Function to calculate matched keywords percentage
def calculate_matched_keywords_percentage(job_description, resume_text):
    job_keywords = set(extract_keywords(job_description))
    resume_keywords = set(extract_keywords(resume_text))
    matched_keywords = job_keywords & resume_keywords
    total_keywords_count = len(job_keywords)
    if total_keywords_count == 0:
        return 0
    matched_keywords_percentage = (len(matched_keywords) / total_keywords_count) * 100
    return matched_keywords_percentage

# Function to extract skills from resume text
def extract_skills(resume_text):
    # Regular expression pattern to match common skills section titles

    skills_patterns = [
        r'\bSkills\b',
        r'\bTechnical\s+Skills\b',
        r'\bKey\s+Skills\b'
        # Add more patterns as needed
    ]

    skills = []
    for pattern in skills_patterns:
        match = re.search(pattern, resume_text, re.IGNORECASE)
        if match:
            skills_section = resume_text[match.end():]  # Start extracting from the end of the matched section title
            # Find the end of the section (next section title or end of text)
            end_match = re.search(r'\b(?:Skills|Technical\s+Skills|Key\s+Skills)\b', skills_section, re.IGNORECASE)
            if end_match:
                skills_section = skills_section[:end_match.start()]
            # Extracting only alphanumeric words from the section
            section_words = re.findall(r'\b([A-Za-z]+)\b', skills_section)
            skills += section_words[:8]
            break  # Exit loop after finding the first matching section

    return skills

# Route to display previously scanned resumes
@app.route('/previously-scanned-resumes')
def previously_scanned_resumes():
    resumes = retrieve_resumes_from_database()
    # Retrieve unique skills from the database
    conn = connect_to_database()
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT UNNEST(string_to_array(skills, ', ')) AS skill FROM resumes")
    skills = [row[0] for row in cursor.fetchall()]
    conn.close()
    return render_template('previously_scanned_resumes.html', resumes=resumes, skills=skills)

# Default route
@app.route('/')
def index():
    return render_template('index.html')

# Modify the '/filter-resumes' route to accept POST requests with JSON data
@app.route('/filter-resumes', methods=['POST'])
def filter_resumes():
    selected_skill = request.json.get('selected_skill')
    if not selected_skill:
        return jsonify({'error': 'No skill selected'})

    # Retrieve resumes from the database that contain the selected skill
    conn = connect_to_database()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM resumes WHERE skills ILIKE %s", ('%' + selected_skill + '%',))
    filtered_resumes = cursor.fetchall()
    conn.close()

    return jsonify(resumes=filtered_resumes)

@app.route('/upload', methods=['POST'])
def upload():
    if 'resume' not in request.files:
        return "No file part"
    resume_file = request.files['resume']
    if resume_file.filename == '':
        return "No selected file"
    try:
        resume_text = extract_text_from_pdf(resume_file)
        resume_skills = extract_skills(resume_text)
    except Exception as e:
        return f"Error: Unable to extract text from the PDF file ({e})"
    job_description = request.form.get('job_description', '')
    if not job_description or not resume_text:
        return "Error: Job description or resume text is empty"
    matched_keywords_percentage = calculate_matched_keywords_percentage(job_description, resume_text)
    matched_keywords_percentage = round(matched_keywords_percentage, 2)


# Displaying matched skills-related keywords
    job_keywords = set(extract_keywords(job_description))
    resume_keywords = set(extract_keywords(resume_text))
    matched_skills_keywords = job_keywords & resume_keywords

# Create static directory if it doesn't exist
    static_dir = os.path.join(os.getcwd(), 'static')
    if not os.path.exists(static_dir):
        os.makedirs(static_dir)

# Plotting pie chart
    labels = ['Matched Keywords', 'Unmatched Keywords']
    sizes = [len(matched_skills_keywords), len(job_keywords) - len(matched_skills_keywords)]
    colors = ['#ff9999', '#66b3ff']
    fig1, ax1 = plt.subplots()
    ax1.pie(sizes, colors=colors, labels=labels, autopct='%1.1f%%', startangle=90)
    ax1.axis('equal')  # Equal aspect ratio ensures that pie is drawn as a circle.
    plt.tight_layout()
    pie_chart_path = 'static/pie_chart.png'  # Save pie chart image
    plt.savefig(pie_chart_path)

# Assign the filename of the uploaded resume to resume_filename
    resume_filename = resume_file.filename

    conn = connect_to_database()
    insert_into_database(conn, resume_filename, matched_keywords_percentage, ', '.join(resume_skills))
    conn.close()

    return render_template('index.html', matched_keywords_percentage=matched_keywords_percentage,
                           matched_keywords=matched_skills_keywords, pie_chart_path=pie_chart_path,
                           resume_filename=resume_filename, resume_skills=resume_skills)

if __name__ == '__main__':
    app.run(debug=True)